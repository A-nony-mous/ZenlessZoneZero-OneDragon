"""旧版本数据迁移设置卡片组件 (Legacy Migration Setting Card)."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QWidget
from qfluentwidgets import (
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    PushButton,
)

from one_dragon.utils import legacy_migration, os_utils
from one_dragon.utils.i18_utils import gt
from one_dragon.utils.log_utils import log
from one_dragon_qt.dialogs.legacy_migration_dialog import (
    ConflictSelectionDialog,
)
from one_dragon_qt.widgets.setting_card.setting_card_base import SettingCardBase


class LegacyMigrationCard(SettingCardBase):
    """设置页旧版本数据迁移卡片。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            icon=FluentIcon.HISTORY,
            title=gt("旧版本数据迁移"),
            content="",
            parent=parent,
        )
        self.work_dir = Path(os_utils.get_work_dir())

        # 按钮容器
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(12)

        self.import_btn = PushButton(gt("从旧版本导入数据"), self)
        self.import_btn.clicked.connect(self._on_import_clicked)
        self.btn_layout.addWidget(
            self.import_btn, 0, Qt.AlignmentFlag.AlignRight
        )

        self.open_dir_btn = PushButton(gt("打开所在目录"), self)
        self.open_dir_btn.clicked.connect(self._on_open_dir_clicked)
        self.btn_layout.addWidget(
            self.open_dir_btn, 0, Qt.AlignmentFlag.AlignRight
        )

        self.btn_layout.addSpacing(16)
        self.hBoxLayout.addLayout(self.btn_layout, 0)

        self.refresh_display()

    def refresh_display(self) -> None:
        """刷新卡片展示的迁移状态、备份信息与说明。"""
        # 1. 状态行
        status_info = legacy_migration.load_migration_status(self.work_dir)
        if status_info is None:
            status_text = gt("当前状态：未迁移")
        else:
            st = status_info.get("status")
            if st == "migrated":
                time_str = status_info.get("timestamp", "")
                src_path = status_info.get("source_path", "")
                status_text = gt(
                    f"当前状态：已迁移（来源：{src_path}，时间：{time_str}）"
                )
            elif st == "dismissed":
                status_text = gt("当前状态：已跳过（新用户）")
            elif st == "skipped":
                status_text = gt("当前状态：已跳过")
            else:
                status_text = gt(f"当前状态：{st}")

        # 2. 备份目录行
        backup_count, total_bytes = (
            legacy_migration.get_backup_directories_info(self.work_dir)
        )
        backup_size_str = legacy_migration.format_bytes(total_bytes)
        backup_text = gt(
            f"历史配置备份：{backup_count} 个目录，共占用 {backup_size_str}"
        )

        # 3. 插件不迁移说明行
        plugin_text = gt(
            "说明：第三方插件（plugins/）不迁移，请通过插件管理重新安装。"
        )

        full_content = f"{status_text}\n{backup_text}\n{plugin_text}"
        self.setContent(full_content)

    def _on_open_dir_clicked(self) -> None:
        """打开工作目录或最新备份目录。"""
        try:
            target_path = self.work_dir
            if not target_path.exists():
                return
            if sys.platform == "win32":
                os.startfile(str(target_path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target_path)])
            else:
                subprocess.Popen(["xdg-open", str(target_path)])
        except Exception:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.work_dir)))

    def _on_import_clicked(self) -> None:
        """点击从旧版本导入数据。"""
        chosen_dir_str = QFileDialog.getExistingDirectory(
            self.window(),
            gt("选择旧版本 OneDragon 根目录"),
            "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if not chosen_dir_str:
            return

        chosen_dir = Path(chosen_dir_str)
        is_valid, err_msg = legacy_migration.is_valid_legacy_dir(
            chosen_dir, self.work_dir
        )
        if not is_valid:
            box = MessageBox(gt("目录无效"), gt(err_msg), self.window())
            box.exec()
            return

        scan_res = legacy_migration.scan_migration_items(chosen_dir)
        file_count = scan_res["file_count"]
        size_str = legacy_migration.format_bytes(scan_res["total_bytes"])

        confirm_text = gt(
            f"已识别到旧版本数据：\n"
            f"• 路径：{chosen_dir}\n"
            f"• 待迁移文件数：{file_count} 个\n"
            f"• 数据总体积：{size_str}\n\n"
            f"安全承诺：旧目录全程只读，绝不修改、删除或重命名旧目录文件。\n"
            f"迁移前将自动为新根层配置生成持久备份。\n"
            f"是否立即开始迁移？"
        )
        confirm_box = MessageBox(
            gt("确认数据迁移"), confirm_text, self.window()
        )
        if not confirm_box.exec():
            return

        def _conflict_resolver(
            conflicts: list[dict[str, Any]],
        ) -> dict[str, str]:
            # 获取实际生成的最新备份目录名称，避免给用户展示通配符
            backup_name = "config_backup"
            backups = [
                d.name
                for d in self.work_dir.iterdir()
                if d.is_dir()
                and d.name.startswith(legacy_migration.USER_BACKUP_DIR_PREFIX)
            ]
            if backups:
                backup_name = sorted(backups)[-1]

            dlg = ConflictSelectionDialog(
                conflicts=conflicts,
                backup_dir_name=backup_name,
                parent=self.window(),
            )
            dlg.exec()
            choice = dlg.selected_choice
            return {c["key"]: choice for c in conflicts}

        try:
            legacy_migration.execute_migration(
                legacy_dir=chosen_dir,
                work_dir=self.work_dir,
                conflict_resolver=_conflict_resolver,
                force=True,
            )
            self.refresh_display()
            InfoBar.success(
                title=gt("迁移成功"),
                content=gt("旧数据已成功导入并合并到当前版本"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self.window(),
            )
        except Exception as e:
            log.error("手动导入旧数据失败", exc_info=True)
            fail_box = MessageBox(
                gt("迁移未完成"),
                gt(f"数据迁移未成功，已自动恢复环境。\n失败原因: {e}"),
                self.window(),
            )
            fail_box.exec()
            self.refresh_display()
