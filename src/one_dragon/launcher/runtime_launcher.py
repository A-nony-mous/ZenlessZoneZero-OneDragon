import ctypes
import sys
import traceback

from one_dragon.launcher.exe_launcher import ExeLauncher


class RuntimeLauncher(ExeLauncher):
    """集成启动器基类

    将 Python 运行时嵌入到应用目录中的启动器。
    提供控制台隐藏等通用功能。
    """

    def __init__(self, description: str, version: str) -> None:
        ExeLauncher.__init__(self, description, version)

    @staticmethod
    def _hide_console() -> None:
        """隐藏控制台窗口，用于 GUI 模式"""
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE

    @staticmethod
    def _show_fatal_error(error_info: str) -> None:
        """显示致命错误对话框并退出"""
        ctypes.windll.user32.MessageBoxW(
            None,
            f"启动失败，报错信息如下:\n{error_info}",
            "OneDragon 集成启动器",
            0x10,  # MB_ICONERROR
        )
        sys.exit(1)

    def run_onedragon_mode(self, launch_args: list[str]) -> None:
        try:
            self._do_run_onedragon(launch_args)
        except Exception:
            self._show_fatal_error(traceback.format_exc())

    def run_gui_mode(self) -> None:
        try:
            self._hide_console()
            self._do_run_gui()
        except Exception:
            self._show_fatal_error(traceback.format_exc())

    def _do_run_onedragon(self, launch_args: list[str]) -> None:
        """运行一条龙模式，子类实现"""
        pass

    def _do_run_gui(self) -> None:
        """运行GUI模式，子类实现"""
        pass
