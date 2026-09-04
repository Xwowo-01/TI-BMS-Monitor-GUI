# theme.py
"""
全局主题与通用 UI 组件。

统一配色、QSS 样式，以及卡片容器、标题、状态点等复用组件。
只负责外观，不包含任何业务逻辑。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QSizePolicy,
    QWidget,
)

# ---------------------------------------------------------------------------
# 配色（专业·浅色企业风，配深色顶栏形成对比）
# ---------------------------------------------------------------------------
COLORS = {
    "bg": "#eef1f5",            # 窗口/页面底色
    "surface": "#ffffff",       # 卡片底色
    "surface_alt": "#f7f9fb",   # 次级底色（表头、交替行）
    "border": "#e3e7ee",        # 边框
    "border_strong": "#d3d9e2",  # 强边框

    "primary": "#2563eb",       # 主色（蓝）
    "primary_dark": "#1d4ed8",
    "primary_soft": "#eaf1fe",  # 主色浅底

    "text": "#1f2937",          # 主文字
    "text_secondary": "#5b6472",  # 次级文字
    "text_muted": "#8a94a3",    # 弱文字

    "ok": "#16a34a",
    "ok_soft": "#e8f7ee",
    "warn": "#f59e0b",
    "warn_soft": "#fdf3e2",
    "danger": "#dc2626",
    "danger_soft": "#fdeaea",
    "info": "#0ea5e9",

    "header_bg": "#0f172a",     # 顶栏深色底
    "header_border": "#1e293b",
}

# 状态 -> 颜色
STATUS_COLOR = {
    "connected": COLORS["ok"],
    "connecting": COLORS["warn"],
    "disconnected": COLORS["text_muted"],
    "offline": COLORS["danger"],
}


def mono_font(size=12, bold=False):
    """等宽字体（用于技术数值/报文/日志）。"""
    f = QFont("Consolas", size)
    f.setStyleHint(QFont.Monospace)
    f.setBold(bold)
    return f


def setup_plot(plot, min_height=150):
    """让 pyqtgraph 图表填充可用空间，而不把窗口的 preferred 尺寸撑得过高。

    pyqtgraph 的 PlotWidget 默认 sizeHint 较大，多个图表纵向堆叠后会使
    窗口 sizeHint 异常高，导致拖拽/还原窗口时变成超长竖长方形。
    这里把垂直策略设为 Ignored（忽略 sizeHint，只按布局伸缩），
    水平策略设为 Expanding（填满宽度）。
    """
    plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
    plot.setMinimumHeight(min_height)
    return plot


def ui_font(size=13, bold=False, weight=None):
    f = QFont("Segoe UI", size)
    if weight is not None:
        f.setWeight(weight)
    f.setBold(bold)
    return f


# ---------------------------------------------------------------------------
# 全局样式表
# ---------------------------------------------------------------------------
APP_STYLESHEET = """
* {
    font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    color: #1f2937;
    outline: none;
}

QWidget#Root {
    background: #eef1f5;
}

/* ---------- 顶栏 ---------- */
QFrame#HeaderBar {
    background: #0f172a;
    border: none;
}
QLabel#HeaderTitle {
    color: #ffffff;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 0.5px;
}
QLabel#HeaderSubtitle {
    color: #8b98ab;
    font-size: 11px;
}

/* ---------- 标签页 ---------- */
QTabWidget::pane {
    border: none;
    background: #eef1f5;
}
QTabBar {
    background: transparent;
}
QTabBar::tab {
    background: transparent;
    color: #5b6472;
    padding: 11px 26px;
    margin-right: 2px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 13px;
    font-weight: 500;
}
QTabBar::tab:hover:!selected {
    color: #1f2937;
    background: rgba(37, 99, 235, 0.05);
}
QTabBar::tab:selected {
    color: #2563eb;
    border-bottom: 2px solid #2563eb;
    font-weight: 600;
}

/* ---------- 卡片 ---------- */
QFrame#Card {
    background: #ffffff;
    border: 1px solid #e3e7ee;
    border-radius: 10px;
}
QLabel#CardTitle {
    font-size: 14px;
    font-weight: 600;
    color: #111827;
}
QLabel#CardSubtitle {
    color: #5b6472;
    font-size: 11px;
}
QLabel#HelpText {
    color: #8a94a3;
    font-size: 11px;
}

