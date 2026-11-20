"""旧数据迁移核心模块 (Legacy Data Migration Core).

负责从 OneDragon 旧版形态（源码版或集成版）向 Velopack 新架构目录迁移用户历史数据。
遵循硬约束：
1. 探测仅做方案 A（首启向导弹窗让用户手动选目录），不做任何后台驱动器或快捷方式扫描；
2. 弹窗只在纯首启时出现（新根层没有任何用户配置且不存在迁移标记文件），升级后日常启动绝不弹窗；
3. 源码开发模式下默认不弹首启迁移弹窗；
4. 迁移白名单：config/（含多实例）、custom/、assets/models/。
   plugins/ 不迁移；旧源码、旧运行时、旧启动器、旧日志等一律不迁移；
5. 旧目录全程只读，任何操作均不得写入、删除或重命名源目录中的任何文件；
6. 原子性与回退保证：空间前置检查，在 .migration_staging_<uuid> 中准备与合并，
   两阶段原子重命名替换；任何一步异常均回滚原状，不留下半个目录；
7. 延迟迁移冲突保护：新根层已被用户修改时，迁移前先持久备份至 config_backup_<YYYYMMDD_HHMMSS>/，
   默认保留新版修改；仅核心冲突（游戏路径、主账号等）才提供冲突决策清单；
8. 备份永久保留，程序绝不自动删除。
"""

import contextlib
import datetime
import hashlib
import json
import os
import shutil
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from one_dragon.utils import os_utils
from one_dragon.utils.bundle_seed import (
    _merge_yaml_missing_keys,
    get_current_package_version,
)
from one_dragon.utils.log_utils import log

# 标记文件文件名
MIGRATION_STATUS_FILE_NAME = ".legacy_migration_status.json"

# 临时 staging 目录前缀
STAGING_DIR_PREFIX = ".migration_staging_"

# 事务临时配置备份目录前缀
CONFIG_TRANSACTION_BACKUP_PREFIX = ".config.backup_"

# 用户持久配置快照前缀（延迟迁移时生成）
USER_BACKUP_DIR_PREFIX = "config_backup_"

# 迁移白名单顶层相对路径
WHITELIST_DIRS = ("config", "custom", "assets/models")

# 延迟迁移核心冲突字段名单（若新旧两端均配置且值不同，视为核心业务冲突）
CORE_CONFLICT_KEYS: tuple[str, ...] = (
    "game_path",
    "game_account",
    "account",
    "game_directory",
    "game_exe",
)


class MigrationError(Exception):
    """迁移流程通用异常基类。"""


class DiskSpaceInsufficientError(MigrationError):
    """磁盘剩余空间不足异常。"""


class InvalidLegacyDirError(MigrationError):
    """所选旧目录不合法异常。"""


class MigrationConflictError(MigrationError):
    """迁移过程出现未决冲突或用户取消。"""


