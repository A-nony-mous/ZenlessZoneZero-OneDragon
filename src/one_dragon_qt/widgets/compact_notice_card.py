# coding:utf-8
"""
紧凑型通知公告卡片组件
作为仪表盘的一部分，不会撑大页面，支持从远程加载Markdown/JSON内容
"""
import json
import os
import time
import requests
import re
from dataclasses import dataclass, field
from typing import List, Optional
from PySide6.QtCore import Qt, QSize, Signal, QThread, QRectF, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPainterPath, QFont, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
    QListWidget, QListWidgetItem, QGraphicsDropShadowEffect,
    QScrollArea, QFrame, QSizePolicy, QPushButton
)
from qfluentwidgets import (
    SimpleCardWidget, FluentIcon, qconfig, Theme,
    NavigationInterface, NavigationItemPosition, NavigationPushButton,
    ScrollArea, SingleDirectionScrollArea
)
from one_dragon.utils.log_utils import log


@dataclass
class ContentCategory:
    """内容分类"""
    id: str
    title: str
    url: str
    icon: FluentIcon = FluentIcon.DOCUMENT
    content_type: str = "markdown"  # "markdown" or "json"


@dataclass
class ContentConfig:
    """内容配置"""
    categories: List[ContentCategory] = field(default_factory=list)
    default_category: str = ""

    @classmethod
    def create_default_config(cls) -> 'ContentConfig':
        """创建默认配置"""
        categories = [
            ContentCategory("intro", "home", "https://raw.githubusercontent.com/OneDragon-Anything/onedragon-anything.github.io/refs/heads/main/src/zzz/zh/home.md", FluentIcon.HOME),
            ContentCategory("quickstart", "speedoff", "https://raw.githubusercontent.com/OneDragon-Anything/onedragon-anything.github.io/refs/heads/main/src/zzz/zh/quickstart.md", FluentIcon.SPEED_HIGH),
            ContentCategory("faq", "?", "https://raw.githubusercontent.com/OneDragon-Anything/onedragon-anything.github.io/refs/heads/main/src/zzz/zh/faq.md", FluentIcon.QUESTION),
            ContentCategory("onedragon", "help", "https://raw.githubusercontent.com/OneDragon-Anything/onedragon-anything.github.io/refs/heads/main/src/zzz/zh/docs/feat_one_dragon.md", FluentIcon.ROBOT),
        ]
        return cls(categories=categories, default_category="intro")


class MarkdownParser:
    """Markdown解析器"""

    @staticmethod
    def parse(markdown_content: str) -> dict:
        """解析Markdown内容"""
        # 简单解析，提取标题和内容
        lines = markdown_content.split('\n')
        title = "内容"
        content_lines = []

        for line in lines:
            if line.startswith('# '):
                title = line[2:].strip()
            elif line.strip():
                # 移除Markdown语法
                clean_line = re.sub(r'[#*`\[\]()]', '', line)
                content_lines.append(clean_line)

        # 限制内容长度，避免显示过多
        content = '\n'.join(content_lines[:20])  # 只显示前20行
        if len(content) > 500:
            content = content[:500] + '...'

        return {
            "title": title,
            "content": content
        }


class ContentFetcher(QThread):
    """内容获取器"""
    content_fetched = Signal(dict)

    CACHE_DIR = "notice_cache"
    CACHE_DURATION = 86400  # 1天缓存
    TIMEOUT = 5

    def __init__(self, url: str, content_type: str = "markdown"):
        super().__init__()
        self.url = url
        self.content_type = content_type
        self.cache_file = os.path.join(
            self.CACHE_DIR,
            f"{hash(url)}.json"
        )

    def run(self):
        """获取内容"""
        try:
            # 尝试从缓存读取
            if self._is_cache_valid():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.content_fetched.emit(data)
                    return

            # 从网络获取
            response = requests.get(self.url, timeout=self.TIMEOUT)
            response.raise_for_status()

            if self.content_type == "markdown":
                data = MarkdownParser.parse(response.text)
            else:
                data = response.json()

            # 保存到缓存
            self._save_cache(data)
            self.content_fetched.emit(data)

        except Exception as e:
            log.error(f"获取内容失败: {e}")
            # 返回默认内容
            self.content_fetched.emit({
                "title": "加载失败",
                "content": "无法加载内容，请检查网络连接"
            })

    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if not os.path.exists(self.cache_file):
            return False
        cache_time = os.path.getmtime(self.cache_file)
        return time.time() - cache_time < self.CACHE_DURATION

    def _save_cache(self, data: dict):
        """保存缓存"""
        os.makedirs(self.CACHE_DIR, exist_ok=True)
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


