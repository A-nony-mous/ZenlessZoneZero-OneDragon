"""旧数据迁移交互弹窗 (Legacy Migration Dialogs)."""

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    IndeterminateProgressBar,
    MessageBox,
    MessageBoxBase,
    PrimaryPushButton,
    PushButton,
    SubtitleLabel,
)

from one_dragon.utils import legacy_migration
from one_dragon.utils.i18_utils import gt
from one_dragon.utils.log_utils import log


class FirstLaunchMigrationDialog(MessageBoxBase):
    """首次启动时的旧数据迁移向导弹窗（只做方案 A：手动选目录）。"""

    def __init__(self, work_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.work_dir = work_dir
        self.widget.setMinimumWidth(560)

        # 隐藏默认按钮，采用三个明确的业务按钮
        self.yesButton.hide()
        self.cancelButton.hide()

        self.title_label = SubtitleLabel(gt("旧版本数据迁移"), self)
        self.viewLayout.addWidget(self.title_label)

        content = gt(
            "欢迎使用新版 OneDragon！\n\n"
            "如果您此前曾使用过旧版本（源码版或集成版），可选择旧版本目录以自动继承您的账号配置、个性化素材与 AI 识别模型：\n\n"
            "• 迁移范围：config/（含多实例）、custom/、assets/models/\n"
            "• 安全保障：旧版本目录全程只读，绝不修改、删除或重命名旧目录文件。"
        )
        self.content_label = BodyLabel(content, self)
        self.content_label.setWordWrap(True)
        self.viewLayout.addWidget(self.content_label)

        # 进度指示器（默认隐藏）
        self.progress_bar = IndeterminateProgressBar(self)
        self.progress_bar.setVisible(False)
        self.viewLayout.addWidget(self.progress_bar)

        self.status_label = BodyLabel("", self)
        self.status_label.setVisible(False)
        self.viewLayout.addWidget(self.status_label)

        # 按钮栏：【选择旧版本目录】、【我是新用户】、【以后再说】
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(12)

        self.select_btn = PrimaryPushButton(
            FluentIcon.FOLDER, gt("选择旧版本目录"), self
        )
        self.select_btn.clicked.connect(self._on_select_clicked)
        self.btn_layout.addWidget(self.select_btn)

        self.new_user_btn = PushButton(gt("我是新用户"), self)
        self.new_user_btn.clicked.connect(self._on_new_user_clicked)
        self.btn_layout.addWidget(self.new_user_btn)

        self.skip_btn = PushButton(gt("以后再说"), self)
        self.skip_btn.clicked.connect(self._on_skip_clicked)
        self.btn_layout.addWidget(self.skip_btn)

        self.viewLayout.addLayout(self.btn_layout)

    def _on_new_user_clicked(self) -> None:
        legacy_migration.record_dismissed(self.work_dir)
        self.accept()

    def _on_skip_clicked(self) -> None:
        legacy_migration.record_skipped(self.work_dir)
        self.reject()

    def _on_select_clicked(self) -> None:
        chosen_dir_str = QFileDialog.getExistingDirectory(
            self,
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
            box = MessageBox(gt("目录无效"), gt(err_msg), self)
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
            f"是否立即开始迁移？"
        )
        confirm_box = MessageBox(gt("确认数据迁移"), confirm_text, self)
        if not confirm_box.exec():
            return

        self._start_migration(chosen_dir)

    def _start_migration(self, legacy_dir: Path) -> None:
        self.select_btn.setEnabled(False)
        self.new_user_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.start()
        self.status_label.setVisible(True)
        self.status_label.setText(gt("正在迁移数据，请稍候..."))

        try:
            legacy_migration.execute_migration(
                legacy_dir=legacy_dir,
                work_dir=self.work_dir,
                force=True,
            )
            success_box = MessageBox(
                gt("迁移完成"),
                gt("旧版本数据已成功迁移至新版！即将启动主程序。"),
                self,
            )
            success_box.exec()
            self.accept()
        except legacy_migration.MigrationRollbackFailedError as e:
            log.error("首启迁移失败且回滚未完全恢复", exc_info=True)
            paths_text = (
                "\n".join(f"• {p}" for p in e.preserved_paths)
                if e.preserved_paths
                else "（无保留目录）"
            )
            fail_box = MessageBox(
                gt("迁移失败且自动回滚未完成"),
                gt(
                    f"数据迁移未成功，且环境自动回滚未完全恢复。\n"
                    f"为保障数据安全，系统已为您保留原始备份与事务数据，绝不丢失：\n\n"
                    f"{paths_text}\n\n"
                    f"您可以从上述路径中手动找回配置。"
                ),
                self,
            )
            fail_box.exec()
            self.select_btn.setEnabled(True)
            self.new_user_btn.setEnabled(True)
            self.skip_btn.setEnabled(True)
            self.progress_bar.stop()
            self.progress_bar.setVisible(False)
            self.status_label.setText(gt("迁移未完成，数据已保留在安全备份中。"))
        except Exception as e:
            log.error("首启迁移失败", exc_info=True)
            fail_box = MessageBox(
                gt("迁移未完成"),
                gt(
                    f"数据迁移未成功，已自动恢复环境，未产生残留文件。\n失败原因: {e}"
                ),
                self,
            )
            fail_box.exec()
            self.select_btn.setEnabled(True)
            self.new_user_btn.setEnabled(True)
            self.skip_btn.setEnabled(True)
            self.progress_bar.stop()
            self.progress_bar.setVisible(False)
            self.status_label.setText(gt("迁移失败，可重新选择目录或跳过。"))


class ConflictSelectionDialog(MessageBoxBase):
    """延迟迁移检测到新版已被修改时的冲突提示框。"""

    def __init__(
        self,
        conflicts: list[dict[str, Any]],
        backup_dir_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.widget.setMinimumWidth(560)
        self.yesButton.hide()
        self.cancelButton.hide()
        self.selected_choice: str = "keep_new"

        self.title_label = SubtitleLabel(gt("检测到新版本已有配置"), self)
        self.viewLayout.addWidget(self.title_label)

        conflict_lines = [
            f"• {c.get('key')}: 旧版值 '{c.get('old_value')}' vs 新版值 '{c.get('new_value')}'"
            for c in conflicts
        ]
        conflicts_summary = "\n".join(conflict_lines) if conflict_lines else ""

        text = gt(
            f"您此前在新版本中已产生配置修改。为保障数据安全，系统已将新版现有配置备份至：\n"
            f"{backup_dir_name}\n\n"
            f"核心配置冲突项：\n{conflicts_summary}\n\n"
            f"请选择迁移策略："
        )
        self.content_label = BodyLabel(text, self)
        self.content_label.setWordWrap(True)
        self.viewLayout.addWidget(self.content_label)

        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(12)

        self.keep_new_btn = PrimaryPushButton(gt("保留新版修改（推荐）"), self)
        self.keep_new_btn.clicked.connect(self._choose_keep_new)
        self.btn_layout.addWidget(self.keep_new_btn)

        self.use_old_btn = PushButton(gt("以旧版配置覆盖"), self)
        self.use_old_btn.clicked.connect(self._choose_use_old)
        self.btn_layout.addWidget(self.use_old_btn)

        self.cancel_btn = PushButton(gt("取消"), self)
        self.cancel_btn.clicked.connect(self._choose_cancel)
        self.btn_layout.addWidget(self.cancel_btn)

        self.viewLayout.addLayout(self.btn_layout)

    def _choose_keep_new(self) -> None:
        self.selected_choice = "keep_new"
        self.accept()

    def _choose_use_old(self) -> None:
        self.selected_choice = "use_old"
        self.accept()

    def _choose_cancel(self) -> None:
        self.selected_choice = "cancel"
        self.reject()


def show_first_launch_migration_dialog(work_dir: Path) -> None:
    """显示首启迁移向导弹窗。"""
    try:
        dlg = FirstLaunchMigrationDialog(work_dir)
        dlg.exec()
    except Exception:
        log.error("显示首启迁移对话框异常", exc_info=True)
