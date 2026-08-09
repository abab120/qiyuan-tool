import marshal
import ctypes
import os
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path


def resource_path(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    if not getattr(sys, "frozen", False) and (base / "柒悁工具箱").is_dir():
        base = base / "柒悁工具箱"
    return base / name


def load_raw(name):
    path = resource_path(name + ".raw")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[name] = module
    exec(marshal.loads(path.read_bytes()), module.__dict__)
    return module


# These imports are intentionally explicit so PyInstaller includes runtime-only imports.
import psutil  # noqa: F401
import updater
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QLockFile, QThread, QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices
from jihao_panel import JihaoPanel

tool = load_raw("tool")


def _acquire_instance_guard():
    """Return a process-held lock, or an explanatory message when already open."""
    current_pid = os.getpid()
    try:
        bootloader_pid = psutil.Process(current_pid).ppid()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        bootloader_pid = 0
    process_names = {"toolbox", "toolbox.exe", "柒悁工具箱", "柒悁工具箱.exe"}
    for proc in psutil.process_iter(["pid", "name", "ppid"]):
        try:
            pid = int(proc.info["pid"])
            # PyInstaller one-file builds briefly have a bootloader parent and
            # a child process with the same executable name. They are one launch.
            if pid in {current_pid, bootloader_pid} or int(proc.info.get("ppid") or 0) == current_pid:
                continue
            if (proc.info.get("name") or "").lower() in process_names:
                return None, "检测到柒悁工具箱已在后台运行，不允许多开。"
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, TypeError, ValueError):
            continue

    lock_path = Path(tempfile.gettempdir()) / "qiyuan-toolbox-single-instance.lock"
    lock = QLockFile(str(lock_path))
    lock.setStaleLockTime(5000)
    if not lock.tryLock(100):
        return None, "检测到柒悁工具箱已在后台运行，不允许多开。"
    return lock, None


def _refresh_process_table(self):
    table = self.process_table
    rows = []
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = proc.info
            memory = int(getattr(info.get("memory_info"), "rss", 0) or 0)
            rows.append((memory, int(info["pid"]), info.get("name") or "未知进程"))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, TypeError, ValueError):
            continue
    rows.sort(reverse=True)
    table.setRowCount(0)
    for memory, pid, name in rows:
        row = table.rowCount()
        table.insertRow(row)
        checked = QTableWidgetItem()
        checked.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        checked.setCheckState(Qt.Unchecked)
        table.setItem(row, 0, checked)
        table.setItem(row, 1, QTableWidgetItem(name))
        table.setItem(row, 2, QTableWidgetItem(str(pid)))
        table.setItem(row, 3, QTableWidgetItem(f"{memory / 1024 / 1024:.0f} MB"))
    self.process_status.setText(f"共 {len(rows)} 个进程，已按内存占用排序")


def _end_selected_processes(self):
    table = self.process_table
    selected = []
    for row in range(table.rowCount()):
        checkbox = table.item(row, 0)
        if checkbox and checkbox.checkState() == Qt.Checked:
            pid_item = table.item(row, 2)
            name_item = table.item(row, 1)
            if pid_item and name_item:
                try:
                    selected.append((int(pid_item.text()), name_item.text()))
                except ValueError:
                    pass
    selected = [(pid, name) for pid, name in selected if pid != os.getpid()]
    if not selected:
        QMessageBox.information(self, "结束进程", "请先勾选要结束的进程。")
        return
    names = "、".join(name for _, name in selected[:6])
    if len(selected) > 6:
        names += " 等"
    answer = QMessageBox.question(
        self,
        "确认结束进程",
        f"确定结束 {len(selected)} 个进程吗？\n\n{names}",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if answer != QMessageBox.Yes:
        return
    ended = 0
    failed = []
    for pid, name in selected:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=1.5)
            except psutil.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1.5)
            ended += 1
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            ended += 1
        except (psutil.AccessDenied, psutil.TimeoutExpired, OSError) as exc:
            failed.append(f"{name} ({exc})")
    _refresh_process_table(self)
    message = f"已结束 {ended} 个进程。"
    if failed:
        message += "\n以下进程未能结束：\n" + "\n".join(failed[:8])
    QMessageBox.information(self, "操作完成", message)


