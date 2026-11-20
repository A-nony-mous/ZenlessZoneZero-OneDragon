import contextlib
import ctypes
import sys
import traceback
import webbrowser
from pathlib import Path

# 资源播种、更新生命周期与日志基础能力，必须在主应用与 GUI 模块导入前解耦准备就绪
from one_dragon.utils import bundle_seed, os_utils
from one_dragon.utils.bundle_seed import ensure_work_dir_ready, get_seed_status_text
from one_dragon.utils.log_utils import log
from one_dragon.utils.updater import init_velopack

_init_error: str | None = None
stack_trace: str = ""

try:
    from PySide6.QtCore import Qt, QThread, QTimer, Signal
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QApplication
    from qfluentwidgets import (
        InfoBar,
        InfoBarPosition,
        NavigationItemPosition,
        Theme,
        setTheme,
    )

    from one_dragon.base.operation.one_dragon_context import ContextInstanceEventEnum
    from one_dragon.utils import app_utils
    from one_dragon.utils.i18_utils import gt
    from one_dragon_qt.overlay.overlay_manager import OverlayManager
    from one_dragon_qt.services.styles_manager import OdQtStyleSheet
    from one_dragon_qt.view.context_event_signal import ContextEventSignal
    from one_dragon_qt.windows.main_app_window_base import MainAppWindowBase
    from one_dragon_qt.windows.window import PhosTitleBar
    from zzz_od.context.zzz_context import ZContext


    class CtxInitRunner(QThread):
        finished = Signal()

        def __init__(self, ctx: ZContext, window: MainAppWindowBase, parent=None):
            super().__init__(parent)
            self.ctx = ctx
            self._window = window

        def run(self):
            self.ctx.init()
            self._window.on_ctx_ready()
            self.finished.emit()


    class CheckVersionRunner(QThread):

        get = Signal(tuple)

        def __init__(self, ctx: ZContext, parent=None):
            super().__init__(parent)
            self.ctx = ctx

        def run(self):
            launcher_version = app_utils.get_launcher_version()
            if launcher_version and not launcher_version.startswith('v'):
                launcher_version = f'v{launcher_version}'

            if os_utils.is_velopack_mode():
                code_version = "velopack"
                launch_tag = "发行版"
            else:
                code_version = self.ctx.git_service.get_current_version()
                launch_tag = '集成' if os_utils.run_in_exe() else '源码'

            versions = (launcher_version, code_version, launch_tag)
            self.get.emit(versions)

    # 定义应用程序的主窗口类
    class AppWindow(MainAppWindowBase):
        titleBar: PhosTitleBar

        def __init__(self, ctx: ZContext, parent=None):
            """初始化主窗口类，设置窗口标题和图标"""
            self.ctx: ZContext = ctx

            # 记录应用启动时间
            import time
            self._app_start_time = time.time()

            MainAppWindowBase.__init__(
                self,
                ctx=ctx,
                win_title=(
                    f'{gt(ctx.project_config.project_name)} '
                    f'{ctx.one_dragon_config.current_active_instance.name}'
                ),
                project_config=ctx.project_config,
                app_icon="logo.ico",
                parent=parent,
            )
            self.ctx.listen_event(ContextInstanceEventEnum.instance_active.value, self._on_instance_active_event)
            self._context_event_signal: ContextEventSignal = ContextEventSignal()
            self._context_event_signal.instance_changed.connect(self._on_instance_active_signal)

            self._check_version_runner = CheckVersionRunner(self.ctx)
            self._check_version_runner.get.connect(self._update_version)

            # 延迟发送应用启动事件，等待窗口完全显示
            self._launch_timer = QTimer()
            self._launch_timer.setSingleShot(True)
            self._launch_timer.timeout.connect(self._after_app_launch)
            self._launch_timer.start(2000)  # 2秒后发送，确保UI完全渲染

            self.overlay_manager = OverlayManager.create(self.ctx, parent=self)
            if self.overlay_manager is not None:
                self.overlay_manager.start()

        # 继承初始化函数
        def init_window(self):
            self.resize(1140, 760)  # 3:2比例

            # 初始化位置
            screen = QApplication.primaryScreen()
            geometry = screen.availableGeometry()
            w, h = geometry.width(), geometry.height()
            self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

            # 设置配置ID
            self.setObjectName("PhosWindow")
            self.navigationInterface.setObjectName("NavigationInterface")
            self.stackedWidget.setObjectName("StackedWidget")
            self.titleBar.setObjectName("TitleBar")

            # 布局样式调整
            self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
            self.navigationInterface.setContentsMargins(0, 0, 0, 0)

            # 配置样式
            OdQtStyleSheet.NAVIGATION_INTERFACE.apply(self.navigationInterface)
            OdQtStyleSheet.STACKED_WIDGET.apply(self.stackedWidget)
            OdQtStyleSheet.AREA_WIDGET.apply(self.areaWidget)
            OdQtStyleSheet.TITLE_BAR.apply(self.titleBar)

        def create_sub_interface(self):
            """创建和添加各个子界面"""
            super().create_sub_interface()

            # 主页
            from zzz_od.gui.view.home.home_interface import HomeInterface
            self.home_interface = HomeInterface(self.ctx, parent=self)
            self.add_sub_interface(self.home_interface)

            # 游戏助手
            from zzz_od.gui.view.game_assistant.game_assistant_interface import (
                GameAssistantInterface,
            )
            self.add_sub_interface(GameAssistantInterface(self.ctx, parent=self))

            # 一条龙
            from zzz_od.gui.view.one_dragon.zzz_one_dragon_interface import (
                ZOneDragonInterface,
            )
            self.add_sub_interface(ZOneDragonInterface(self.ctx, parent=self))

            # 应用运行
            from zzz_od.gui.view.standalone.zzz_standalone_app_interface import (
                ZStandaloneAppInterface,
            )
            self.add_sub_interface(ZStandaloneAppInterface(self.ctx, parent=self))

            # 画中画
            from one_dragon_qt.widgets.pip_button import PipButton
            self.pip_btn = PipButton(self.ctx, parent=self)
            self.add_nav_widget(self.pip_btn)

            # 点赞
            from one_dragon_qt.view.like_interface import LikeInterface
            self.add_sub_interface(
                LikeInterface(self.ctx, parent=self),
                position=NavigationItemPosition.BOTTOM,
            )

            # 开发工具
            from zzz_od.gui.view.devtools.app_devtools_interface import (
                AppDevtoolsInterface,
            )
            self.devtools_interface = AppDevtoolsInterface(self.ctx, parent=self)
            self.add_sub_interface(
                self.devtools_interface,
                position=NavigationItemPosition.BOTTOM,
            )

            # 插件总入口，紧挨在资源管理上面
            from one_dragon_qt.view.plugin.plugin_interface import (
                PluginInterface,
            )
            self.plugin_interface = PluginInterface(self.ctx, parent=self)
            self.add_sub_interface(
                self.plugin_interface,
                position=NavigationItemPosition.BOTTOM,
            )

            # 资源管理
            from one_dragon_qt.view.resource_manager_interface import (
                ResourceManagerInterface,
            )
            self.add_sub_interface(
                ResourceManagerInterface(
                    self.ctx,
                    self.download_queue,
                    parent=self,
                ),
                position=NavigationItemPosition.BOTTOM,
            )

            # 多账号管理
            from zzz_od.gui.view.accounts.app_accounts_interface import (
                AccountsInterface,
            )
            self.add_sub_interface(
                AccountsInterface(self.ctx, parent=self),
                position=NavigationItemPosition.BOTTOM,
            )

            # 设置
            from zzz_od.gui.view.setting.app_setting_interface import (
                AppSettingInterface,
            )
            self.add_sub_interface(
                AppSettingInterface(self.ctx, parent=self),
                position=NavigationItemPosition.BOTTOM,
            )

            # 连接导航变化信号
            self.stackedWidget.currentChanged.connect(self._on_navigation_changed)

        def _on_navigation_changed(self, index):
            """导航变化时的处理"""
            self._last_stack_idx = index

        def _apply_developer_mode_visibility(self) -> None:
            """刷新绝区零开发工具导航和通用高级控件。"""
            super()._apply_developer_mode_visibility()
            if hasattr(self, 'devtools_interface'):
                nav_widget = self.navigationInterface.widget(
                    self.devtools_interface.objectName()
                )
                if nav_widget is not None:
                    nav_widget.setVisible(self.ctx.env_config.developer_mode)

        def _on_instance_active_event(self, event) -> None:
            """
            切换实例后 更新title 这是context的事件 不能更新UI
            :return:
            """
            self._context_event_signal.instance_changed.emit()

        def _on_instance_active_signal(self) -> None:
            """
            切换实例后 更新title 这是Signal 可以更新UI
            :return:
            """
            project_name = gt(self.ctx.project_config.project_name)
            instance_name = self.ctx.one_dragon_config.current_active_instance.name
            self.setWindowTitle(f'{project_name} {instance_name}')

        def _update_version(self, versions: tuple[str, str, str]) -> None:
            """
            更新版本显示
            @param versions: (启动器版本, 代码版本, 启动器类型tag)
            @return:
            """
            self.titleBar.setLauncherVersion(versions[0])
            self.titleBar.setCodeVersion(versions[1])
            self.titleBar.setLaunchTag(versions[2])

        def _check_first_run(self):
            """首次运行时显示防倒卖弹窗"""
            if self.ctx.env_config.is_first_run:
                from one_dragon_qt.widgets.welcome_dialog import WelcomeDialog
                dialog = WelcomeDialog(self, gt('欢迎使用绝区零一条龙'))
                if dialog.exec():
                    self.ctx.env_config.is_first_run = False

        def _check_bundle_seed_error(self) -> None:
            """启动时若只读资源播种失败，弹一次性警告通知用户。"""
            try:
                from one_dragon.utils import bundle_seed

                if bundle_seed.has_seed_error():
                    failed_dirs = bundle_seed.get_failed_asset_dirs()
                    dir_info = f" ({', '.join(failed_dirs)})" if failed_dirs else ""
                    InfoBar.warning(
                        title=gt('资源更新失败'),
                        content=gt(f'只读资源更新失败{dir_info}，详细报错请查看 .log/ 目录下的日志'),
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP_RIGHT,
                        duration=15000,
                        parent=self,
                    )
                    bundle_seed.clear_seed_error()
            except Exception:
                log.warning('检查只读资源播种状态失败', exc_info=True)

        def _after_app_launch(self):
            """异步处理应用启动后需要处理的事情"""
            self._check_version_runner.start()
            self._check_first_run()
            self._check_bundle_seed_error()
            self.check_resource_updates(force=True)
            self.on_welcome_dialog_closed()

        def closeEvent(self, event: QCloseEvent) -> None:
            """窗口关闭事件"""
            super().closeEvent(event)
            if not event.isAccepted():
                return
            if hasattr(self, 'plugin_interface') and self.plugin_interface is not None:
                self.plugin_interface.shutdown()
            if hasattr(self, 'pip_btn') and self.pip_btn:
                self.pip_btn.dispose()

            if hasattr(self, "overlay_manager") and self.overlay_manager is not None:
                self.overlay_manager.shutdown()

