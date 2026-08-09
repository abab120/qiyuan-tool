import hashlib
import json
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

import requests
from PyQt5.QtCore import QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import QMessageBox, QApplication


CURRENT_VERSION = "1.3.5"
# Upload a toolbox EXE asset to this repository to publish updates.
DEFAULT_RELEASE_API = "https://api.github.com/repos/abab120/qiyuan-tool/releases/latest"


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


def _run_hidden(args):
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    return subprocess.run(
        args,
        capture_output=True,
        timeout=30,
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
            result = _run_hidden(args)
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
    return {
        "version": version,
        "url": asset.get("browser_download_url"),
        "sha256": digest,
        "notes": data.get("body", ""),
    }


class CheckWorker(QThread):
    found = pyqtSignal(object)
    checked = pyqtSignal(object)
    error = pyqtSignal(str)

    def run(self):
        try:
            try:
                response = requests.get(
                    _manifest_url(),
                    timeout=8,
                    headers={"Accept": "application/json", "User-Agent": "QiyuanToolbox"},
                )
                response.raise_for_status()
                payload = response.json()
            except requests.exceptions.RequestException:
                payload = json.loads(_native_request(_manifest_url()))
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
        temp_path = Path(tempfile.gettempdir()) / "qj_toolbox_update.exe"
        try:
            try:
                response = requests.get(
                    self.manifest["url"],
                    stream=True,
                    timeout=30,
                    headers={"User-Agent": "QiyuanToolbox"},
                )
                response.raise_for_status()
                total = int(response.headers.get("content-length", 0))
                received = 0
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
            except requests.exceptions.RequestException:
                _native_request(self.manifest["url"], temp_path)
                digest = hashlib.sha256(temp_path.read_bytes())
                self.progress.emit(100)
            expected = str(self.manifest.get("sha256", "")).lower().replace("sha256:", "")
            if expected and digest.hexdigest().lower() != expected:
                raise ValueError("下载文件校验失败")
            self.completed.emit(str(temp_path))
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

    def schedule(self):
        QTimer.singleShot(1800, self.check)

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
            self.downloader = DownloadWorker(manifest, self.parent)
            self.downloader.progress.connect(lambda value: self.parent.statusBar().showMessage(f"正在下载更新 {value}%"))
            self.downloader.completed.connect(self._apply)
            self.downloader.failed.connect(lambda error: QMessageBox.warning(self.parent, "更新失败", error))
            self.downloader.start()

    def _apply(self, downloaded):
        if not getattr(sys, "frozen", False):
            QMessageBox.information(self.parent, "更新提示", "开发模式不会替换 Python 解释器，请在打包后的 EXE 中更新。")
            return
        current = Path(sys.executable).resolve()
        script = Path(tempfile.gettempdir()) / "qj_apply_update.cmd"
        script.write_text(
            "@echo off\r\n"
            "timeout /t 2 /nobreak >nul\r\n"
            f'copy /y "{downloaded}" "{current}" >nul\r\n'
            f'start "" "{current}"\r\n'
            f'del "%~f0"\r\n',
            encoding="mbcs",
        )
        subprocess.Popen(["cmd.exe", "/c", str(script)], creationflags=0x08000000)
        QApplication.instance().quit()
