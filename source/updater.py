import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import shutil
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from pathlib import Path

import requests
import urllib3
from PyQt5.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import QMessageBox, QApplication, QProgressDialog


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


CURRENT_VERSION = "1.2.0"
# Upload a toolbox EXE asset to this repository to publish updates.
DEFAULT_RELEASE_API = "https://gitee.com/api/v5/repos/xiaoqi313/qiyuan-tool/releases/latest"
FALLBACK_RELEASE_API = "https://api.github.com/repos/abab120/qiyuan-tool/releases/latest"


def _base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _version(value):
    parts = []
    for item in str(value).lstrip("vV").split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple((parts + [0, 0, 0])[:3])


def _manifest_url():
    config = _base_dir() / "update.json"
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
        if data.get("url"):
            return str(data["url"])
    except (OSError, ValueError, TypeError):
        pass
    return os.environ.get("QJ_TOOLBOX_UPDATE_URL", DEFAULT_RELEASE_API)


def _run_hidden(args, timeout=30):
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    return subprocess.run(
        args,
        capture_output=True,
        timeout=timeout,
        startupinfo=startupinfo,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=True,
    )


def _powershell_request(url, output_path=None):
    """Use Windows' Schannel certificate store when Python's CA bundle is unavailable."""
    escaped_url = str(url).replace("'", "''")
    if output_path is None:
        script = (
            "$ProgressPreference='SilentlyContinue'; "
            f"(Invoke-WebRequest -UseBasicParsing -Uri '{escaped_url}' "
            "-Headers @{Accept='application/json'; 'User-Agent'='QiyuanToolbox'}).Content"
        )
    else:
        escaped_path = str(output_path).replace("'", "''")
        script = (
            "$ProgressPreference='SilentlyContinue'; "
            f"Invoke-WebRequest -UseBasicParsing -Uri '{escaped_url}' -OutFile '{escaped_path}'"
        )
    result = _run_hidden(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        timeout=300 if output_path is not None else 30,
    )
    return result.stdout.decode("utf-8-sig", errors="replace") if output_path is None else None


def _native_request(url, output_path=None):
    """Use Windows Schannel clients without opening a console window."""
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if curl:
        args = [curl, "--fail", "--silent", "--show-error", "--location", "--max-time", "25", "--user-agent", "QiyuanToolbox"]
        if output_path is None:
            args.append(str(url))
        else:
            args.extend(["--output", str(output_path), str(url)])
        try:
            result = _run_hidden(args, timeout=300 if output_path is not None else 30)
            return result.stdout.decode("utf-8-sig", errors="replace") if output_path is None else None
        except (OSError, subprocess.CalledProcessError):
            pass
    return _powershell_request(url, output_path)


def _read_release(data):
    if "version" in data and "url" in data:
        return data
    version = data.get("tag_name", "")
    assets = data.get("assets", [])
    asset = next(
        (
            x
            for x in assets
            if str(x.get("name", "")).lower().endswith(".exe")
            and ("toolbox" in str(x.get("name", "")).lower() or "柒悁" in str(x.get("name", "")))
        ),
        None,
    )
    if not asset:
        return None
    digest = asset.get("digest", "")
    if digest.startswith("sha256:"):
        digest = digest[7:]
    if not digest:
        match = re.search(r"sha256\s*[:=]\s*([0-9a-f]{64})", str(data.get("body", "")), re.IGNORECASE)
        if match:
            digest = match.group(1)
    download_url = asset.get("browser_download_url")
    return {
        "version": version,
        "url": download_url,
        "mirrors": _mirror_urls(download_url),
        "sha256": digest,
        "notes": data.get("body", ""),
    }


def _mirror_urls(url):
    """Return optional CDN URLs for GitHub assets, keeping the original URL as fallback."""
    if not url:
        return []
    parsed = urlparse(str(url))
    if parsed.scheme != "https" or parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        return []
    return [f"https://gh-proxy.com/{url}"]


