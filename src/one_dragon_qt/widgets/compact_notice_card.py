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
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set
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
    ScrollArea, SingleDirectionScrollArea, TabBar, TextBrowser
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
    def parse(markdown_content: str, source_url: str = None) -> dict:
        """解析Markdown内容
        
        Args:
            markdown_content: Markdown原始内容
            source_url: 源URL，用于解析相对路径
        """
        # 提取标题
        lines = markdown_content.split('\n')
        title = "内容"

        for line in lines:
            if line.startswith('# '):
                title = line[2:].strip()
                break

        # 处理内容，移除YAML front matter
        content_lines = []
        in_front_matter = False

        for line in lines:
            # 跳过YAML front matter
            if line.strip() == '---':
                if not in_front_matter:
                    in_front_matter = True
                    continue
                else:
                    in_front_matter = False
                    continue

            if in_front_matter:
                continue

            content_lines.append(line)

        # 重新组合内容
        processed_content = '\n'.join(content_lines)

        # 处理图片URL（转换相对路径为绝对路径）
        if source_url:
            processed_content = MarkdownParser._process_image_urls(processed_content, source_url)

        # 限制内容长度，避免显示过多
        if len(processed_content) > 2000:
            # 找到第一个段落结束的位置
            first_paragraph_end = processed_content.find('\n\n', 1500)
            if first_paragraph_end > 0:
                processed_content = processed_content[:first_paragraph_end] + '\n\n...'
            else:
                processed_content = processed_content[:2000] + '...'

        # 转换为HTML以更好地支持图片
        html_content = MarkdownParser._markdown_to_html(processed_content)

        # 提取所有图片URL
        image_urls = MarkdownParser._extract_image_urls(html_content)
        
        return {
            "title": title,
            "content": processed_content,
            "html": html_content,
            "image_urls": list(image_urls)  # 转换Set为List以支持JSON序列化
        }
    
    @staticmethod
    def _process_image_urls(content: str, source_url: str) -> str:
        """处理图片URL，将相对路径转换为绝对路径"""
        # 解析基础URL
        if 'github.com' in source_url or 'githubusercontent.com' in source_url:
            # GitHub Raw URL处理
            base_parts = source_url.rsplit('/', 1)[0]
            
            # 查找所有图片标签
            image_pattern = r'!\[([^\]]*)\]\(([^\)]+)\)'
            
            def replace_image_url(match):
                alt_text = match.group(1)
                url = match.group(2)
                
                # 如果是相对路径，转换为绝对路径
                if not url.startswith(('http://', 'https://')):
                    if url.startswith('/'):
                        # 以/开头的路径，需要获取域名部分
                        # 从GitHub raw URL中提取基础部分
                        if 'githubusercontent.com' in base_parts:
                            # 例如: https://raw.githubusercontent.com/user/repo/branch/path
                            # 需要保留到branch部分
                            parts = base_parts.split('/')
                            # 找到githubusercontent.com后的第4个部分（branch）
                            base_url = '/'.join(parts[:7])  # 保留到branch
                            url = f"{base_url}{url}"
                        else:
                            url = f"{base_parts}{url}"
                    elif url.startswith('./'):
                        # 当前目录的相对路径
                        url = f"{base_parts}/{url[2:]}"
                    elif url.startswith('../'):
                        # 处理上级目录
                        parent_parts = base_parts.rsplit('/', 1)[0]
                        url = f"{parent_parts}/{url[3:]}"
                    else:
                        # 普通相对路径
                        url = f"{base_parts}/{url}"
                
                return f'![{alt_text}]({url})'
            
            content = re.sub(image_pattern, replace_image_url, content)
        
        return content
    
    @staticmethod
    def _markdown_to_html(markdown_content: str) -> str:
        """将Markdown转换为HTML（简单实现）"""
        html = markdown_content
        
        # 转换标题
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        
        # 转换代码块（先处理代码块，避免内部内容被其他规则影响）
        html = re.sub(r'```([^`]+)```', r'<pre><code>\1</code></pre>', html, flags=re.DOTALL)
        html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)
        
        # 转换图片 - 必须在链接之前处理！
        html = re.sub(r'!\[([^\]]*)\]\(([^\)]+)\)', 
                     r'<img src="\2" alt="\1" style="max-width: 100%; height: auto;" />', html)
        
        # 转换链接（在图片之后处理）
        html = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', html)
        
        # 转换粗体（避免与列表标记冲突）
        html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
        html = re.sub(r'__(.+?)__', r'<b>\1</b>', html)
        
        # 转换斜体（避免与列表标记冲突）
        html = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', html)
        html = re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'<i>\1</i>', html)
        
        # 转换列表
        html = re.sub(r'^\* (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'^\d+\. (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        
        # 转换段落
        paragraphs = html.split('\n\n')
        html_paragraphs = []
        for p in paragraphs:
            p = p.strip()
            if p and not p.startswith('<'):
                p = f'<p>{p}</p>'
            html_paragraphs.append(p)
        html = '\n'.join(html_paragraphs)
        
        # 包装列表项
        html = re.sub(r'(<li>.*</li>)', r'<ul>\1</ul>', html, flags=re.DOTALL)
        
        return html
    
    @staticmethod
    def _extract_image_urls(html_content: str) -> Set[str]:
        """从HTML内容中提取所有图片URL"""
        image_urls = set()
        # 匹配img标签中的src属性
        img_pattern = r'<img[^>]+src="([^"]+)"'
        matches = re.findall(img_pattern, html_content)
        for url in matches:
            if url and not url.startswith('file:///'):
                image_urls.add(url)
        return image_urls


class ContentFetcher(QThread):
    """内容获取器"""
    content_fetched = Signal(dict)

    CACHE_DIR = "notice_cache"
    IMAGE_CACHE_DIR = "notice_cache/images"
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
        # 确保图片缓存目录存在
        os.makedirs(self.IMAGE_CACHE_DIR, exist_ok=True)

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
                data = MarkdownParser.parse(response.text, self.url)
                # 下载并缓存图片
                if "image_urls" in data and data["image_urls"]:
                    data["html"] = self._download_and_replace_images(data["html"], data["image_urls"])
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
    
    def _download_and_replace_images(self, html_content: str, image_urls: list) -> str:
        """下载图片并替换HTML中的URL为本地路径"""
        for url in image_urls:
            try:
                # 生成本地文件名
                url_hash = hashlib.md5(url.encode()).hexdigest()
                # 尝试从URL获取文件扩展名
                ext = '.png'  # 默认扩展名
                if '.' in url:
                    potential_ext = url.rsplit('.', 1)[-1].lower()
                    if potential_ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp']:
                        ext = f'.{potential_ext}'
                
                local_filename = f"{url_hash}{ext}"
                local_path = os.path.join(self.IMAGE_CACHE_DIR, local_filename)
                
                # 如果图片已缓存且未过期，直接使用
                if os.path.exists(local_path):
                    cache_time = os.path.getmtime(local_path)
                    if time.time() - cache_time < self.CACHE_DURATION:
                        # 使用本地路径替换URL（使用绝对路径）
                        absolute_path = os.path.abspath(local_path)
                        file_url = f"file:///{absolute_path.replace(os.sep, '/')}"
                        html_content = html_content.replace(f'src="{url}"', f'src="{file_url}"')
                        continue
                
                # 下载图片
                log.info(f"下载图片: {url}")
                img_response = requests.get(url, timeout=self.TIMEOUT)
                img_response.raise_for_status()
                
                # 保存图片
                with open(local_path, 'wb') as f:
                    f.write(img_response.content)
                
                # 使用本地路径替换URL（使用绝对路径）
                absolute_path = os.path.abspath(local_path)
                file_url = f"file:///{absolute_path.replace(os.sep, '/')}"
                html_content = html_content.replace(f'src="{url}"', f'src="{file_url}"')
                log.info(f"图片已缓存: {local_filename}")
                
            except Exception as e:
                log.error(f"下载图片失败 {url}: {e}")
                # 如果下载失败，保持原URL
                continue
        
        return html_content


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


class NavigationBar(TabBar):
    """顶部TabBar导航栏"""
    category_changed = Signal(str)  # 发送分类ID

    def __init__(self, categories: List[ContentCategory], parent=None):
        super().__init__(parent)
        self.categories = categories
        self.current_category = categories[0].id if categories else ""

        # 禁用关闭标签页功能
        self.setTabsClosable(False)
        self.setAddButtonVisible(False)
        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        # 添加tab项
        for category in self.categories:
            self.addTab(
                routeKey=category.id,
                text=category.title,
                icon=category.icon,
                onClick=lambda cat_id=category.id: self._on_category_clicked(cat_id)
            )

        # 设置默认选中
        if self.current_category:
            self.setCurrentTab(self.current_category)

    def _on_category_clicked(self, category_id: str):
        """分类点击处理"""
        if category_id == self.current_category:
            return

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

        # 内容 - 使用TextBrowser支持Markdown渲染
        self.content_browser = TextBrowser()
        self.content_browser.setObjectName("contentText")
        self.content_browser.setOpenExternalLinks(True)  # 允许点击链接
        self.content_browser.setMaximumHeight(250)  # 增加高度以显示更多内容
        # 启用图片加载
        self.content_browser.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction | 
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        content_font = QFont()
        content_font.setPointSize(9)  # 稍微减小字体
        self.content_browser.setFont(content_font)
        self.content_layout.addWidget(self.content_browser)

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
                background: transparent;
                border: none;
            }}
        """)

    def set_content(self, data: dict):
        """设置内容"""
        self.title_label.setText(data.get("title", ""))
        
        # 优先使用HTML内容（如果有）以更好地支持图片
        if "html" in data and data["html"]:
            self.content_browser.setHtml(data["html"])
        else:
            # 回退到Markdown渲染
            self.content_browser.setMarkdown(data.get("content", ""))


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

        # 主布局 - 改为垂直布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 顶部导航栏（TabBar格式）
        self.nav_bar = NavigationBar(self.content_config.categories, self)
        self.nav_bar.category_changed.connect(self._on_category_changed)
        self.main_layout.addWidget(self.nav_bar)

        # 内容区
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