class EnhancedAcrylicBackground(QWidget):
    """增强的亚克力背景效果"""

    def __init__(self, parent=None, radius: int = 8):
        super().__init__(parent)
        self.radius = radius
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._update_theme()
        qconfig.themeChanged.connect(self._update_theme)

    def _update_theme(self):
        """更新主题色"""
        is_dark = qconfig.theme == Theme.DARK
        # 提高不透明度，增强模糊感
        alpha = 220 if is_dark else 240
        base_color = 25 if is_dark else 250
        self.tint_color = QColor(base_color, base_color, base_color, alpha)
        self.border_color = QColor(255, 255, 255, 40 if is_dark else 60)
        self.update()

    def paintEvent(self, event):
        """绘制背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 创建圆角矩形路径
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)

        # 填充背景色（增强的半透明效果）
        painter.fillPath(path, self.tint_color)

        # 绘制边框高光
        painter.setPen(self.border_color)
        painter.drawPath(path)


class NavigationBar(QWidget):
    """左侧导航栏"""
    category_changed = Signal(str)  # 发送分类ID

    def __init__(self, categories: List[ContentCategory], parent=None):
        super().__init__(parent)
        self.categories = categories
        self.current_category = categories[0].id if categories else ""
        self.buttons = {}
        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # 创建导航按钮
        for category in self.categories:
            btn = NavigationPushButton(
                icon=category.icon,
                text=category.title,
                isSelectable=True,
                parent=self
            )
            btn.clicked.connect(lambda checked, cat_id=category.id: self._on_category_clicked(cat_id))
            layout.addWidget(btn)
            self.buttons[category.id] = btn

        layout.addStretch()

        # 设置默认选中
        if self.current_category in self.buttons:
            self.buttons[self.current_category].setSelected(True)

    def _on_category_clicked(self, category_id: str):
        """分类点击处理"""
        if category_id == self.current_category:
            return

        # 更新选中状态
        if self.current_category in self.buttons:
            self.buttons[self.current_category].setSelected(False)
        if category_id in self.buttons:
            self.buttons[category_id].setSelected(True)

        self.current_category = category_id
        self.category_changed.emit(category_id)


class ContentView(ScrollArea):
    """右侧内容显示区"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 内容容器
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        self.content_layout.setSpacing(12)

        # 标题
        self.title_label = QLabel("加载中...")
        self.title_label.setObjectName("contentTitle")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.content_layout.addWidget(self.title_label)

        # 内容
        self.content_label = QLabel("正在加载内容...")
        self.content_label.setObjectName("contentText")
        self.content_label.setWordWrap(True)
        self.content_label.setTextFormat(Qt.TextFormat.PlainText)
        content_font = QFont()
        content_font.setPointSize(10)
        self.content_label.setFont(content_font)
        self.content_layout.addWidget(self.content_label)

        self.content_layout.addStretch()
        self.setWidget(self.content_widget)

        # 应用样式
        self._apply_theme()
        qconfig.themeChanged.connect(self._apply_theme)

    def _apply_theme(self):
        """应用主题样式"""
        is_dark = qconfig.theme == Theme.DARK
        text_color = "#ffffff" if is_dark else "#000000"
        subtitle_color = "#cccccc" if is_dark else "#666666"

        self.setStyleSheet(f"""
            ScrollArea {{
                background: transparent;
                border: none;
            }}
            #contentTitle {{
                color: {text_color};
            }}
            #contentText {{
                color: {subtitle_color};
            }}
        """)

    def set_content(self, data: dict):
        """设置内容"""
        self.title_label.setText(data.get("title", ""))
        self.content_label.setText(data.get("content", ""))


