# 柒悁工具箱（统一版）

`build` 和 `tool` 目录原来是同一个 PyInstaller 项目的中间产物，入口源码是 `tool.py`。统一版保留原有工具页，并增加“v1.2 助手”和磁盘清理页；助手功能现在由 Python/Win32 直接实现，不依赖 `MythwareToolkit-1.2.1.exe`。`vendor/MythwareToolkit-1.2.1` 保存了最新 C++ 源码、资源和构建工程，发布包会包含源码副本供参考和重新构建。

## 源码

点小球实现位于根目录 `launcher.py`，构建时会编译为 `launcher.raw`。

## 运行

直接运行 `柒悁工具箱.exe`，不要单独移动或删除 `_internal`。工具箱新增“点小球”训练页：可以设置目标大小、训练时长和目标刷新时间，统计命中率、平均反应与最佳反应；“鼠标灵敏度”支持读取、应用和恢复 Windows 系统鼠标速度。

精简版不再携带 699MB 的离线 wheel；其余工具功能不受影响。

## 打包

运行 `打包工具箱.bat`，或执行 `python package_release.py --zip`。输出位于 `release/柒悁工具箱`，其中包含可执行文件、依赖清单和全部离线 wheel；复制整个目录即可在无网络环境中部署。

## 构建最新 C++ 助手

运行 `python build_mythware.py`。项目内置便携 Zig 编译器，不需要修改系统 PATH。源码中的中文窄字符串已按 Windows GBK 代码页重新编码，避免界面乱码。由于原版 `uiAccess=true` 需要作者的数字签名，默认构建使用 `uiAccess=false`，可正常运行但不提供未签名程序的超级置顶能力。

