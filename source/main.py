import marshal
import os
import shutil
import sys
import tempfile
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
from PyQt5.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices

tool = load_raw("tool")


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


CURRENT_VERSION = "1.0.0"
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


def _load_panels(window):
    # Start the update request before loading the heavier feature panels.
    window._updater = updater.Updater(window)
    about = AboutPanel(window._updater, window)
    window.about_panel = about
    window.tab_widget.addTab(about, "关于")
    window._updater.check()

    launcher = load_raw("launcher")
    reaction_test = load_raw("reaction_test")
    library_manager = load_raw("library_manager")
    mythware_panel = load_raw("mythware_panel")
    ai_panel = load_raw("ai_panel")

    aim = launcher.AimTrainerPanel(window)
    window.aim_panel = aim
    window.tab_widget.insertTab(1, aim, "点小球")

    reaction = reaction_test.ReactionTestPanel(window)
    window.tab_widget.insertTab(2, reaction, "反应力测试")

    package_root = resource_path("").resolve()
    libraries = library_manager.LibraryManager(package_root, window)
    window.library_manager = libraries
    window.tab_widget.addTab(libraries, "常用库管理")

    assistant = mythware_panel.MythwarePanel(window)
    window.assistant_panel = assistant
    window.tab_widget.addTab(assistant, "软件工具箱")

    ai = ai_panel.AIPanel(window)
    window.ai_panel = ai
    window.tab_widget.insertTab(0, ai, "AI 助手")
    window.tab_widget.setCurrentWidget(ai)

    cleanup = DiskCleanupPanel(window)
    window.cleanup_panel = cleanup
    window.tab_widget.addTab(cleanup, "磁盘清理")

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("柒悁工具箱")
    app.setStyle("Fusion")
    icon = resource_path("favicon.ico")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    window = tool.ToolBox()
    window.setWindowTitle("柒悁工具箱")
    window.setStyleSheet(tool.WORKSPACE_STYLE)
    for label in window.findChildren(QLabel):
        if label.text().startswith("v1.2"):
            label.setText(f"v{CURRENT_VERSION} · 64 位")
    if icon.exists():
        window.setWindowIcon(QIcon(str(icon)))

    window.show()
    QTimer.singleShot(0, lambda: _load_panels(window))
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