class CompactNoticeCard(SimpleCardWidget):
    """紧凑型通知公告卡片"""

    def __init__(self, content_config: ContentConfig = None, parent=None):
        super().__init__(parent)
        self.content_config = content_config or ContentConfig.create_default_config()
        self.fetchers = {}  # 存储内容获取器
        self.current_category = self.content_config.default_category

        # 设置固定大小，避免撑大页面
        self.setFixedSize(600, 320)  # 宽度600，高度320，紧凑设计
        self.setBorderRadius(8)

        # 增强的亚克力背景
        self.acrylic_bg = EnhancedAcrylicBackground(self, radius=8)

        # 主布局
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 左侧导航栏（宽度150）
        self.nav_bar = NavigationBar(self.content_config.categories, self)
        self.nav_bar.setFixedWidth(150)
        self.nav_bar.category_changed.connect(self._on_category_changed)
        self.main_layout.addWidget(self.nav_bar)

        # 分隔线
        separator = QFrame()
        separator.setFrameStyle(QFrame.Shape.VLine)
        separator.setStyleSheet("QFrame { color: rgba(255, 255, 255, 30); }")
        self.main_layout.addWidget(separator)

        # 右侧内容区
        self.content_view = ContentView(self)
        self.main_layout.addWidget(self.content_view, 1)

        # 添加阴影效果
        self._add_shadow()

        # 加载默认内容
        if self.current_category:
            self._load_category(self.current_category)

    def _add_shadow(self):
        """添加阴影效果"""
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

    def _on_category_changed(self, category_id: str):
        """分类切换处理"""
        self.current_category = category_id
        self._load_category(category_id)

    def _load_category(self, category_id: str):
        """加载分类内容"""
        # 查找分类配置
        category = None
        for cat in self.content_config.categories:
            if cat.id == category_id:
                category = cat
                break

        if not category:
            return

        # 创建或获取内容获取器
        if category_id not in self.fetchers:
            fetcher = ContentFetcher(category.url, category.content_type)
            fetcher.content_fetched.connect(
                lambda data: self._on_content_fetched(category_id, data)
            )
            self.fetchers[category_id] = fetcher

        # 启动获取
        self.fetchers[category_id].start()

    def _on_content_fetched(self, category_id: str, data: dict):
        """内容获取完成"""
        if category_id == self.current_category:
            self.content_view.set_content(data)

    def resizeEvent(self, event):
        """调整大小事件"""
        super().resizeEvent(event)
        # 确保背景充满整个卡片
        if self.acrylic_bg:
            self.acrylic_bg.setGeometry(self.rect())

    def _normalBackgroundColor(self):
        """覆盖父类方法，返回透明色"""
        return QColor(0, 0, 0, 0)


class CompactNoticeCardContainer(QWidget):
    """紧凑型通知卡片容器"""

    def __init__(self, content_config: ContentConfig = None, parent=None):
        super().__init__(parent)
        self.content_config = content_config

        # 创建布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建通知卡片
        self.notice_card = CompactNoticeCard(content_config, self)
        layout.addWidget(self.notice_card)

        # 设置固定大小
        self.setFixedSize(600, 320)

        # 初始状态
        self._enabled = False

    def set_notice_enabled(self, enabled: bool):
        """设置是否启用"""
        self._enabled = enabled
        self.setVisible(enabled)

    def refresh_content(self):
        """刷新内容"""
        if self._enabled and self.notice_card:
            # 重新加载当前分类
            self.notice_card._load_category(self.notice_card.current_category)