def _init_process_tab(self):
    layout = QVBoxLayout(self.tab_process)
    title = QLabel("勾选进程后结束，系统进程可能需要管理员权限")
    title.setObjectName("processHint")
    layout.addWidget(title)

    self.process_table = QTableWidget(0, 4)
    self.process_table.setHorizontalHeaderLabels(["选择", "进程名称", "PID", "内存"])
    self.process_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    self.process_table.setSelectionMode(QAbstractItemView.SingleSelection)
    self.process_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    self.process_table.verticalHeader().setVisible(False)
    self.process_table.setAlternatingRowColors(True)
    self.process_table.setColumnWidth(0, 58)
    self.process_table.setColumnWidth(2, 90)
    self.process_table.setColumnWidth(3, 100)
    self.process_table.horizontalHeader().setStretchLastSection(True)
    layout.addWidget(self.process_table, 1)

    self.process_status = QLabel("正在读取进程...")
    layout.addWidget(self.process_status)
    self.process_log = QTextEdit()
    self.process_log.setReadOnly(True)
    self.process_log.setMaximumHeight(96)
    self.process_log.setPlaceholderText("服务列表将在这里显示")
    layout.addWidget(self.process_log)

    buttons = QHBoxLayout()
    end_button = QPushButton("结束选中进程")
    end_button.clicked.connect(lambda: _end_selected_processes(self))
    refresh_button = QPushButton("刷新进程")
    refresh_button.clicked.connect(lambda: _refresh_process_table(self))
    service_button = QPushButton("列出运行中的服务")
    service_button.clicked.connect(self.list_services)
    buttons.addWidget(end_button)
    buttons.addWidget(refresh_button)
    buttons.addWidget(service_button)
    layout.addLayout(buttons)
    _refresh_process_table(self)


def _install_process_manager():
    tool.ToolBox.init_process_tab = _init_process_tab
    tool.ToolBox.list_processes = _refresh_process_table


_install_process_manager()


CURRENT_VERSION = "1.2.2"
OPEN_SOURCE_URL = "https://github.com/abab120/qiyuan-tool"


class AboutPanel(QWidget):
    def __init__(self, updater, parent=None):
        super().__init__(parent)
        self.updater = updater
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel("关于柒悁工具箱")
        title.setObjectName("contentTitle")
        layout.addWidget(title)
        subtitle = QLabel("版本、更新与开源信息")
        subtitle.setObjectName("contentStatus")
        layout.addWidget(subtitle)

        info = QLabel(f"当前版本  v{CURRENT_VERSION}\n运行环境  Windows 64 位\n项目地址  github.com/abab120/qiyuan-tool")
        info.setObjectName("aboutInfo")
        layout.addWidget(info)

        changelog_title = QLabel("更新日志")
        changelog_title.setObjectName("contentTitle")
        layout.addWidget(changelog_title)
        self.changelog = QTextEdit()
        self.changelog.setReadOnly(True)
        self.changelog.setMaximumHeight(190)
        self.changelog.setPlainText(
            "v1.2.2\n"
            "• 嘉豪专区增加多种模板并支持导出 HTML 爱心代码\n"
            "• 优化任务栏图标和单实例启动识别\n"
            "• 123 网盘渠道改为确认更新后再启用\n\n"
            "v1.2.1\n"
            "• 增加嘉豪专用爱心文字模块，支持自定义显示文字\n"
            "• 增加后台进程检测，禁止程序多开\n"
            "• 优化圆角界面和下载提示\n\n"
            "v1.2.0\n"
            "• 磁盘清理支持选择不同磁盘，并重新整理清理界面\n"
            "• 移除常用库管理模块，关于页面移动到末尾\n"
            "• 下载页增加微信、QQ 内置浏览器提示\n\n"
            "v1.1.0\n"
            "• 增加分类磁盘清理、浏览器缓存和应用缓存扫描\n"
            "• 更新安装完成后自动替换、重启并清理旧文件\n\n"
            "v1.0.0\n"
            "• 首个统一版工具箱发布"
        )
        layout.addWidget(self.changelog)

        self.status = QLabel("更新状态：尚未检查")
        self.status.setObjectName("contentStatus")
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.check_button = QPushButton("检查更新")
        self.check_button.clicked.connect(self.check_updates)
        source_button = QPushButton("开源信息")
        source_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(OPEN_SOURCE_URL)))
        buttons.addWidget(self.check_button)
        buttons.addWidget(source_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)

    def check_updates(self):
        self.check_button.setEnabled(False)
        self.status.setText("更新状态：正在检查...")
        if not self.updater.check_now(self.on_checked, self.on_failed):
            self.check_button.setEnabled(True)
            self.status.setText("更新状态：已有检查任务")

    def on_checked(self, manifest):
        self.check_button.setEnabled(True)
        if manifest and updater._version(manifest.get("version")) > updater._version(CURRENT_VERSION):
            self.status.setText(f"更新状态：发现新版本 {manifest.get('version')}")
            self.updater._offer(manifest)
        else:
            self.status.setText("更新状态：当前已是最新版本")

    def on_failed(self, error):
        self.check_button.setEnabled(True)
        self.status.setText("更新状态：检查失败，请确认网络连接")