def _parallel_download(url, output_path, progress, expected_digest):
    """Download a ranged asset concurrently; return False when Range is unsupported."""
    if not expected_digest:
        return False
    probe = requests.get(
        url,
        stream=True,
        headers={"Range": "bytes=0-0", "User-Agent": "QiyuanToolbox"},
        timeout=(8, 10),
        verify=False,
    )
    try:
        if probe.status_code != 206:
            return False
        content_range = probe.headers.get("content-range", "")
        if "/" not in content_range:
            return False
        total = int(content_range.rsplit("/", 1)[1])
    finally:
        probe.close()
    if total < 4 * 1024 * 1024:
        return False

    workers = 4
    step = (total + workers - 1) // workers
    ranges = [(start, min(total - 1, start + step - 1)) for start in range(0, total, step)]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as output:
        output.truncate(total)
    completed = 0
    lock = threading.Lock()

    def fetch_range(start, end):
        nonlocal completed
        response = requests.get(
            url,
            stream=True,
            headers={
                "Range": f"bytes={start}-{end}",
                "User-Agent": "QiyuanToolbox",
            },
            timeout=(8, 10),
            verify=False,
        )
        try:
            if response.status_code != 206:
                raise ValueError("下载线路不支持分段请求")
            remaining = end - start + 1
            position = start
            with output_path.open("r+b") as output:
                for chunk in response.iter_content(1024 * 256):
                    if not chunk:
                        continue
                    chunk = chunk[:remaining]
                    output.seek(position)
                    output.write(chunk)
                    position += len(chunk)
                    remaining -= len(chunk)
                    with lock:
                        completed += len(chunk)
                        progress(min(99, completed * 100 // total))
                    if remaining <= 0:
                        break
            if remaining:
                raise IOError("分段下载未完成")
        finally:
            response.close()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch_range, start, end) for start, end in ranges]
        for future in as_completed(futures):
            future.result()
    return True


