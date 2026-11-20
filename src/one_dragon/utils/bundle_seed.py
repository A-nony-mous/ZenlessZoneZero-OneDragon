import contextlib
import json
import re
import shutil
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from one_dragon.utils import os_utils
from one_dragon.utils.log_utils import log

READONLY_ASSET_DIRS: tuple[str, ...] = ('template', 'ui', 'text', 'game_data')

_seed_executed: bool = False
_seed_error: bool = False
_failed_asset_dirs: list[str] = []


def is_seed_executed() -> bool:
    """本次运行是否执行过资源播种（仅在冻结环境下执行）。"""
    return _seed_executed


def has_seed_error() -> bool:
    """是否存在只读资源播种失败。"""
    return _seed_error


def get_failed_asset_dirs() -> list[str]:
    """获取本次启动播种失败的只读资源目录列表。"""
    return list(_failed_asset_dirs)


def clear_seed_error() -> None:
    """清除播种失败标记（供 UI 弹窗处理完毕后重置）。"""
    global _seed_error, _failed_asset_dirs, _seed_executed
    _seed_error = False
    _failed_asset_dirs = []
    _seed_executed = False


def get_seed_status_text() -> str:
    """获取资源播种状态描述文本，供错误弹窗与日志使用。"""
    if has_seed_error():
        failed_dirs = get_failed_asset_dirs()
        if failed_dirs:
            return f"资源初始化：失败（{', '.join(failed_dirs)}），详见 .log/"
        return "资源初始化：失败，详见 .log/"
    return "资源初始化：成功"


def _merge_yaml_missing_keys(bundled_file: Path, user_file: Path) -> None:
    """仅补充用户配置文件中缺失的顶层键，已有的键一律不覆盖。

    用户文件解析失败时直接跳过，不覆盖用户内容。
    """
    try:
        import yaml
    except Exception:
        log.warning('缺少 yaml 模块，跳过配置文件合并: %s', user_file, exc_info=True)
        return
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


def _cleanup_stale_temp_assets(work_dir: Path) -> None:
    """清理 assets/ 下本机制自己产生的 .new / .old 残留目录，不碰其他目录。"""
    assets_dir = work_dir / 'assets'
    if not assets_dir.exists():
        return
    try:
        for item in assets_dir.iterdir():
            if not item.is_dir():
                continue
            name = item.name
            is_stale_temp = any(
                name == f'{d}.new'
                or name == f'{d}.old'
                or name.startswith(f'.{d}.new')
                or name.startswith(f'.{d}.old')
                or name.startswith(f'{d}.new-')
                or name.startswith(f'{d}.old-')
                for d in READONLY_ASSET_DIRS
            )
            if is_stale_temp:
                shutil.rmtree(item, ignore_errors=True)
    except Exception:
        log.warning('清理临时资源目录残留失败', exc_info=True)