class DiskCleanupWorker(QThread):
    scanned = pyqtSignal(object)
    completed = pyqtSignal(int, int)
    failed = pyqtSignal(str)

    def __init__(self, targets, cleanup=False, parent=None):
        super().__init__(parent)
        self.targets = targets
        self.cleanup = cleanup

    def _files(self, target):
        root = target["path"]
        if target["kind"] == "glob":
            if root.exists():
                yield from (path for path in root.glob(target["pattern"]) if path.is_file())
            return
        if not root.exists():
            return
        current_mei = Path(getattr(sys, "_MEIPASS", "")).resolve()
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                if current_mei and current_mei != Path(".").resolve() and current_mei in path.parents:
                    continue
            except OSError:
                continue
            yield path

    def run(self):
        try:
            results = []
            removed_bytes = 0
            removed_files = 0
            for target in self.targets:
                size = 0
                files = list(self._files(target))
                for path in files:
                    try:
                        size += path.stat().st_size
                    except OSError:
                        continue
                results.append({"key": target["key"], "size": size, "files": len(files)})
                if self.cleanup:
                    for path in files:
                        try:
                            amount = path.stat().st_size
                            path.unlink()
                            removed_bytes += amount
                            removed_files += 1
                        except (OSError, PermissionError):
                            continue
                    if target["kind"] == "tree" and target["path"].exists():
                        for directory in sorted(target["path"].rglob("*"), reverse=True):
                            if directory.is_dir():
                                try:
                                    directory.rmdir()
                                except OSError:
                                    pass
            if self.cleanup:
                self.completed.emit(removed_bytes, removed_files)
            else:
                self.scanned.emit(results)
        except Exception as exc:
            self.failed.emit(str(exc))


class DiskCleanupPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.rows = {}
        local_app_data = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
        self.targets = [
            {"key": "user_temp", "name": "用户临时文件", "path": Path(tempfile.gettempdir()), "kind": "tree", "default": True},
            {"key": "windows_temp", "name": "Windows 临时文件", "path": Path(os.environ.get("WINDIR", "C:\\Windows")) / "Temp", "kind": "tree", "default": False},
            {"key": "thumbcache", "name": "缩略图缓存", "path": local_app_data / "Microsoft" / "Windows" / "Explorer", "kind": "glob", "pattern": "thumbcache*.db", "default": False},
        ]
        layout = QVBoxLayout(self)
        title = QLabel("扫描并清理可重建的临时文件，不会删除文档、图片或项目文件")
        title.setObjectName("contentStatus")
        layout.addWidget(title)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["清理", "项目", "占用空间"])
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.status = QLabel("准备扫描")
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.scan_button = QPushButton("扫描磁盘")
        self.scan_button.clicked.connect(self.scan)
        self.clean_button = QPushButton("清理选中")
        self.clean_button.clicked.connect(self.clean)
        self.clean_button.setEnabled(False)
        buttons.addWidget(self.scan_button)
        buttons.addWidget(self.clean_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        QTimer.singleShot(100, self.scan)

    @staticmethod
    def _format_size(size):
        if size >= 1024 ** 3:
            return f"{size / 1024 ** 3:.2f} GB"
        if size >= 1024 ** 2:
            return f"{size / 1024 ** 2:.1f} MB"
        return f"{size / 1024:.1f} KB"

    def _set_busy(self, busy, message):
        self.scan_button.setEnabled(not busy)
        self.clean_button.setEnabled(not busy and bool(self.rows))
        self.progress.setVisible(busy)
        if busy:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
        self.status.setText(message)

    def scan(self):
        if self.worker and self.worker.isRunning():
            return
        self._set_busy(True, "正在扫描可清理文件...")
        self.worker = DiskCleanupWorker(self.targets, parent=self)
        self.worker.scanned.connect(self._on_scanned)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._release_worker)
        self.worker.start()

    def _on_scanned(self, results):
        self.table.setRowCount(0)
        self.rows = {}
        for result, target in zip(results, self.targets):
            row = self.table.rowCount()
            self.table.insertRow(row)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            check.setCheckState(Qt.Checked if target.get("default") else Qt.Unchecked)
            self.table.setItem(row, 0, check)
            self.table.setItem(row, 1, QTableWidgetItem(target["name"]))
            self.table.setItem(row, 2, QTableWidgetItem(self._format_size(result["size"])))
            self.rows[target["key"]] = (row, result["size"])
        total = sum(item[1] for item in self.rows.values())
        self._set_busy(False, f"扫描完成，可清理 {self._format_size(total)}")

    def _selected_targets(self):
        selected = []
        for target in self.targets:
            row_info = self.rows.get(target["key"])
            if row_info and self.table.item(row_info[0], 0).checkState() == Qt.Checked:
                selected.append(target)
        return selected

    def clean(self):
        selected = self._selected_targets()
        total = sum(self.rows[target["key"]][1] for target in selected)
        if not selected or total <= 0:
            QMessageBox.information(self, "磁盘清理", "没有可清理的已选项目。")
            return
        answer = QMessageBox.question(
            self,
            "确认清理",
            f"确定清理选中的 {self._format_size(total)} 临时文件吗？\n正在使用的文件会自动跳过。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._set_busy(True, "正在清理文件...")
        self.worker = DiskCleanupWorker(selected, cleanup=True, parent=self)
        self.worker.completed.connect(self._on_cleaned)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._release_worker)
        self.worker.start()

    def _on_cleaned(self, amount, files):
        self._set_busy(False, f"已清理 {files} 个文件，释放 {self._format_size(amount)}")
        QTimer.singleShot(200, self.scan)

    def _on_failed(self, error):
        self._set_busy(False, f"扫描失败：{error}")

    def _release_worker(self):
        self.worker = None