except Exception:
    stack_trace = traceback.format_exc()
    _init_error = f"启动一条龙失败，报错信息如下:\n{stack_trace}"


def _record_startup_error(stack_trace_str: str, seed_status_str: str) -> None:
    """在模块导入失败路径上记录详细诊断日志到 .log/。

    记录播种执行状态、结果、失败目录以及导入异常堆栈。
    若日志模块本身不可用，退一步写到 .log/startup_error.txt 纯文本文件。
    """
    try:
        failed_dirs = bundle_seed.get_failed_asset_dirs()
    except Exception:
        failed_dirs = []

    failed_dirs_str = ", ".join(failed_dirs) if failed_dirs else "无"

    log_content = (
        f"应用启动失败（模块导入异常）\n"
        f"资源播种状态: {seed_status_str}\n"
        f"失败资源目录: {failed_dirs_str}\n"
        f"导入异常堆栈:\n{stack_trace_str}"
    )

    logged = False
    try:
        if log is not None:
            log.error("%s", log_content)
            for handler in getattr(log, 'handlers', []):
                with contextlib.suppress(Exception):
                    handler.flush()
            logged = True
    except Exception:
        logged = False

    if not logged:
        try:
            try:
                work_dir = Path(os_utils.get_work_dir())
            except Exception:
                work_dir = Path.cwd()
            log_dir = work_dir / ".log"
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "startup_error.txt").write_text(log_content + "\n", encoding="utf-8")
        except Exception:
            with contextlib.suppress(Exception):
                Path("startup_error.txt").write_text(log_content + "\n", encoding="utf-8")


