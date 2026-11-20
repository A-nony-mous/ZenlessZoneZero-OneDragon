import contextlib
import shutil
import sys
from pathlib import Path

import yaml

from one_dragon.utils import os_utils
from one_dragon.utils.log_utils import log

READONLY_ASSET_DIRS: tuple[str, ...] = ('template', 'ui', 'text', 'game_data')


def _merge_yaml_missing_keys(bundled_file: Path, user_file: Path) -> None:
    """仅补充用户配置文件中缺失的顶层键，已有的键一律不覆盖。

    用户文件解析失败时直接跳过，不覆盖用户内容。
    """
    try:
        user_content = user_file.read_text(encoding='utf-8')
        user_data = yaml.safe_load(user_content)
    except Exception:
        log.warning('解析用户配置文件失败，跳过缺键合并: %s', user_file, exc_info=True)
        return

    if not isinstance(user_data, dict):
        return

    try:
        bundled_data = yaml.safe_load(bundled_file.read_text(encoding='utf-8'))
    except Exception:
        log.warning('解析包内默认配置文件失败: %s', bundled_file, exc_info=True)
        return

    if not isinstance(bundled_data, dict):
        return

    missing_keys = [k for k in bundled_data if k not in user_data]
    if not missing_keys:
        return

    missing_dict = {k: bundled_data[k] for k in missing_keys}
    dumped = yaml.safe_dump(missing_dict, allow_unicode=True, sort_keys=False)

    if user_content and not user_content.endswith('\n'):
        user_content += '\n'
    user_content += '\n# 以下为版本升级自动补齐的新增默认配置项\n' + dumped
    user_file.write_text(user_content, encoding='utf-8')


def ensure_work_dir_ready() -> None:
    """冻结环境首次启动与升级后资源初始化与配置补齐。

    四类只读目录（assets/template、assets/ui、assets/text、assets/game_data）升级时由包内版本整体覆盖，请勿手工修改。
    仅在冻结环境运行时生效：
    1. 确保工作目录下的 config、assets、custom、.log 基础目录存在；
    2. config 目录仅补充缺失的配置文件和已有配置中缺失的顶层键，不覆盖用户已修改的配置；
    3. assets 下的四类只读资源（template、ui、text、game_data）在版本变化时整体覆盖；
    4. 版本标记写入根目录的 .bundle_seed_version。
    5. 整体出错只记录日志，不向外抛出异常，也不写入 .bundle_seed_version 以便下次启动重试。
    """
    if not (os_utils.run_in_exe() or getattr(sys, 'frozen', False)):
        return

    try:
        _ensure_work_dir_ready_impl()
    except Exception:
        log.error('工作目录资源初始化与配置补齐失败，下次启动将重试', exc_info=True)


def _ensure_work_dir_ready_impl() -> None:
    work_dir = Path(os_utils.get_work_dir())
    for dir_name in ('config', 'assets', 'custom', '.log'):
        (work_dir / dir_name).mkdir(parents=True, exist_ok=True)

    bundle_dir = os_utils.get_bundle_dir()
    if bundle_dir is None or not bundle_dir.exists():
        return

    resources_dir = bundle_dir / 'resources'
    if not resources_dir.exists():
        resources_dir = bundle_dir

    has_error = False

    # 补齐 config 缺失文件及缺失的顶层键
    bundled_config = resources_dir / 'config'
    if bundled_config.exists():
        for item in bundled_config.rglob('*'):
            if item.is_file():
                try:
                    rel_path = item.relative_to(bundled_config)
                    target_file = work_dir / 'config' / rel_path
                    if not target_file.exists():
                        target_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, target_file)
                    elif target_file.suffix in ('.yml', '.yaml'):
                        _merge_yaml_missing_keys(item, target_file)
                except Exception:
                    has_error = True
                    log.warning('处理配置文件失败: %s', item, exc_info=True)

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
            try:
                src_dir = resources_dir / 'assets' / name
                if not src_dir.exists():
                    src_dir = resources_dir / name
                if not src_dir.exists():
                    continue

                target_dir = work_dir / 'assets' / name
                target_new = work_dir / 'assets' / f'{name}.new'
                if target_new.exists():
                    shutil.rmtree(target_new, ignore_errors=True)

                shutil.copytree(src_dir, target_new)

                if target_dir.exists():
                    target_old = work_dir / 'assets' / f'{name}.old'
                    if target_old.exists():
                        shutil.rmtree(target_old, ignore_errors=True)
                    with contextlib.suppress(Exception):
                        target_dir.rename(target_old)

                    if not target_dir.exists():
                        target_new.rename(target_dir)
                        shutil.rmtree(target_old, ignore_errors=True)
                    else:
                        target_new.replace(target_dir)
                else:
                    target_new.rename(target_dir)
            except Exception:
                has_error = True
                log.error('复制只读资源目录失败: %s', name, exc_info=True)
                if (work_dir / 'assets' / f'{name}.new').exists():
                    shutil.rmtree(work_dir / 'assets' / f'{name}.new', ignore_errors=True)

    if not has_error:
        try:
            seed_version_file.write_text(current_version, encoding='utf-8')
        except Exception:
            log.warning('写入 .bundle_seed_version 失败', exc_info=True)
    else:
        log.warning('资源播种过程中存在错误，未写入 .bundle_seed_version，下次启动将重试')
