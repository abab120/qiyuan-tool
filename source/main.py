import marshal
import sys
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
import PIL  # noqa: F401
import cryptography  # noqa: F401
import psutil  # noqa: F401
import pyautogui  # noqa: F401
import pyzipper  # noqa: F401
import rarfile  # noqa: F401
import requests  # noqa: F401
import updater
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

tool = load_raw("tool")
ai_panel = load_raw("ai_panel")
library_manager = load_raw("library_manager")
mythware_panel = load_raw("mythware_panel")
reaction_test = load_raw("reaction_test")
launcher = load_raw("launcher")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("柒悁工具箱")
    app.setStyle("Fusion")
    icon = resource_path("favicon.ico")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    window = tool.ToolBox()
    window.setStyleSheet(tool.WORKSPACE_STYLE)
    if icon.exists():
        window.setWindowIcon(QIcon(str(icon)))

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
    window.tab_widget.addTab(assistant, "v1.2 助手")

    ai = ai_panel.AIPanel(window)
    window.ai_panel = ai
    window.tab_widget.insertTab(0, ai, "AI 助手")
    window.tab_widget.setCurrentWidget(ai)
    window._updater = updater.Updater(window)
    window._updater.schedule()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