# 初始化应用程序，并启动主窗口
def main() -> None:
    # 无论模块导入是否失败，生命周期初始化与资源播种均优先执行且绝不向外抛出未捕获异常
    with contextlib.suppress(Exception):
        init_velopack()

    with contextlib.suppress(Exception):
        ensure_work_dir_ready()

    if _init_error is not None:
        seed_status = get_seed_status_text()
        _record_startup_error(stack_trace, seed_status)

        # 显示错误弹窗，正文追加播种状态，并询问用户是否打开排障文档
        error_message = (
            f"启动一条龙失败,报错信息如下:\n{stack_trace}\n\n"
            f"{seed_status}\n\n"
            f"是否打开排障文档查看解决方案?"
        )
        # MB_ICONERROR | MB_OKCANCEL = 0x10 | 0x01 = 0x11
        # 返回值: IDOK = 1, IDCANCEL = 2
        try:
            result = ctypes.windll.user32.MessageBoxW(0, error_message, "错误", 0x11)
        except Exception:
            result = 2

        # 如果用户点击确定，则打开排障文档
        if result == 1:  # IDOK
            with contextlib.suppress(Exception):
                webbrowser.open("https://docs.qq.com/doc/p/7add96a4600d363b75d2df83bb2635a7c6a969b5")

        sys.exit(1)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings)

    _ctx = ZContext()

    # 设置主题
    setTheme(Theme[_ctx.custom_config.theme.upper()])

    # 创建并显示主窗口
    w = AppWindow(_ctx)

    w.show()
    w.activateWindow()

    # 加载配置
    init_runner = CtxInitRunner(_ctx, w)
    init_runner.start()

    # 启动应用程序事件循环
    quit_code = app.exec()

    _ctx.after_app_shutdown()

    sys.exit(quit_code)


if __name__ == "__main__":
    main()