class CheckWorker(QThread):
    found = pyqtSignal(object)
    checked = pyqtSignal(object)
    error = pyqtSignal(str)

    @staticmethod
    def _fetch_payload(endpoint):
        """Fetch one release endpoint, falling back to Windows' native TLS client."""
        try:
            response = requests.get(
                endpoint,
                timeout=(3, 5),
                headers={"Accept": "application/json", "User-Agent": "QiyuanToolbox"},
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            return json.loads(_native_request(endpoint))

    def run(self):
        try:
            endpoints = [_manifest_url()]
            if FALLBACK_RELEASE_API not in endpoints:
                endpoints.append(FALLBACK_RELEASE_API)
            payload = None
            last_error = None
            executor = ThreadPoolExecutor(max_workers=len(endpoints))
            futures = [executor.submit(self._fetch_payload, endpoint) for endpoint in endpoints]
            try:
                # Race the configured channel and the fallback so a slow
                # provider never blocks a healthy one.
                for future in as_completed(futures):
                    try:
                        payload = future.result()
                        if payload:
                            break
                    except Exception as exc:
                        last_error = exc
            finally:
                for future in futures:
                    future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
            if payload is None:
                raise last_error or RuntimeError("无法获取更新信息")
            manifest = _read_release(payload)
            self.checked.emit(manifest)
            if manifest and _version(manifest.get("version")) > _version(CURRENT_VERSION):
                self.found.emit(manifest)
        except Exception as exc:
            self.error.emit(str(exc))


class DownloadWorker(QThread):
    progress = pyqtSignal(int)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, manifest, parent=None):
        super().__init__(parent)
        self.manifest = manifest

    def run(self):
        fd, temp_name = tempfile.mkstemp(prefix="qj_toolbox_update_", suffix=".exe")
        os.close(fd)
        temp_path = Path(temp_name)
        expected = str(self.manifest.get("sha256", "")).lower().replace("sha256:", "")
        urls = []
        for url in [*self.manifest.get("mirrors", []), self.manifest.get("url")]:
            if url and url not in urls:
                urls.append(url)
        last_error = None
        try:
            for url in urls:
                try:
                    temp_path.unlink(missing_ok=True)
                    if _parallel_download(url, temp_path, self.progress.emit, expected):
                        digest = hashlib.sha256(temp_path.read_bytes())
                        if expected and digest.hexdigest().lower() != expected:
                            raise ValueError("下载文件校验失败")
                        self.progress.emit(100)
                        self.completed.emit(str(temp_path))
                        return
                    temp_path.unlink(missing_ok=True)
                    response = requests.get(
                        url,
                        stream=True,
                        timeout=(8, 20),
                        headers={"User-Agent": "QiyuanToolbox"},
                    )
                    response.raise_for_status()
                    total = int(response.headers.get("content-length", 0))
                    received = 0
                    started = time.monotonic()
                    digest = hashlib.sha256()
                    with temp_path.open("wb") as output:
                        for chunk in response.iter_content(1024 * 256):
                            if not chunk:
                                continue
                            output.write(chunk)
                            digest.update(chunk)
                            received += len(chunk)
                            if total:
                                self.progress.emit(min(100, received * 100 // total))
                            # Move to the next route when a CDN is accepting the
                            # connection but delivering unusably slowly.
                            elapsed = time.monotonic() - started
                            if received >= 512 * 1024 and elapsed >= 6 and received / elapsed < 96 * 1024:
                                raise TimeoutError("当前下载线路速度过慢")
                    if expected and digest.hexdigest().lower() != expected:
                        raise ValueError("下载文件校验失败")
                    self.progress.emit(100)
                    self.completed.emit(str(temp_path))
                    return
                except requests.exceptions.RequestException as exc:
                    # If Python's TLS stack is unavailable, retry this route
                    # through Windows' Schannel-backed curl/PowerShell client.
                    try:
                        temp_path.unlink(missing_ok=True)
                        _native_request(url, temp_path)
                        digest = hashlib.sha256(temp_path.read_bytes())
                        if expected and digest.hexdigest().lower() != expected:
                            raise ValueError("下载文件校验失败")
                        self.progress.emit(100)
                        self.completed.emit(str(temp_path))
                        return
                    except Exception as native_exc:
                        last_error = native_exc
                        continue
                except (OSError, TimeoutError, ValueError) as exc:
                    last_error = exc
                    continue
                except Exception as exc:
                    last_error = exc
                    continue
            if last_error:
                raise last_error
            raise ValueError("没有可用的下载地址")
        except Exception as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            self.failed.emit(str(exc))


class Updater:
    def __init__(self, parent):
        self.parent = parent
        self.checker = None
        self.downloader = None
        self.manifest = None
        self.progress_dialog = None

    def schedule(self):
        QTimer.singleShot(300, self.check)

    def check(self):
        self.checker = CheckWorker(self.parent)
        self.checker.found.connect(self._offer)
        self.checker.finished.connect(self._release_checker)
        self.checker.start()

    def check_now(self, checked, failed):
        if self.checker and self.checker.isRunning():
            return False
        self.checker = CheckWorker(self.parent)
        self.checker.checked.connect(checked)
        self.checker.error.connect(failed)
        self.checker.finished.connect(self._release_checker)
        self.checker.start()
        return True

    def _release_checker(self):
        self.checker = None

    def _offer(self, manifest):
        self.manifest = manifest
        message = f"发现新版本 {manifest.get('version')}，当前版本为 {CURRENT_VERSION}。\n\n现在下载并更新吗？"
        if QMessageBox.question(self.parent, "发现更新", message, QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self._show_progress_dialog()
            self.downloader = DownloadWorker(manifest, self.parent)
            self.downloader.progress.connect(self._on_download_progress)
            self.downloader.completed.connect(self._apply)
            self.downloader.failed.connect(self._on_download_failed)
            self.downloader.start()

    def _show_progress_dialog(self):
        self.progress_dialog = QProgressDialog("正在准备下载更新... 0%", "", 0, 100, self.parent)
        self.progress_dialog.setWindowTitle("下载更新")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.setAutoReset(False)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()

    def _on_download_progress(self, value):
        if self.progress_dialog is not None:
            self.progress_dialog.setLabelText(f"正在下载更新... {value}%")
            self.progress_dialog.setValue(value)
        self.parent.statusBar().showMessage(f"正在下载更新 {value}%")

    def _close_progress_dialog(self):
        if self.progress_dialog is not None:
            self.progress_dialog.close()
            self.progress_dialog.deleteLater()
            self.progress_dialog = None

    def _on_download_failed(self, error):
        self._close_progress_dialog()
        QMessageBox.warning(self.parent, "更新失败", error)

    def _apply(self, downloaded):
        self._close_progress_dialog()
        if not getattr(sys, "frozen", False):
            QMessageBox.information(self.parent, "更新提示", "开发模式不会替换 Python 解释器，请在打包后的 EXE 中更新。")
            return
        current = Path(sys.executable).resolve()
        old_copy = current.with_name(current.name + ".old")
        script = Path(tempfile.gettempdir()) / f"qj_apply_update_{os.getpid()}.cmd"
        script.write_text(
            "@echo off\r\n"
            "setlocal\r\n"
            "timeout /t 1 /nobreak >nul\r\n"
            ":retry\r\n"
            f'del /q "{old_copy}" >nul 2>nul\r\n'
            f'move /y "{current}" "{old_copy}" >nul 2>nul\r\n'
            "if errorlevel 1 (\r\n"
            "  timeout /t 1 /nobreak >nul\r\n"
            "  goto retry\r\n"
            ")\r\n"
            f'copy /y "{downloaded}" "{current}" >nul 2>nul\r\n'
            "if errorlevel 1 (\r\n"
            f'  move /y "{old_copy}" "{current}" >nul 2>nul\r\n'
            "  timeout /t 1 /nobreak >nul\r\n"
            "  goto retry\r\n"
            ")\r\n"
            f'start "" "{current}"\r\n'
            f'del /q "{old_copy}" >nul 2>nul\r\n'
            f'del /q "{downloaded}" >nul 2>nul\r\n'
            f'del "%~f0"\r\n',
            encoding="mbcs",
        )
        QMessageBox.information(
            self.parent,
            "更新完成",
            "新版本将自动安装，程序将自动重启，并清理旧版本和临时文件。",
        )
        subprocess.Popen(["cmd.exe", "/c", str(script)], creationflags=0x08000000)
        QApplication.instance().quit()