def _load_asset_seed_status(work_dir: Path, last_seed_version: str | None) -> dict[str, str]:
    """读取每个只读资源目录的播种版本记录。"""
    status_file = work_dir / '.bundle_seed_status.json'
    status: dict[str, str] = {}
    if status_file.exists():
        try:
            data = json.loads(status_file.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                status = {str(k): str(v) for k, v in data.items()}
        except Exception:
            log.warning('读取 .bundle_seed_status.json 失败', exc_info=True)
    elif last_seed_version:
        # 兼容旧版本：若 .bundle_seed_version 存在且目录齐全，视同已对该版本完成播种
        for name in READONLY_ASSET_DIRS:
            if (work_dir / 'assets' / name).exists():
                status[name] = last_seed_version
    return status


def _save_asset_seed_status(work_dir: Path, status: dict[str, str]) -> None:
    """持久化保存每个只读资源目录的播种版本记录。"""
    status_file = work_dir / '.bundle_seed_status.json'
    try:
        status_file.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        log.warning('写入 .bundle_seed_status.json 失败', exc_info=True)


def parse_nuspec_version(xml_text: str) -> str | None:
    """从 nuspec XML 内容中解析 <version> 节点文本。

    优先使用 xml.etree.ElementTree，兼容任意命名空间；
    XML 解析失败时使用稳妥的正则兜底。解析失败返回 None。
    """
    if not xml_text:
        return None
    try:
        root = ET.fromstring(xml_text)
        v_elem = root.find('.//{*}version')
        if v_elem is not None and v_elem.text:
            text = v_elem.text.strip()
            if text:
                return text
        for elem in root.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag.lower() == 'version' and elem.text:
                text = elem.text.strip()
                if text:
                    return text
    except Exception:
        pass

    try:
        m = re.search(r'<(?:\w+:)?version\b[^>]*>([^<]+)</(?:\w+:)?version>', xml_text, re.IGNORECASE)
        if m:
            text = m.group(1).strip()
            if text:
                return text
    except Exception:
        pass

    return None


def get_current_package_version() -> str:
    """获取当前软件包的纯版本号。

    1. 从 sys.executable 同级或 Velopack 目录下的 sq.version 中解析 <version> 节点；
    2. 若解析失败或不存在，依次回退：
       - updater.get_current_version()
       - one_dragon.version.__version__
       - 'unknown'
    写进标记文件、状态文件及 --version 输出的均为此纯版本号（例如 '0.1.0-beta.1'）。
    """
    # 1. 尝试从 sq.version 解析
    with contextlib.suppress(Exception):
        exe_parent = Path(sys.executable).resolve().parent
        sq_version_file = exe_parent / 'sq.version'
        if not sq_version_file.exists():
            vpk_root = os_utils.get_velopack_root()
            if vpk_root is not None:
                cand = vpk_root / 'current' / 'sq.version'
                if cand.exists():
                    sq_version_file = cand

        if sq_version_file.exists():
            raw_text = sq_version_file.read_text(encoding='utf-8').strip()
            parsed = parse_nuspec_version(raw_text)
            if parsed:
                return parsed
            if raw_text and '<' not in raw_text:
                return raw_text

    # 2. 回退到 updater.get_current_version()
    with contextlib.suppress(Exception):
        from one_dragon.utils import updater

        ver = updater.get_current_version()
        if ver:
            return ver

    # 3. 回退到 one_dragon.version.__version__
    with contextlib.suppress(Exception):
        from one_dragon.version import __version__

        if __version__:
            return __version__.strip()

    # 4. 兜底
    return 'unknown'


def ensure_work_dir_ready() -> None:
    """冻结环境首次启动与升级后资源初始化与配置补齐。

    四类只读目录（assets/template、assets/ui、assets/text、assets/game_data）升级时由包内版本整体覆盖，请勿手工修改。
    仅在冻结环境运行时生效：
    1. 确保工作目录下的 config、assets、custom、.log 基础目录存在；
    2. config 目录仅补充缺失的配置文件和已有配置中缺失的顶层键，不覆盖用户已修改的配置；
       config 的异常只记日志，不阻断资源版本标记，天然在每次启动时幂等重试；
    3. assets 下的四类只读资源（template、ui、text、game_data）在版本变化时通过唯一临时目录（mkdtemp）隔离构建后替换；
       每次播种前自动清理本机制残留的 .new/.old 临时目录；
       按目录在 .bundle_seed_status.json 中记录完成版本，单个资源目录因文件锁等失败时，下次启动仅重试失败的目录；
    4. 四类资源目录全部播种成功后，版本标记写入根目录的 .bundle_seed_version；
    5. 若有资源目录失败，记录失败状态（通过 has_seed_error() 供主窗口弹出一次性告警），下次启动只重试未完成项；
    6. 整体出错只记录日志，不向外抛出未捕获异常。

    老版本兼容说明：
    已有用户的 .bundle_seed_version 和 .bundle_seed_status.json 中可能存有历史的 nuspec XML 全文。
    升级到本版本后，由于 XML 全文与解析出的纯版本号不相等，会触发一次全量重新播种。
    播种完成后以纯版本号覆写标记文件与状态文件，后续启动将命中版本匹配，仅全量重播一次，不会每次启动都重来。
    """
    if not (os_utils.run_in_exe() or getattr(sys, 'frozen', False)):
        return

    global _seed_error, _seed_executed
    _seed_executed = True
    try:
        _ensure_work_dir_ready_impl()
    except Exception:
        _seed_error = True
        log.error('工作目录资源初始化与配置补齐失败，下次启动将重试', exc_info=True)


def _ensure_work_dir_ready_impl() -> None:
    global _seed_error, _failed_asset_dirs
    work_dir = Path(os_utils.get_work_dir())
    for dir_name in ('config', 'assets', 'custom', '.log'):
        (work_dir / dir_name).mkdir(parents=True, exist_ok=True)

    bundle_dir = os_utils.get_bundle_dir()
    if bundle_dir is None or not bundle_dir.exists():
        return

    resources_dir = bundle_dir / 'resources'
    if not resources_dir.exists():
        resources_dir = bundle_dir

    # 1. 补齐 config 缺失文件及缺失的顶层键（独立处理，错误不影响资源播种标记）
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
                    log.warning('处理配置文件失败: %s', item, exc_info=True)

    # 2. 确定当前包版本
    current_version = get_current_package_version()

    seed_version_file = work_dir / '.bundle_seed_version'
    last_seed_version: str | None = None
    if seed_version_file.exists():
        with contextlib.suppress(Exception):
            last_seed_version = seed_version_file.read_text(encoding='utf-8').strip()

    # 3. 播种前先清理本机制自己产生的历史 .new / .old 残留
    _cleanup_stale_temp_assets(work_dir)

    # 4. 按目录记录与比对完成状态（单个资源失败下次只重试失败的目录）
    asset_status = _load_asset_seed_status(work_dir, last_seed_version)
    assets_dir = work_dir / 'assets'
    failed_asset_dirs: list[str] = []

    for name in READONLY_ASSET_DIRS:
        target_dir = assets_dir / name
        need_seed = (asset_status.get(name) != current_version) or (not target_dir.exists())
        if not need_seed:
            continue

        src_dir = resources_dir / 'assets' / name
        if not src_dir.exists():
            src_dir = resources_dir / name
        if not src_dir.exists():
            continue

        target_new: Path | None = None
        unique_id = uuid.uuid4().hex[:8]
        try:
            # 临时目录采用唯一前缀，避免旧残留锁文件导致 copytree 崩溃
            target_new = Path(tempfile.mkdtemp(dir=assets_dir, prefix=f'.{name}.new-{unique_id}-'))
            shutil.copytree(src_dir, target_new, dirs_exist_ok=True)

            if target_dir.exists():
                target_old = assets_dir / f'.{name}.old-{unique_id}'
                if target_old.exists():
                    shutil.rmtree(target_old, ignore_errors=True)

                target_dir.rename(target_old)
                try:
                    target_new.rename(target_dir)
                    shutil.rmtree(target_old, ignore_errors=True)
                except Exception:
                    # 回滚原目录
                    with contextlib.suppress(Exception):
                        target_old.rename(target_dir)
                    raise
            else:
                target_new.rename(target_dir)

            asset_status[name] = current_version
            _save_asset_seed_status(work_dir, asset_status)
        except Exception:
            failed_asset_dirs.append(name)
            log.error('复制只读资源目录失败: %s', name, exc_info=True)
            if target_new is not None and target_new.exists():
                shutil.rmtree(target_new, ignore_errors=True)

    # 5. 校验四类资源是否全部成功播种
    all_assets_ready = all(
        asset_status.get(name) == current_version and (assets_dir / name).exists()
        for name in READONLY_ASSET_DIRS
    )

    if all_assets_ready:
        _seed_error = False
        _failed_asset_dirs = []
        try:
            seed_version_file.write_text(current_version, encoding='utf-8')
        except Exception:
            log.warning('写入 .bundle_seed_version 失败', exc_info=True)
    else:
        _seed_error = True
        _failed_asset_dirs = failed_asset_dirs
        log.warning('只读资源播种未全部完成（未完成目录: %s），未写入 .bundle_seed_version，下次启动将仅重试未完成目录', failed_asset_dirs)