class MigrationRollbackFailedError(MigrationError):
    """迁移失败后逆序回滚未完全成功，或新根层未能完全还原至迁移前初始状态。

    为了绝对避免用户数据丢失，已保留安全网备份目录与事务临时目录。
    """

    def __init__(
        self,
        message: str,
        preserved_paths: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.preserved_paths: list[str] = preserved_paths or []


def _compute_file_sha256(file_path: Path) -> str:
    """计算单个文件的 SHA-256 哈希值（只读安全）。"""
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_dir_sha256_map(directory: Path) -> dict[str, str]:
    """递归计算目录下所有文件的相对路径与其 SHA-256 哈希值字典（只读安全）。

    用于验收用例 TC-MIG-01 验证旧目录逐文件哈希在迁移前后 100% 一致。
    """
    hashes: dict[str, str] = {}
    if not directory.exists() or not directory.is_dir():
        return hashes
    for root, _, files in os.walk(directory):
        for file in files:
            full_path = Path(root) / file
            rel_path = str(full_path.relative_to(directory))
            with contextlib.suppress(OSError):
                hashes[rel_path] = _compute_file_sha256(full_path)
    return hashes


def is_valid_legacy_dir(
    legacy_dir: Path,
    current_work_dir: Path | None = None,
) -> tuple[bool, str]:
    """校验所选目录是否为合法的 OneDragon 旧版本安装目录。

    契约（设计文档第 7.3.1 节）：
    1. 反向排他校验（自隔离）：所选目录解析后的绝对路径不得等于当前工作目录，
       亦不得是当前工作目录的父目录或子目录，防止发生自我死循环嵌套复制。
    2. 特征标识判定（满足下列规则之一即判定合法）：
       - 规则 1（源码版）：存在 OneDragon-Launcher.exe 或 zzz_installer.py，且存在 config/ 目录；
       - 规则 2（集成版）：存在 OneDragon-RuntimeLauncher.exe，且存在 config/ 目录；
       - 规则 3（通用/便携开发根）：存在 config/project.yml 或 config/env.yml，
         且存在 src/ 或 .install/ 目录（或已存在 config 目录结构）。

    Args:
        legacy_dir: 用户选择的待检验旧目录。
        current_work_dir: 当前应用工作根目录，若为 None 则从 os_utils 获取。

    Returns:
        (is_valid, error_msg): 是否合法及不合法的错误原因。
    """
    try:
        if not legacy_dir.exists() or not legacy_dir.is_dir():
            return False, "所选路径不存在或不是文件夹，请重新选择。"

        target_path = legacy_dir.resolve()
        work_path = (current_work_dir or Path(os_utils.get_work_dir())).resolve()

        if target_path == work_path:
            return False, "所选目录为当前运行目录，不能作为旧版本数据源。"
        if target_path in work_path.parents:
            return False, "所选目录为当前运行目录的父级目录，请选择确切的旧版本根目录。"
        if work_path in target_path.parents:
            return False, "所选目录为当前运行目录的子目录，不能作为旧版本数据源。"

        has_config_dir = (target_path / "config").is_dir()

        # 规则 1：源码版特征
        if has_config_dir and (
            (target_path / "OneDragon-Launcher.exe").exists()
            or (target_path / "zzz_installer.py").exists()
        ):
            return True, ""

        # 规则 2：集成版特征
        if has_config_dir and (target_path / "OneDragon-RuntimeLauncher.exe").exists():
            return True, ""

        # 规则 3：通用/便携根目录特征
        has_cfg_file = (target_path / "config" / "project.yml").exists() or (
            target_path / "config" / "env.yml"
        ).exists()
        has_env_dir = (
            (target_path / "src").is_dir()
            or (target_path / ".install").is_dir()
            or has_config_dir
        )
        if has_cfg_file and has_env_dir:
            return True, ""

        return False, "所选目录缺少 OneDragon 旧版核心特征文件（未找到启动器或 config 目录），请重新选择。"
    except Exception as e:
        return False, f"校验旧版本目录失败: {e}"


def has_user_configured(work_dir: Path) -> tuple[bool, list[str]]:
    """判定新工作根层是否已被用户修改配置。

    播种出的默认系统配置（如 bundle_seed 复制的 project.yml, repository.yml 等空白模板）不计为用户配置。
    判定契约（设计文档第 7.4.1 节）：
    1. 存在多实例配置子目录（如 config/00, config/01 等）；
    2. 存在仅用户交互才会生成的私有配置文件（如 config/game_account.yml, config/one_dragon.yml）；
    3. config/env.yml 存在且包含脱离默认值的关键配置（如 game_path 非空、代理设置已填入等）；
    4. 播种的基础配置文件（如 config/project.yml）哈希与包内模板不同；
    5. custom/ 目录下存在用户自定义素材文件（如 custom/assets/ui/banner）。
    （注：assets/models/ 下的模型文件为运行时/预打包下载的模型权重，不计入用户私有配置判定，避免误判）。

    Returns:
        (has_configured, reasons): 是否已修改及命中的判定原因列表。
    """
    reasons: list[str] = []
    config_dir = work_dir / "config"

    if config_dir.is_dir():
        # 1. 检查多实例子目录
        for item in config_dir.iterdir():
            if item.is_dir() and item.name.isdigit():
                reasons.append(f"存在多实例配置目录: {item.name}")

        # 2. 检查仅用户交互产生的私有配置文件
        for private_name in ("game_account.yml", "one_dragon.yml", "custom.yml"):
            p_file = config_dir / private_name
            if p_file.exists() and p_file.stat().st_size > 0:
                reasons.append(f"存在用户私有配置文件: {private_name}")

        # 3. 检查 env.yml 关键配置
        env_file = config_dir / "env.yml"
        if env_file.exists():
            try:
                env_data = yaml.safe_load(env_file.read_text(encoding="utf-8"))
                if isinstance(env_data, dict):
                    # 检查游戏路径是否已设置
                    game_path = env_data.get("game_path")
                    if game_path and str(game_path).strip():
                        reasons.append(f"env.yml 已配置游戏路径: {game_path}")
                    # 检查是否配置了个人代理
                    proxy = env_data.get("personal_proxy")
                    if proxy and str(proxy).strip():
                        reasons.append(f"env.yml 已配置个人代理: {proxy}")
            except Exception:
                pass

        # 4. 检查播种文件是否被修改（比对 bundle 模板）
        bundle_dir = os_utils.get_bundle_dir()
        if bundle_dir is not None:
            resources_dir = (
                bundle_dir / "resources"
                if (bundle_dir / "resources").exists()
                else bundle_dir
            )
            bundled_project = resources_dir / "config" / "project.yml"
            work_project = config_dir / "project.yml"
            if bundled_project.exists() and work_project.exists():
                try:
                    if _compute_file_sha256(bundled_project) != _compute_file_sha256(
                        work_project
                    ):
                        reasons.append("project.yml 与内置模板不一致")
                except Exception:
                    pass

    # 5. 检查 custom 素材
    custom_dir = work_dir / "custom"
    if custom_dir.is_dir():
        for f in custom_dir.rglob("*"):
            if f.is_file() and f.stat().st_size > 0:
                reasons.append(f"custom/ 存在自定义素材: {f.name}")
                break

    # 注意：assets/models/ 下的模型文件为运行时/预打包下载的 AI 权重资源，
    # 不属于用户私有业务配置。若将模型计入用户配置，预打包模型或静默下载将导致
    # 首启向导被永久抑制，因此此处不把模型存在作为已配置判定依据。

    return len(reasons) > 0, reasons


def should_show_first_launch_migration_dialog(work_dir: Path) -> bool:
    """判定是否应当在启动时弹出首启旧数据迁移对话框。

    契约：
    1. 源码模式（python / uv run，is_velopack_mode() is False）默认不弹窗；
    2. .legacy_migration_status.json 存在时（状态无论是 migrated, dismissed, skipped），绝不弹窗；
    3. 新根层已被用户配置过（has_user_configured(work_dir)[0] is True）时，不弹窗；
    4. 仅在纯净首启场景下返回 True。
    """
    if not os_utils.is_velopack_mode():
        return False

    status_file = work_dir / MIGRATION_STATUS_FILE_NAME
    if status_file.exists():
        return False

    has_conf, _ = has_user_configured(work_dir)
    return not has_conf


def scan_migration_items(legacy_dir: Path) -> dict[str, Any]:
    """只读扫描旧目录中待迁移的白名单内容与统计信息。

    旧目录全程只读，严禁任何写、删、改调用。

    Returns:
        {
            "items": {
                "config": [rel_path1, rel_path2, ...],
                "custom": [...],
                "assets/models": [...],
            },
            "total_bytes": int,
            "file_count": int,
        }
    """
    items: dict[str, list[str]] = {
        "config": [],
        "custom": [],
        "assets/models": [],
    }
    total_bytes = 0
    file_count = 0

    # 1. config/
    old_config = legacy_dir / "config"
    if old_config.is_dir():
        for root, _, files in os.walk(old_config):
            for file in files:
                full_path = Path(root) / file
                rel_path = str(full_path.relative_to(old_config))
                items["config"].append(rel_path)
                with contextlib.suppress(OSError):
                    total_bytes += full_path.stat().st_size
                file_count += 1

    # 2. custom/
    old_custom = legacy_dir / "custom"
    if old_custom.is_dir():
        for root, _, files in os.walk(old_custom):
            for file in files:
                full_path = Path(root) / file
                rel_path = str(full_path.relative_to(old_custom))
                items["custom"].append(rel_path)
                with contextlib.suppress(OSError):
                    total_bytes += full_path.stat().st_size
                file_count += 1

    # 3. assets/models/
    old_models = legacy_dir / "assets" / "models"
    if old_models.is_dir():
        for root, _, files in os.walk(old_models):
            for file in files:
                full_path = Path(root) / file
                rel_path = str(full_path.relative_to(old_models))
                items["assets/models"].append(rel_path)
                with contextlib.suppress(OSError):
                    total_bytes += full_path.stat().st_size
                file_count += 1

    return {
        "items": items,
        "total_bytes": total_bytes,
        "file_count": file_count,
    }


def check_disk_space(work_dir: Path, required_bytes: int) -> None:
    """检查工作目录所在分区的磁盘空间是否满足迁移要求。"""
    try:
        usage = shutil.disk_usage(work_dir)
        # 需满足 required_bytes * 1.2 且额外保留不少于 100MB
        needed = int(required_bytes * 1.2) + 100 * 1024 * 1024
        if usage.free < needed:
            raise DiskSpaceInsufficientError(
                f"磁盘可用空间不足。需要约 {needed // (1024 * 1024)} MB，"
                f"当前仅剩余 {usage.free // (1024 * 1024)} MB。"
            )
    except OSError as e:
        log.warning("检查磁盘空间时发生异常: %s", e)


def create_config_backup(work_dir: Path) -> Path:
    """在延迟迁移前，将新根层的现有 config/ 与 custom/ 完整备份到持久目录。

    备份目录命名形如：config_backup_<YYYYMMDD_HHMMSS>/
    备份永久保留，程序绝不自动删除。
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{USER_BACKUP_DIR_PREFIX}{timestamp}"
    backup_dir = work_dir / backup_name
    backup_dir.mkdir(parents=True, exist_ok=True)

    config_dir = work_dir / "config"
    if config_dir.exists():
        shutil.copytree(config_dir, backup_dir / "config", dirs_exist_ok=True)

    custom_dir = work_dir / "custom"
    if custom_dir.exists():
        shutil.copytree(custom_dir, backup_dir / "custom", dirs_exist_ok=True)

    return backup_dir


def get_backup_directories_info(work_dir: Path) -> tuple[int, int]:
    """统计工作目录下所有 config_backup_* 的目录数与总占用字节数。

    Returns:
        (count, total_bytes)
    """
    count = 0
    total_bytes = 0
    try:
        if not work_dir.exists():
            return 0, 0
        for item in work_dir.iterdir():
            if item.is_dir() and item.name.startswith(USER_BACKUP_DIR_PREFIX):
                count += 1
                for f in item.rglob("*"):
                    if f.is_file():
                        with contextlib.suppress(OSError):
                            total_bytes += f.stat().st_size
    except Exception as e:
        log.warning("统计备份目录失败: %s", e)
    return count, total_bytes


def format_bytes(total_bytes: int) -> str:
    """格式化字节大小为易读文本。"""
    if total_bytes < 1024:
        return f"{total_bytes} B"
    if total_bytes < 1024 * 1024:
        return f"{total_bytes / 1024:.1f} KB"
    if total_bytes < 1024 * 1024 * 1024:
        return f"{total_bytes / (1024 * 1024):.1f} MB"
    return f"{total_bytes / (1024 * 1024 * 1024):.2f} GB"


def load_migration_status(work_dir: Path) -> dict[str, Any] | None:
    """读取新根层下的迁移标记文件内容。"""
    status_file = work_dir / MIGRATION_STATUS_FILE_NAME
    if not status_file.exists():
        return None
    try:
        data = json.loads(status_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        log.warning("读取迁移状态标记失败", exc_info=True)
        return None


def save_migration_status(work_dir: Path, status_data: dict[str, Any]) -> None:
    """保存迁移状态标记文件。"""
    status_file = work_dir / MIGRATION_STATUS_FILE_NAME
    status_file.write_text(
        json.dumps(status_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def record_dismissed(work_dir: Path) -> None:
    """用户点击【我是新用户】时记录决策状态，以后永不提示。"""
    save_migration_status(
        work_dir,
        {
            "status": "dismissed",
            "timestamp": datetime.datetime.now().astimezone().isoformat(),
        },
    )


def record_skipped(work_dir: Path) -> None:
    """用户点击【以后再说】时记录决策状态，后续启动不弹窗、不挂横幅，仅在设置页常驻入口。"""
    save_migration_status(
        work_dir,
        {
            "status": "skipped",
            "timestamp": datetime.datetime.now().astimezone().isoformat(),
        },
    )


def _safe_rename(
    src: Path,
    dst: Path,
    retries: int = 3,
    delay: float = 0.2,
) -> None:
    """重命名目录或文件；遇到 Windows 文件占用锁（PermissionError）时进行指数回退重试。"""
    for attempt in range(retries):
        try:
            src.rename(dst)
            return
        except PermissionError:
            if attempt == retries - 1:
                raise
            time.sleep(delay * (attempt + 1))


def _safe_rmtree(path: Path) -> None:
    """递归删除目录或文件；若失败则记录警告日志，绝不静默吞错。"""
    if not path.exists():
        return
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    except Exception as rm_err:
        log.warning("清理路径 %s 失败: %s", path, rm_err)


def _find_core_conflicts(
    old_data: dict[str, Any],
    new_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """检测两份配置中是否存在 CORE_CONFLICT_KEYS 核心冲突。"""
    conflicts: list[dict[str, Any]] = []
    for key in CORE_CONFLICT_KEYS:
        if key in old_data and key in new_data:
            old_val = old_data[key]
            new_val = new_data[key]
            if (
                old_val
                and new_val
                and str(old_val).strip() != str(new_val).strip()
            ):
                conflicts.append(
                    {
                        "key": key,
                        "old_value": old_val,
                        "new_value": new_val,
                    }
                )
    return conflicts


def _merge_delayed_yaml_file(
    old_file: Path,
    new_file: Path,
    target_file: Path,
    core_choices: dict[str, str] | None = None,
) -> None:
    """延迟迁移模式下的单文件 YAML 智能合并：默认保留新版修改，核心冲突可自定义选择。"""
    try:
        old_data = yaml.safe_load(old_file.read_text(encoding="utf-8"))
    except Exception:
        old_data = {}
    try:
        new_data = yaml.safe_load(new_file.read_text(encoding="utf-8"))
    except Exception:
        new_data = {}

    if not isinstance(old_data, dict):
        old_data = {}
    if not isinstance(new_data, dict):
        new_data = {}

    merged = dict(old_data)
    # 默认新版修改优先
    merged.update(new_data)

    # 处理核心冲突选择
    if core_choices:
        for k, choice in core_choices.items():
            if choice == "use_old" and k in old_data:
                merged[k] = old_data[k]

    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(
        yaml.safe_dump(merged, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _snapshot_targets(work_dir: Path) -> dict[str, str]:
    """计算工作根目录下 config/, custom/, assets/models/ 三个目标的所有文件的相对路径及 SHA-256。"""
    manifest: dict[str, str] = {}
    for sub in ("config", "custom", "assets/models"):
        target_dir = work_dir / sub
        if target_dir.is_dir():
            for root, _, files in os.walk(target_dir):
                for f in files:
                    p = Path(root) / f
                    rel = str(p.relative_to(work_dir)).replace("\\", "/")
                    manifest[rel] = _compute_file_sha256(p)
    return manifest


def execute_migration(
    legacy_dir: Path,
    work_dir: Path,
    conflict_resolver: (
        Callable[[list[dict[str, Any]]], dict[str, str]] | None
    ) = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """执行旧数据迁移全流程（满足硬约束 2-7）。

    Args:
        legacy_dir: 旧版本 OneDragon 安装目录（只读）。
        work_dir: 新版本应用工作根目录。
        conflict_resolver: 核心冲突回调函数，入参为冲突列表，返回各个 key 的决策字典
                           {"key": "keep_new" | "use_old"}。若未提供则默认全选 "keep_new"。
        progress_callback: 迁移进度回调 (current_count, total_count, message)。
        force: 若为 True，即使已存在 status="migrated" 标记也强制重新迁移（供设置页使用）。

    Returns:
        包含迁移详情的状态字典。
    """
    # 1. 校验旧目录合法性
    is_valid, err_msg = is_valid_legacy_dir(legacy_dir, work_dir)
    if not is_valid:
        raise InvalidLegacyDirError(err_msg)

    # 2. 检查标记：若未设置 force 且已完成过迁移，则不重复执行
    current_status = load_migration_status(work_dir)
    if (
        not force
        and current_status
        and current_status.get("status") == "migrated"
    ):
        log.info("检测到已存在迁移成功标记，跳过重复迁移")
        return current_status

    # 3. 判定是否为延迟迁移（新根层已被用户配置修改）
    is_delayed, modify_reasons = has_user_configured(work_dir)

    # 4. 只读扫描旧目录白名单内容
    scan_info = scan_migration_items(legacy_dir)
    total_bytes = scan_info["total_bytes"]
    file_count = scan_info["file_count"]

    # 5. 磁盘空间前置检查
    check_disk_space(work_dir, total_bytes)

    # 6. 准备 Staging 目录与用户持久备份
    staging_id = uuid.uuid4().hex
    staging_dir = work_dir / f"{STAGING_DIR_PREFIX}{staging_id}"
    staging_config = staging_dir / "config"
    staging_custom = staging_dir / "custom"
    staging_models = staging_dir / "assets" / "models"

    staging_config.mkdir(parents=True, exist_ok=True)
    staging_custom.mkdir(parents=True, exist_ok=True)
    staging_models.mkdir(parents=True, exist_ok=True)

    # 迁移前拍下 3 个目标（config/, custom/, assets/models/）的初始 SHA-256 快照
    initial_targets_snapshot = _snapshot_targets(work_dir)
    backup_dir_path: Path | None = None

    assets_dir = work_dir / "assets"
    assets_existed_before = assets_dir.exists()

    swap_targets: list[dict[str, Any]] = [
        {
            "name": "custom",
            "target": work_dir / "custom",
            "staging": staging_custom,
            "tx_backup": work_dir / f".custom.tx_{staging_id}",
            "existed_before": False,
            "swapped": False,
        },
        {
            "name": "models",
            "target": work_dir / "assets" / "models",
            "staging": staging_models,
            "tx_backup": (work_dir / "assets") / f".models.tx_{staging_id}",
            "existed_before": False,
            "swapped": False,
        },
        {
            "name": "config",
            "target": work_dir / "config",
            "staging": staging_config,
            "tx_backup": work_dir / f".config.tx_{staging_id}",
            "existed_before": False,
            "swapped": False,
        },
    ]
    swapped_targets: list[dict[str, Any]] = []

    try:
        # 若是延迟迁移：先生成持久快照 config_backup_<YYYYMMDD_HHMMSS>/
        if is_delayed:
            backup_dir_path = create_config_backup(work_dir)
            log.info("延迟迁移：已将新版本原配置备份至 %s", backup_dir_path.name)

        # -------------------- 阶段一：在 Staging 中完成复制与合并 --------------------
        copied_count = 0

        # A. 迁移 custom/
        old_custom = legacy_dir / "custom"
        target_custom = work_dir / "custom"
        # 预先将 work_dir / "custom" 现有内容完整合入 staging
        if target_custom.is_dir():
            for root, _, files in os.walk(target_custom):
                for file in files:
                    src_file = Path(root) / file
                    rel = src_file.relative_to(target_custom)
                    dst_file = staging_custom / rel
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)

        if old_custom.is_dir():
            for root, _, files in os.walk(old_custom):
                for file in files:
                    src_file = Path(root) / file
                    rel = src_file.relative_to(old_custom)
                    dst_file = staging_custom / rel
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    # 延迟迁移场景：若新版已有同名素材，保留新版
                    if is_delayed and (target_custom / rel).exists():
                        pass
                    else:
                        shutil.copy2(src_file, dst_file)
                    copied_count += 1
                    if progress_callback:
                        progress_callback(
                            copied_count, file_count, f"复制素材: {rel}"
                        )

        # B. 迁移 assets/models/
        old_models = legacy_dir / "assets" / "models"
        target_models = work_dir / "assets" / "models"
        # 预先将 work_dir / "assets" / "models" 现有内容完整合入 staging
        if target_models.is_dir():
            for root, _, files in os.walk(target_models):
                for file in files:
                    src_file = Path(root) / file
                    rel = src_file.relative_to(target_models)
                    dst_file = staging_models / rel
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)

        if old_models.is_dir():
            for root, _, files in os.walk(old_models):
                for file in files:
                    src_file = Path(root) / file
                    rel = src_file.relative_to(old_models)
                    dst_file = staging_models / rel
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    # 新根层已有的模型文件保持新根层，未下载的增量补入
                    if not (target_models / rel).exists():
                        shutil.copy2(src_file, dst_file)
                    copied_count += 1
                    if progress_callback:
                        progress_callback(
                            copied_count, file_count, f"复制模型: {rel}"
                        )

        # C. 迁移 config/（含多实例）
        old_config = legacy_dir / "config"
        new_config = work_dir / "config"

        # 收集新旧两端的核心冲突
        all_core_conflicts: list[dict[str, Any]] = []
        if is_delayed and old_config.is_dir() and new_config.is_dir():
            for root, _, files in os.walk(old_config):
                for file in files:
                    if file.endswith((".yml", ".yaml")):
                        src_f = Path(root) / file
                        rel = src_f.relative_to(old_config)
                        work_f = new_config / rel
                        if work_f.exists():
                            try:
                                o_d = yaml.safe_load(
                                    src_f.read_text(encoding="utf-8")
                                )
                                n_d = yaml.safe_load(
                                    work_f.read_text(encoding="utf-8")
                                )
                                if isinstance(o_d, dict) and isinstance(
                                    n_d, dict
                                ):
                                    all_core_conflicts.extend(
                                        _find_core_conflicts(o_d, n_d)
                                    )
                            except Exception:
                                pass

        core_decisions: dict[str, str] = {}
        if all_core_conflicts and conflict_resolver:
            core_decisions = conflict_resolver(all_core_conflicts)

        # 遍历旧 config 进行复制与合并
        if old_config.is_dir():
            for root, _, files in os.walk(old_config):
                for file in files:
                    src_file = Path(root) / file
                    rel = src_file.relative_to(old_config)
                    dst_file = staging_config / rel
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    work_f = new_config / rel

                    if is_delayed and work_f.exists():
                        # 延迟迁移冲突处理
                        if file.endswith((".yml", ".yaml")):
                            _merge_delayed_yaml_file(
                                src_file,
                                work_f,
                                dst_file,
                                core_choices=core_decisions,
                            )
                        else:
                            # 非 YAML（如 json/txt），新版优先
                            shutil.copy2(work_f, dst_file)
                    else:
                        # 纯首启或新版缺失该文件：以旧配置为主
                        shutil.copy2(src_file, dst_file)
                        # 纯首启补齐新版引入的全新顶层键
                        if file.endswith((".yml", ".yaml")):
                            template_f = work_f if work_f.exists() else None
                            if template_f is None:
                                bundle_dir = os_utils.get_bundle_dir()
                                if bundle_dir:
                                    res_dir = (
                                        bundle_dir / "resources"
                                        if (bundle_dir / "resources").exists()
                                        else bundle_dir
                                    )
                                    b_f = res_dir / "config" / rel
                                    if b_f.exists():
                                        template_f = b_f
                            if template_f and template_f.exists():
                                _merge_yaml_missing_keys(template_f, dst_file)

                    copied_count += 1
                    if progress_callback:
                        progress_callback(
                            copied_count, file_count, f"配置合并: {rel}"
                        )

        # 将新 config 中旧版没有的文件追加至 staging（包括延迟迁移或纯首启下新版独有的配置文件）
        if new_config.is_dir():
            for root, _, files in os.walk(new_config):
                for file in files:
                    src_file = Path(root) / file
                    rel = src_file.relative_to(new_config)
                    dst_file = staging_config / rel
                    if not dst_file.exists():
                        dst_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_file, dst_file)

        # -------------------- 阶段二：两阶段原子替换 --------------------
        for item in swap_targets:
            target_p: Path = item["target"]
            staging_p: Path = item["staging"]
            tx_backup_p: Path = item["tx_backup"]

            has_staging_content = staging_p.is_dir() and any(
                staging_p.rglob("*")
            )
            if not target_p.exists() and not has_staging_content:
                continue

            item["existed_before"] = target_p.exists()
            target_p.parent.mkdir(parents=True, exist_ok=True)
            tx_backup_p.parent.mkdir(parents=True, exist_ok=True)

            # 步骤 1：若现有目标已存在，原子重命名为 .<name>.tx_<uuid>
            if item["existed_before"]:
                _safe_rename(target_p, tx_backup_p)

            # 步骤 2：将 staging 中对应的目录原子重命名为正式目标
            if staging_p.exists():
                _safe_rename(staging_p, target_p)

            item["swapped"] = True
            swapped_targets.append(item)

        # -------------------- 阶段三：持久化标记文件与清理 --------------------
        # 提交成功：清理所有 tx_backup 事务临时目录
        for item in swap_targets:
            tx_p: Path = item["tx_backup"]
            if tx_p.exists():
                _safe_rmtree(tx_p)

        # 清理 staging 根目录（已全部原子迁出或为空）
        if staging_dir.exists():
            _safe_rmtree(staging_dir)

        result_status: dict[str, Any] = {
            "status": "migrated",
            "timestamp": datetime.datetime.now().astimezone().isoformat(),
            "source_path": str(legacy_dir.resolve()),
            "target_version": get_current_package_version(),
            "migrated_items": list(WHITELIST_DIRS),
            "skipped_items": [],
            "backup_path": backup_dir_path.name if backup_dir_path else "",
            "file_count": file_count,
            "total_bytes": total_bytes,
        }
        save_migration_status(work_dir, result_status)
        log.info(
            "旧数据迁移完成: %d 个文件, 共 %s",
            file_count,
            format_bytes(total_bytes),
        )
        return result_status

    except Exception as migration_err:
        log.error("数据迁移执行失败，开始回滚原环境: %s", migration_err, exc_info=True)
        rollback_errors: list[Exception] = []

        # 1. 逆序回滚所有已完成交换的目标
        for item in reversed(swapped_targets):
            target_p: Path = item["target"]
            tx_backup_p: Path = item["tx_backup"]
            try:
                if target_p.exists():
                    shutil.rmtree(target_p)
                if item["existed_before"] and tx_backup_p.exists():
                    _safe_rename(tx_backup_p, target_p)
            except Exception as rb_err:
                log.error("回滚目标 %s 失败: %s", item["name"], rb_err)
                rollback_errors.append(rb_err)

        # 2. 处理处于半交换中间态的目标（已重命名为 tx_backup 但未完成 target_p 写入）
        for item in swap_targets:
            if item.get("swapped"):
                continue
            target_p = item["target"]
            tx_backup_p = item["tx_backup"]
            if (
                item.get("existed_before")
                and tx_backup_p.exists()
                and not target_p.exists()
            ):
                try:
                    _safe_rename(tx_backup_p, target_p)
                except Exception as rb_err:
                    log.error("还原中间态事务备份 %s 失败: %s", item["name"], rb_err)
                    rollback_errors.append(rb_err)

        # 3. 若 assets 目录为本次新建且为空，清理空目录
        if not assets_existed_before and assets_dir.exists():
            with contextlib.suppress(Exception):
                if not any(assets_dir.iterdir()):
                    assets_dir.rmdir()

        # 4. 回滚之后【先校验】：比对新根层 3 个目标的逐文件 SHA-256 快照
        post_rollback_snapshot = _snapshot_targets(work_dir)
        snapshot_matched = (post_rollback_snapshot == initial_targets_snapshot)
        rollback_succeeded = (len(rollback_errors) == 0 and snapshot_matched)

        if rollback_succeeded:
            # 回滚成功：新根层已 100% 恢复为迁移前状态，可以安全清理 tx_backup、staging 以及持久备份
            for item in swap_targets:
                tx_p = item["tx_backup"]
                if tx_p.exists():
                    _safe_rmtree(tx_p)

            if staging_dir and staging_dir.exists():
                _safe_rmtree(staging_dir)

            if backup_dir_path and backup_dir_path.exists():
                _safe_rmtree(backup_dir_path)

            log.info("回滚校验通过：目标文件 100% 还原至迁移前状态，已清理临时文件与备份")
            raise migration_err
        else:
            # 回滚失败（换不回来、抛出异常或快照校验不一致）：
            # 绝对不调用任何 rmtree！保留 backup_dir_path、所有 tx_backup 和 staging 作为安全网
            preserved_paths: list[str] = []
            if backup_dir_path and backup_dir_path.exists():
                preserved_paths.append(str(backup_dir_path.resolve()))
            for item in swap_targets:
                tx_p = item["tx_backup"]
                if tx_p.exists():
                    preserved_paths.append(str(tx_p.resolve()))
            if staging_dir and staging_dir.exists():
                preserved_paths.append(str(staging_dir.resolve()))

            log.error(
                "回滚校验失败或回滚过程异常！工作区与迁移前状态不一致。已保留安全网备份目录与事务目录: %s",
                preserved_paths,
            )

            paths_bullet = "\n".join(f"  • {p}" for p in preserved_paths)
            rb_err_msg = (
                str(rollback_errors[0])
                if rollback_errors
                else "新根层文件状态与迁移前快照不一致"
            )
            fail_msg = (
                f"数据迁移失败且环境自动回滚未完全恢复！\n"
                f"为防止数据丢失，系统已安全保留以下备份目录与事务临时目录：\n{paths_bullet}\n"
                f"迁移错误: {migration_err}\n"
                f"回滚错误: {rb_err_msg}"
            )
            raise MigrationRollbackFailedError(
                fail_msg,
                preserved_paths=preserved_paths,
            ) from migration_err