/* ---------- 按钮 ---------- */
QPushButton {
    background: #ffffff;
    border: 1px solid #d3d9e2;
    border-radius: 6px;
    padding: 7px 16px;
    color: #1f2937;
    font-weight: 500;
}
QPushButton:hover { background: #f3f5f8; border-color: #b6bfcb; }
QPushButton:pressed { background: #e8ecf1; }
QPushButton:disabled { color: #a7b0bd; background: #f7f9fb; border-color: #e8ecf1; }
QPushButton#PrimaryButton {
    background: #2563eb;
    border: 1px solid #2563eb;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#PrimaryButton:hover { background: #1d4ed8; border-color: #1d4ed8; }
QPushButton#PrimaryButton:pressed { background: #1e40af; }
QPushButton#PrimaryButton:disabled { background: #a7c1f3; border-color: #a7c1f3; color: #ffffff; }
QPushButton#GhostButton {
    background: transparent;
    border: 1px solid #d3d9e2;
    color: #5b6472;
}

/* ---------- 输入 ---------- */
QLineEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #d3d9e2;
    border-radius: 6px;
    padding: 6px 9px;
    min-height: 18px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #2563eb; }
QLineEdit:disabled, QComboBox:disabled { background: #f7f9fb; color: #a7b0bd; }
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #e3e7ee;
    border-radius: 6px;
    selection-background-color: #eaf1fe;
    selection-color: #1f2937;
    padding: 4px;
}

/* ---------- 文本 / 日志 ---------- */
QTextEdit, QPlainTextEdit {
    background: #0f172a;
    color: #cbd5e1;
    border: 1px solid #1e293b;
    border-radius: 8px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    padding: 8px;
}

/* ---------- 进度条 ---------- */
QProgressBar {
    border: none;
    border-radius: 6px;
    background: #e8ecf1;
    text-align: center;
    color: #111827;
    font-weight: 600;
    font-size: 11px;
}
QProgressBar::chunk {
    border-radius: 6px;
    background: #2563eb;
}

/* ---------- 复选框 ---------- */
QCheckBox { spacing: 7px; color: #1f2937; }

/* ---------- 分组框 ---------- */
QGroupBox {
    border: 1px solid #e3e7ee;
    border-radius: 8px;
    margin-top: 10px;
    font-weight: 600;
    color: #334155;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #475569;
    background: transparent;
}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 4px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: #94a3b8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #cbd5e1; border-radius: 4px; min-width: 32px; }
QScrollBar::handle:horizontal:hover { background: #94a3b8; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

/* ---------- 工具提示 ---------- */
QToolTip {
    background: #0f172a;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 5px;
    padding: 7px 9px;
    font-size: 12px;
}

/* ---------- 表格 ---------- */
QTableWidget {
    background: #ffffff;
    border: 1px solid #e3e7ee;
    border-radius: 8px;
    gridline-color: #eef1f5;
    alternate-background-color: #f7f9fb;
}
QHeaderView::section {
    background: #f7f9fb;
    color: #475569;
    border: none;
    border-bottom: 1px solid #e3e7ee;
    padding: 7px 8px;
    font-weight: 600;
}
QTableWidget::item { padding: 4px 6px; }
QTableWidget::item:selected { background: #eaf1fe; color: #1f2937; }
"""


# ---------------------------------------------------------------------------
# 通用组件
# ---------------------------------------------------------------------------
def apply_shadow(widget, blur=24, y=3, alpha=38):
    """给 widget 加柔和投影（可选，用于悬浮层次）。"""
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, y)
    eff.setColor(QColor(15, 23, 42, alpha))
    widget.setGraphicsEffect(eff)
    return eff


class Card(QFrame):
    """带标题栏的卡片容器。

    :param title: 卡片标题
    :param subtitle: 副标题（一句话说明本卡用途）
    :param help_text: 帮助/补充说明（灰色小字，可换行）
    """

    def __init__(self, title="", subtitle="", help_text="", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        self.title_label = None
        self.subtitle_label = None
        self.help_label = None
        self._title_row = None
        self._header_widget = None
        if title or subtitle or help_text:
            header = QVBoxLayout()
            header.setContentsMargins(16, 10, 16, 8)
            header.setSpacing(2)
            if title:
                self.title_label = QLabel(title)
                self.title_label.setObjectName("CardTitle")
                title_row = QHBoxLayout()
                title_row.setSpacing(8)
                title_row.addWidget(self.title_label)
                title_row.addStretch(1)
                self._title_row = title_row
                header.addLayout(title_row)
            if subtitle:
                self.subtitle_label = QLabel(subtitle)
                self.subtitle_label.setObjectName("CardSubtitle")
                self.subtitle_label.setWordWrap(True)
                header.addWidget(self.subtitle_label)
            if help_text:
                self.help_label = QLabel(help_text)
                self.help_label.setObjectName("HelpText")
                self.help_label.setWordWrap(True)
                header.addWidget(self.help_label)
            self._outer.addLayout(header)

            divider = QFrame()
            divider.setFrameShape(QFrame.HLine)
            divider.setFixedHeight(1)
            divider.setStyleSheet(
                "background:#eef1f5; border:none;"
            )
            self._outer.addWidget(divider)

        # 内容区
        self.body = QVBoxLayout()
        self.body.setContentsMargins(16, 10, 16, 12)
        self.body.setSpacing(8)
        self._outer.addLayout(self.body, 1)

    def set_title(self, text):
        if self.title_label is not None:
            self.title_label.setText(text)

    def body_layout(self):
        return self.body

    def add_widget(self, widget, stretch=0, alignment=None):
        if alignment is not None:
            self.body.addWidget(widget, stretch, alignment)
        else:
            self.body.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout, stretch=0):
        self.body.addLayout(layout, stretch)
        return layout

    def add_header_widget(self, widget):
        """在标题行右侧加入一个控件（如按钮），与标题保持同一横排。"""
        if self._title_row is not None:
            self._title_row.addWidget(widget)
            self._header_widget = widget
            return widget
        return None


class StatusDot(QLabel):
    """彩色状态点（用于连接状态等）。"""

    def __init__(self, color="#94a3b8", diameter=10, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._diameter = diameter
        self.setFixedSize(diameter + 2, diameter + 2)

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        d = self._diameter
        r = self.rect()
        center = r.center()
        # 外圈柔光
        p.setPen(Qt.NoPen)
        glow = QColor(self._color)
        glow.setAlpha(60)
        p.setBrush(QBrush(glow))
        p.drawEllipse(center, d // 2 + 2, d // 2 + 2)
        # 实心点
        p.setBrush(QBrush(self._color))
        p.drawEllipse(center, d // 2, d // 2)
        p.end()


def info_rich(key, value, key_color=None, value_color=None, value_mono=False,
              suffix=""):
    """生成一条「键：值」的富文本 HTML（用于信息展示，风格统一）。"""
    kc = key_color or COLORS["text_secondary"]
    vc = value_color or COLORS["text"]
    mono = 'font-family:"Consolas","Courier New",monospace;' if value_mono else ""
    return (
        f'<span style="color:{kc};">{key}：</span>'
        f'<span style="color:{vc};{mono}">{value}{suffix}</span>'
    )