class ProDiskCleanupWorker(QThread):
    progress = pyqtSignal(int, str)
    scanned = pyqtSignal(object)
    completed = pyqtSignal(int, int)
    failed = pyqtSignal(str)

    def __init__(self, targets, cleanup=False, parent=None):
        super().__init__(parent)
        self.targets = targets
        self.cleanup = cleanup

    def _files(self, target):
        current_mei = Path(getattr(sys, "_MEIPASS", "")).resolve()
        cutoff = time.time() - int(target.get("min_age_seconds", 0))
        seen = set()
        for root in target.get("paths", []):
            root = Path(root)
            if not root.exists():
                continue
            candidates = root.glob(target.get("pattern", "*")) if target.get("kind") == "glob" else root.rglob("*")
            for path in candidates:
                if not path.is_file():
                    continue
                try:
                    resolved = path.resolve()
                    if resolved in seen or (current_mei != Path(".").resolve() and current_mei in resolved.parents):
                        continue
                    if path.stat().st_mtime > cutoff:
                        continue
                except OSError:
                    continue
                seen.add(resolved)
                yield path

    def run(self):
        try:
            results = []
            removed_bytes = 0
            removed_files = 0
            count = max(1, len(self.targets))
            for index, target in enumerate(self.targets, 1):
                self.progress.emit(int((index - 1) * 100 / count), f"正在扫描 {target['name']}...")
                files = list(self._files(target))
                size = 0
                for path in files:
                    try:
                        size += path.stat().st_size
                    except OSError:
                        pass
                results.append({"key": target["key"], "size": size, "files": len(files)})
                if self.cleanup:
                    for path in files:
                        try:
                            amount = path.stat().st_size
                            path.unlink()
                            removed_bytes += amount
                            removed_files += 1
                        except (OSError, PermissionError):
                            continue
                    for root in target.get("paths", []):
                        root = Path(root)
                        if target.get("kind") == "tree" and root.exists():
                            for directory in sorted(root.rglob("*"), reverse=True):
                                if directory.is_dir():
                                    try:
                                        directory.rmdir()
                                    except OSError:
                                        pass
            if self.cleanup:
                self.completed.emit(removed_bytes, removed_files)
            else:
                self.progress.emit(100, "扫描完成")
                self.scanned.emit(results)
        except Exception as exc:
            self.failed.emit(str(exc))


