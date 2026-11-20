import contextlib
import shutil
import sys
from pathlib import Path

from one_dragon.utils import os_utils
from one_dragon.utils.log_utils import log

READONLY_ASSET_DIRS: tuple[str, ...] = ('template', 'ui', 'text', 'game_data')


def ensure_work_dir_ready() -> None:
    """冻结环境首次启动与升级后资源初始化与配置补齐。

    仅在冻结环境运行时生效：
    1. 确保工作目录下的 config、assets、custom、.log 基础目录存在；
    2. config 目录仅补充缺失的配置文件，不覆盖用户已修改的配置；
    3. assets 下的四类只读资源（template、ui、text、game_data）在版本变化时整体覆盖；
    4. 版本标记写入根目录的 .bundle_seed_version。
    """
    if not (os_utils.run_in_exe() or getattr(sys, 'frozen', False)):
        return

    work_dir = Path(os_utils.get_work_dir())
    for dir_name in ('config', 'assets', 'custom', '.log'):
        (work_dir / dir_name).mkdir(parents=True, exist_ok=True)

    bundle_dir = os_utils.get_bundle_dir()
    if bundle_dir is None or not bundle_dir.exists():
        return

    resources_dir = bundle_dir / 'resources'
    if not resources_dir.exists():
        resources_dir = bundle_dir

    # 补齐 config 缺失文件
    bundled_config = resources_dir / 'config'
    if bundled_config.exists():
        for item in bundled_config.rglob('*'):
            if item.is_file():
                rel_path = item.relative_to(bundled_config)
                target_file = work_dir / 'config' / rel_path
                if not target_file.exists():
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target_file)

    # 确定当前包版本
    current_version: str | None = None
    with contextlib.suppress(Exception):
        exe_parent = Path(sys.executable).resolve().parent
        sq_version_file = exe_parent / 'sq.version'
        if sq_version_file.exists():
            current_version = sq_version_file.read_text(encoding='utf-8').strip()

    if not current_version:
        with contextlib.suppress(Exception):
            from one_dragon.version import __version__

            if __version__ and __version__ != 'v0.0.0':
                current_version = __version__

    if not current_version:
        current_version = 'unknown'

    seed_version_file = work_dir / '.bundle_seed_version'
    last_seed_version: str | None = None
    if seed_version_file.exists():
        with contextlib.suppress(Exception):
            last_seed_version = seed_version_file.read_text(encoding='utf-8').strip()

    version_changed = last_seed_version != current_version
    missing_assets = any(
        not (work_dir / 'assets' / name).exists() for name in READONLY_ASSET_DIRS
    )

    if version_changed or missing_assets:
        for name in READONLY_ASSET_DIRS:
            src_dir = resources_dir / 'assets' / name
            if not src_dir.exists():
                src_dir = resources_dir / name
            if not src_dir.exists():
                continue

            target_dir = work_dir / 'assets' / name
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            shutil.copytree(src_dir, target_dir)

        try:
            seed_version_file.write_text(current_version, encoding='utf-8')
        except Exception:
            log.warning('写入 .bundle_seed_version 失败', exc_info=True)
