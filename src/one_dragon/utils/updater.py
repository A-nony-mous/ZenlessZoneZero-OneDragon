from collections.abc import Callable
from pathlib import Path
from typing import Any

from one_dragon.utils import os_utils
from one_dragon.utils.log_utils import log


def is_supported() -> bool:
    """当前环境是否支持 Velopack 更新。"""
    return os_utils.is_velopack_mode()


def get_current_version() -> str:
    """获取当前已安装的 Velopack 包版本。统一委托至 bundle_seed.get_current_package_version。"""
    from one_dragon.utils.bundle_seed import get_current_package_version

    return get_current_package_version()


def init_velopack() -> None:
    """初始化 Velopack 生命周期。必须在应用最早期调用。"""
    if not is_supported():
        return
    try:
        import velopack

        velopack.App().run()
    except Exception:
        log.warning("初始化 Velopack 失败", exc_info=True)


def get_update_source(project_config: Any = None) -> Any:
    """获取更新源。优先读取 update_source_url，否则回退到 GithubSource。"""
    from velopack import GithubSource, HttpSource

    update_source_url: str | None = None
    github_homepage: str | None = None

    if project_config is not None:
        if isinstance(project_config, dict):
            update_source_url = project_config.get("update_source_url")
            github_homepage = project_config.get("github_homepage")
        else:
            update_source_url = getattr(project_config, "update_source_url", None)
            github_homepage = getattr(project_config, "github_homepage", None)

    if not update_source_url:
        try:
            import yaml

            cfg_path = Path(os_utils.get_work_dir()) / "config" / "project.yml"
            if cfg_path.exists():
                data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    update_source_url = data.get("update_source_url")
                    if not github_homepage:
                        github_homepage = data.get("github_homepage")
        except Exception:
            pass

    if update_source_url:
        return HttpSource(update_source_url)

    if not github_homepage:
        github_homepage = (
            "https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon"
        )

    # 判断是否为测试版
    is_beta = True
    try:
        from one_dragon.version import __version__

        is_beta = "-beta" in __version__
    except Exception:
        pass

    return GithubSource(github_homepage, prerelease=is_beta)


def check_for_updates(project_config: Any = None) -> Any | None:
    """检查是否有可用更新。

    Args:
        project_config: 项目配置对象（包含 update_source_url / github_homepage）。

    Returns:
        有更新时返回 UpdateInfo，当前已是最新时返回 None。

    Raises:
        Exception: 检查失败时抛出异常，以便调用方区分“无更新”与“检查失败”。
    """
    if not is_supported():
        return None

    try:
        from velopack import UpdateManager

        source = get_update_source(project_config)
        um = UpdateManager(source)
        return um.check_for_updates()
    except Exception:
        log.warning("检查 Velopack 更新失败", exc_info=True)
        raise


def download_updates(
    update_info: Any,
    callback: Callable[[int], None] | None = None,
    project_config: Any = None,
) -> None:
    """仅下载更新包。

    Args:
        update_info: check_for_updates 返回的更新信息对象。
        callback: 下载进度回调函数，入参为 0-100 的整数百分比。
        project_config: 项目配置对象。
    """
    if not is_supported():
        return

    try:
        from velopack import UpdateManager

        source = get_update_source(project_config)
        um = UpdateManager(source)
        um.download_updates(update_info, progress_callback=callback)
    except Exception:
        log.error("下载 Velopack 更新包失败", exc_info=True)
        raise


def apply_updates(
    update_info: Any,
    restart: bool = True,
    project_config: Any = None,
) -> None:
    """应用已下载的更新包（退出当前进程后生效）。

    Args:
        update_info: check_for_updates 返回的更新信息对象。
        restart: 更新完成后是否重启应用。
        project_config: 项目配置对象。
    """
    if not is_supported():
        return

    try:
        from velopack import UpdateManager

        source = get_update_source(project_config)
        um = UpdateManager(source)
        um.wait_exit_then_apply_updates(update_info, restart=restart)
    except Exception:
        log.error("应用 Velopack 更新失败", exc_info=True)
        raise


def download_and_apply(
    update_info: Any,
    callback: Callable[[int], None] | None = None,
    restart: bool = True,
    project_config: Any = None,
) -> None:
    """下载并应用更新。

    Args:
        update_info: check_for_updates 返回的更新信息对象。
        callback: 下载进度回调函数，入参为 0-100 的整数百分比。
        restart: 更新完成后是否重启应用。
        project_config: 项目配置对象。
    """
    download_updates(update_info, callback=callback, project_config=project_config)
    apply_updates(update_info, restart=restart, project_config=project_config)