class ProDiskCleanupPanel(QWidget):
    @staticmethod
    def _available_drives():
        drives = []
        seen = set()
        for part in psutil.disk_partitions(all=False):
            root = Path(part.mountpoint)
            try:
                key = str(root.resolve()).lower()
            except OSError:
                continue
            if key in seen or not root.exists():
                continue
            seen.add(key)
            label = part.device or str(root)
            if part.fstype:
                label = f"{label} ({part.fstype})"
            drives.append((root, label))
        if not drives:
            root = Path(os.environ.get("SystemDrive", "C:\\"))
            drives.append((root, str(root)))
        return drives

    def _targets_for_drive(self, root):
        try:
            is_system = root.resolve() == self._system_drive.resolve()
        except OSError:
            is_system = str(root).lower() == str(self._system_drive).lower()
        if is_system:
            return [dict(target, paths=list(target["paths"])) for target in self._system_targets]
        drive_name = root.drive or str(root)
        return [
            {"key": "system", "name": f"{drive_name} 临时文件", "description": "该磁盘 Temp、tmp 和 Windows 临时目录", "paths": [root / "Temp", root / "tmp", root / "Windows" / "Temp"], "kind": "tree", "default": True, "min_age_seconds": 900},
            {"key": "browser", "name": "浏览器缓存", "description": "该磁盘未发现浏览器缓存目录", "paths": [], "kind": "tree", "default": False},
            {"key": "wechat", "name": "微信缓存", "description": "该磁盘未发现微信缓存目录", "paths": [], "kind": "tree", "default": False},
            {"key": "qq", "name": "QQ 缓存", "description": "该磁盘未发现 QQ 缓存目录", "paths": [], "kind": "tree", "default": False},
            {"key": "thumbs", "name": "缩略图缓存", "description": "该磁盘未发现缩略图缓存", "paths": [], "kind": "glob", "pattern": "thumbcache*.db", "default": False},
            {"key": "reports", "name": "崩溃报告", "description": "该磁盘未发现崩溃报告目录", "paths": [], "kind": "tree", "default": False},
            {"key": "updates", "name": "系统更新缓存", "description": "该磁盘未发现系统更新缓存", "paths": [], "kind": "tree", "default": False},
            {"key": "recent", "name": "使用痕迹", "description": "该磁盘未发现使用痕迹目录", "paths": [], "kind": "tree", "default": False},
            {"key": "recycle", "name": "回收站", "description": "清空该磁盘回收站中的项目", "paths": [root / "$RECYCLE.BIN"], "kind": "tree", "default": False},
        ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.rows = {}
        local = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
        roaming = Path(os.environ.get("APPDATA", local / "Roaming"))
        windows = Path(os.environ.get("WINDIR", "C:\\Windows"))

        def browser_roots(base):
            roots = []
            if base.exists():
                for profile in base.iterdir():
                    if not profile.is_dir():
                        continue
                    for name in ("Cache", "Code Cache", "GPUCache", "ShaderCache"):
                        path = profile / name
                        if path.exists():
                            roots.append(path)
                    cache_data = profile / "Cache" / "Cache_Data"
                    if cache_data.exists():
                        roots.append(cache_data)
            return roots

        browser = browser_roots(local / "Google" / "Chrome" / "User Data")
        browser += browser_roots(local / "Microsoft" / "Edge" / "User Data")
        browser += browser_roots(local / "Mozilla" / "Firefox" / "Profiles")

        def app_cache_roots(bases):
            roots = []
            for base in bases:
                if not base.exists():
                    continue
                for pattern in ("*/FileStorage/Cache", "*/Cache", "*/Temp"):
                    roots.extend(path for path in base.glob(pattern) if path.is_dir())
            return roots

        wechat = app_cache_roots([local / "Tencent" / "WeChat", roaming / "Tencent" / "WeChat", local / "Tencent" / "WeChat Files"])
        qq = app_cache_roots([local / "Tencent" / "QQ", roaming / "Tencent" / "QQ"])
        self.targets = [
            {"key": "system", "name": "系统临时文件", "description": "安装、更新和程序运行产生的临时文件", "paths": [Path(tempfile.gettempdir()), windows / "Temp"], "kind": "tree", "default": True, "min_age_seconds": 900},
            {"key": "browser", "name": "浏览器缓存", "description": "Chrome、Edge、Firefox 的缓存和代码缓存", "paths": browser, "kind": "tree", "default": True},
            {"key": "wechat", "name": "微信缓存", "description": "微信图片预览、缓存和临时文件，不包含聊天记录", "paths": wechat, "kind": "tree", "default": False},
            {"key": "qq", "name": "QQ 缓存", "description": "QQ 图片预览和临时缓存，不包含聊天记录", "paths": qq, "kind": "tree", "default": False},
            {"key": "thumbs", "name": "缩略图缓存", "description": "Windows 图片和视频缩略图数据库", "paths": [local / "Microsoft" / "Windows" / "Explorer"], "kind": "glob", "pattern": "thumbcache*.db", "default": True},
            {"key": "reports", "name": "崩溃报告", "description": "Windows 错误报告和应用崩溃转储", "paths": [local / "CrashDumps", local / "Microsoft" / "Windows" / "WER" / "ReportQueue"], "kind": "tree", "default": False, "min_age_seconds": 3600},
            {"key": "updates", "name": "系统更新缓存", "description": "已完成更新留下的下载文件", "paths": [windows / "SoftwareDistribution" / "Download"], "kind": "tree", "default": False, "min_age_seconds": 3600},
            {"key": "recent", "name": "使用痕迹", "description": "最近打开文件记录，不会删除原文件", "paths": [roaming / "Microsoft" / "Windows" / "Recent"], "kind": "tree", "default": False},
            {"key": "recycle", "name": "回收站", "description": "清空系统盘回收站中的项目", "paths": [Path(os.environ.get("SystemDrive", "C:\\")) / "$RECYCLE.BIN"], "kind": "tree", "default": False},
        ]

        self._system_targets = self.targets
        self._system_drive = Path(os.environ.get("SystemDrive", "C:\\"))
        self._drive_entries = self._available_drives()
        self._selected_drive = self._drive_entries[0][0]
        for root, _label in self._drive_entries:
            if str(root).lower().startswith(str(self._system_drive).lower()):
                self._selected_drive = root
                break
        self.targets = self._targets_for_drive(self._selected_drive)

        self.setStyleSheet(
            """
            QFrame#cleanupDrive, QFrame#cleanupCard {
                background: #ffffff;
                border: 1px solid #dfe5ec;
                border-radius: 8px;
            }
            QFrame#cleanupDrive { padding: 2px; }
            QFrame#cleanupCard { min-height: 62px; }
            QFrame#cleanupCard:hover { border-color: #26a269; }
            QComboBox { min-height: 32px; padding: 0 10px; border: 1px solid #cfd8e3; border-radius: 6px; background: #ffffff; }
            QCheckBox { spacing: 8px; font-weight: 600; }
            QLabel#cleanupSize { color: #168653; font-weight: 700; }
            QPushButton#primaryAction { background: #20b875; color: #ffffff; border: 0; border-radius: 8px; font-weight: 700; }
            QPushButton#primaryAction:hover { background: #179962; }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        title = QLabel("空间告急")
        title.setObjectName("contentTitle")
        layout.addWidget(title)
        subtitle = QLabel("扫描清理，释放磁盘空间")
        subtitle.setObjectName("contentStatus")
        layout.addWidget(subtitle)

        drive = QFrame()
        drive.setObjectName("cleanupDrive")
        drive_layout = QVBoxLayout(drive)
        drive_top = QHBoxLayout()
        drive_top.addWidget(QLabel("扫描磁盘"))
        self.drive_combo = QComboBox()
        for root, label in self._drive_entries:
            self.drive_combo.addItem(label, str(root))
        self.drive_combo.currentIndexChanged.connect(self._on_drive_changed)
        drive_top.addWidget(self.drive_combo)
        self.drive_free = QLabel("正在读取磁盘空间...")
        self.drive_free.setObjectName("contentStatus")
        drive_top.addStretch(1)
        drive_top.addWidget(self.drive_free)
        drive_layout.addLayout(drive_top)
        self.drive_progress = QProgressBar()
        self.drive_progress.setTextVisible(False)
        self.drive_progress.setFixedHeight(8)
        drive_layout.addWidget(self.drive_progress)
        layout.addWidget(drive)

        list_header = QHBoxLayout()
        list_header.addWidget(QLabel("可清理项目"))
        self.select_all = QCheckBox("全选")
        self.select_all.toggled.connect(self._toggle_all)
        list_header.addStretch(1)
        list_header.addWidget(self.select_all)
        layout.addLayout(list_header)

        cards = QWidget()
        grid = QGridLayout(cards)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.cards = {}
        for index, target in enumerate(self.targets):
            frame = QFrame()
            frame.setObjectName("cleanupCard")
            card_layout = QVBoxLayout(frame)
            card_layout.setContentsMargins(14, 12, 14, 12)
            top = QHBoxLayout()
            check = QCheckBox(target["name"])
            check.setChecked(target.get("default", False))
            top.addWidget(check)
            top.addStretch(1)
            size = QLabel("未扫描")
            size.setObjectName("cleanupSize")
            top.addWidget(size)
            card_layout.addLayout(top)
            detail = QLabel(target["description"])
            detail.setWordWrap(True)
            detail.setObjectName("contentStatus")
            card_layout.addWidget(detail)
            grid.addWidget(frame, index, 0)
            self.cards[target["key"]] = (check, size, detail)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(cards)
        layout.addWidget(scroll, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        self.status = QLabel("准备扫描")
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.scan_button = QPushButton("扫描")
        self.scan_button.setObjectName("primaryAction")
        self.scan_button.setMinimumHeight(50)
        self.scan_button.clicked.connect(self.scan)
        self.clean_button = QPushButton("一键清理选中")
        self.clean_button.setMinimumHeight(42)
        self.clean_button.clicked.connect(self.clean)
        self.clean_button.setEnabled(False)
        buttons.addWidget(self.scan_button, 1)
        buttons.addWidget(self.clean_button, 1)
        layout.addLayout(buttons)
        self._refresh_drive()
        QTimer.singleShot(200, self.scan)

    @staticmethod
    def _format_size(size):
        if size >= 1024 ** 3:
            return f"{size / 1024 ** 3:.2f} GB"
        if size >= 1024 ** 2:
            return f"{size / 1024 ** 2:.1f} MB"
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"

    def _update_card_metadata(self):
        for target in self.targets:
            card = self.cards.get(target["key"])
            if not card:
                continue
            check, size, detail = card
            check.setText(target["name"])
            check.setChecked(target.get("default", False))
            size.setText("未扫描")
            detail.setText(target["description"])

    def _on_drive_changed(self, index):
        if index < 0:
            return
        if self.worker and self.worker.isRunning():
            return
        self._selected_drive = Path(self.drive_combo.itemData(index))
        self.targets = self._targets_for_drive(self._selected_drive)
        self._update_card_metadata()
        self._refresh_drive()
        self.scan()

    def _toggle_all(self, checked):
        for check, _size, _detail in self.cards.values():
            check.setChecked(checked)

    def _refresh_drive(self):
        try:
            usage = shutil.disk_usage(self._selected_drive)
            percent = int((usage.total - usage.free) * 100 / max(1, usage.total))
            self.drive_progress.setValue(percent)
            self.drive_free.setText(f"可用 {self._format_size(usage.free)} / 共 {self._format_size(usage.total)}")
        except OSError:
            self.drive_free.setText("无法读取磁盘空间")

    def _set_busy(self, busy, message):
        self.scan_button.setEnabled(not busy)
        self.clean_button.setEnabled(not busy and bool(self.rows))
        self.drive_combo.setEnabled(not busy)
        self.status.setText(message)

    def scan(self):
        if self.worker and self.worker.isRunning():
            return
        self.rows = {}
        for check, size, detail in self.cards.values():
            size.setText("扫描中...")
        self._set_busy(True, "正在扫描可清理项目...")
        self.worker = ProDiskCleanupWorker(self.targets, parent=self)
        self.worker.progress.connect(lambda value, message: (self.progress.setValue(value), self.status.setText(message)))
        self.worker.scanned.connect(self._on_scanned)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._release_worker)
        self.worker.start()

    def _on_scanned(self, results):
        self.rows = {result["key"]: result for result in results}
        total = 0
        for target in self.targets:
            result = self.rows.get(target["key"], {"size": 0, "files": 0})
            total += result["size"]
            check, size, detail = self.cards[target["key"]]
            size.setText(self._format_size(result["size"]))
            detail.setText(f"{target['description']} · {result['files']} 个文件")
        self.progress.setValue(100)
        self._set_busy(False, f"扫描完成，可清理 {self._format_size(total)}")

    def clean(self):
        selected = [target for target in self.targets if target["key"] in self.rows and self.cards[target["key"]][0].isChecked()]
        total = sum(self.rows[target["key"]]["size"] for target in selected)
        if not selected or total <= 0:
            QMessageBox.information(self, "磁盘清理", "没有可清理的已选项目。")
            return
        answer = QMessageBox.question(self, "确认清理", f"确定清理已选项目中的 {self._format_size(total)} 吗？\n正在使用的文件会自动跳过。", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self._set_busy(True, "正在清理文件...")
        self.worker = ProDiskCleanupWorker(selected, cleanup=True, parent=self)
        self.worker.progress.connect(lambda value, message: (self.progress.setValue(value), self.status.setText(message)))
        self.worker.completed.connect(self._on_cleaned)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._release_worker)
        self.worker.start()

    def _on_cleaned(self, amount, files):
        self._refresh_drive()
        self._set_busy(False, f"已清理 {files} 个文件，释放 {self._format_size(amount)}")
        QTimer.singleShot(300, self.scan)

    def _on_failed(self, error):
        self._set_busy(False, f"扫描失败：{error}")

    def _release_worker(self):
        self.worker = None


def _load_panels(window):
    # Start the update request before loading the heavier feature panels.
    window._updater = updater.Updater(window)
    about = AboutPanel(window._updater, window)
    window.about_panel = about
    window._updater.check()

    launcher = load_raw("launcher")
    reaction_test = load_raw("reaction_test")
    mythware_panel = load_raw("mythware_panel")
    ai_panel = load_raw("ai_panel")

    aim = launcher.AimTrainerPanel(window)
    window.aim_panel = aim
    window.tab_widget.insertTab(1, aim, "点小球")

    reaction = reaction_test.ReactionTestPanel(window)
    window.tab_widget.insertTab(2, reaction, "反应力测试")

    assistant = mythware_panel.MythwarePanel(window)
    window.assistant_panel = assistant
    window.tab_widget.addTab(assistant, "软件工具箱")

    ai = ai_panel.AIPanel(window)
    window.ai_panel = ai
    window.tab_widget.insertTab(0, ai, "AI 助手")
    window.tab_widget.setCurrentWidget(ai)

    jihao = JihaoPanel(window)
    window.jihao_panel = jihao
    window.tab_widget.addTab(jihao, "嘉豪专区")

    cleanup = ProDiskCleanupPanel(window)
    window.cleanup_panel = cleanup
    window.tab_widget.addTab(cleanup, "磁盘清理")
    window.tab_widget.addTab(about, "关于")

def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Qiyuan.Toolbox")
        except (AttributeError, OSError):
            pass
    app = QApplication(sys.argv)
    if os.environ.get("QIYUAN_ALLOW_RELAUNCH") == "1":
        app._instance_guard = None
    else:
        instance_guard, instance_error = _acquire_instance_guard()
        if instance_guard is None:
            QMessageBox.warning(None, "柒悁工具箱", instance_error)
            return 1
        app._instance_guard = instance_guard
    app.setApplicationName("柒悁工具箱")
    app.setStyle("Fusion")
    icon = resource_path("favicon.ico")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    window = tool.ToolBox()
    window.setWindowTitle("柒悁工具箱")
    window.setStyleSheet(tool.WORKSPACE_STYLE + """
        /* Shared rounded controls for the main workspace. */
        QPushButton {
            min-height: 32px;
            padding: 4px 12px;
            border: 1px solid #cfd8e3;
            border-radius: 8px;
            background: #ffffff;
        }
        QPushButton:hover {
            border-color: #26a269;
            background: #f0fbf5;
        }
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox,
        QSpinBox, QDoubleSpinBox, QListWidget, QTableWidget {
            border: 1px solid #cfd8e3;
            border-radius: 8px;
            background: #ffffff;
            selection-background-color: #dff5e9;
            selection-color: #183326;
        }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
            min-height: 30px;
            padding: 2px 8px;
        }
        QTextEdit, QPlainTextEdit, QListWidget, QTableWidget {
            padding: 4px;
        }
        QTabWidget::pane {
            border: 1px solid #dfe5ec;
            border-radius: 10px;
            background: #ffffff;
            top: -1px;
        }
        QTabBar::tab {
            min-height: 30px;
            padding: 5px 13px;
            border: 1px solid transparent;
            border-radius: 8px 8px 0 0;
        }
        QTabBar::tab:selected {
            color: #16754a;
            background: #e8f7ef;
            border-color: #bde5cf;
        }
        QProgressBar {
            min-height: 12px;
            border: 0;
            border-radius: 6px;
            background: #e8edf2;
            text-align: center;
        }
        QProgressBar::chunk {
            border-radius: 6px;
            background: #20b875;
        }
        QScrollArea {
            border: 0;
            border-radius: 10px;
        }
        QFrame#sidebarFrame {
            margin: 10px 0 10px 10px;
            border: 1px solid #e4e7ec;
            border-radius: 14px;
        }
        QFrame#contentFrame {
            margin: 10px;
            border: 1px solid #e4e7ec;
            border-radius: 14px;
        }
        QFrame#contentHeader {
            border-radius: 14px 14px 0 0;
            padding: 4px 10px;
        }
        QGroupBox {
            border-radius: 12px;
            padding: 14px 12px 12px;
        }
        QListWidget#sidebarNav::item {
            padding: 11px 14px;
            margin: 3px 4px;
            border-radius: 10px;
        }
        QTableWidget {
            border-radius: 10px;
        }
    """)
    for label in window.findChildren(QLabel):
        if label.text().startswith("v1.2"):
            label.setText(f"v{CURRENT_VERSION} · 64 位")
    if icon.exists():
        window.setWindowIcon(QIcon(str(icon)))

    window.show()
    if icon.exists():
        window.setWindowIcon(QIcon(str(icon)))
    QTimer.singleShot(0, lambda: _load_panels(window))
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
