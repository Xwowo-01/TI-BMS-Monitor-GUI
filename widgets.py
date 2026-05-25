import numpy as np

from PySide6.QtWidgets import QToolTip
import math
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QWidget,  QSizePolicy
)
from PySide6.QtCore import Qt, QRect,QPoint,QPointF,QMargins
from PySide6.QtGui import QPainter, QPen, QColor, QFont,QRadialGradient,QBrush
import pyqtgraph as pg
from PySide6.QtCore import Signal
from PySide6.QtCharts import QChartView, QChart, QLineSeries, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget, QLabel
from PySide6.QtGui import QColor, QPainter
# ================= 吸附显示最近数据点 =================
class SnapScatterItem(pg.ScatterPlotItem):
    def __init__(self, x, y, fmt="x={:.2f}\ny={:.2f}", threshold=0.5):
        super().__init__(x=x, y=y, size=3, brush=pg.mkBrush("#2ECC71"))

        self.x = np.array(x)
        self.y = np.array(y)
        self.fmt = fmt
        self.threshold = threshold

        self.text = pg.TextItem(anchor=(0, 1))

        # ===== 字体 =====
        self.text.setFont(QFont("Arial", 10, QFont.Bold))

        # ===== 文字颜色 =====
        self.text.setColor(QColor("#222222"))

        # ===== 初始白底（占位）=====
        self.text.setHtml("""
            <div style="
                background-color: white;
                padding: 4px 6px;
                border: 1px solid #CFCFCF;
                border-radius: 4px;
            ">
            </div>
        """)

        self.text.hide()

    def hoverEvent(self, ev):
        if ev.isExit():
            self.text.hide()
            return

        pos = ev.pos()
        dist = np.hypot(self.x - pos.x(), self.y - pos.y())
        idx = np.argmin(dist)

        if dist[idx] < self.threshold:
            self.text.setHtml(f"""
                <div style="
                    background-color: white;
                    padding: 4px 6px;
                    border: 1px solid #CFCFCF;
                    border-radius: 4px;
                ">
                {self.fmt.format(self.x[idx], self.y[idx])}
                </div>
            """)
            self.text.setPos(self.x[idx], self.y[idx])
            self.text.show()
        else:
            self.text.hide()


# ================= 圆环组件 =================
class CircularGauge(QWidget):
    def __init__(self, title, subtitle, value=75):
        super().__init__()
        self.value = value
        self.title = title
        self.subtitle = subtitle
        self.setMinimumSize(120, 120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def setValue(self, value: int):
        self.value = max(0, min(100, value))
        self.update()

    def set_texts(self, title: str, subtitle: str):
        """运行时更新标题和副标题，并重绘"""
        self.title = title
        self.subtitle = subtitle
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        side = min(self.width(), self.height())
        center = QPoint(self.width() // 2, self.height() // 2)

        # 圆环绘制区域
        circleRect = QRect(
            center.x() - side // 2,
            center.y() - side // 2,
            side,
            side
        ).adjusted(15, 15, -15, -15)

        # ---------- 背景圆环 ----------
        painter.setPen(QPen(QColor("#DDDDDD"), 12))
        painter.drawEllipse(circleRect)

        # ---------- 带发光的圆弧 ----------
        color = QColor("#2ECC71") if self.value >= 70 else QColor("#F1C40F")
        pen = QPen(color, 12)
        painter.setPen(pen)
        painter.drawArc(
            circleRect,
            90 * 16,
            int(-360 * self.value / 100) * 16
        )

        # 发光效果实现：沿圆弧采样，绘制小半透明圆叠加
        glow_radius = 12  # 发光半径
        steps = int(360 * self.value / 100)+12  # 圆弧采样点数
        start_angle = 95  # 逆时针从顶部开始

        for i in range(steps + 1):
            angle = math.radians(start_angle - i)
            # 圆环半径
            r = circleRect.width() / 2
            # 圆弧点坐标
            x = center.x() + r * math.cos(angle)
            y = center.y() - r * math.sin(angle)
            # 发光渐变圆
            gradient = QRadialGradient(QPointF(x, y), glow_radius)
            gradient.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 15))  # 中心亮
            gradient.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))  # 边缘透明
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(x, y), glow_radius, glow_radius)

        # ---------- 文本 ----------
        textRect = QRect(
            center.x() - side // 2,
            center.y() - side // 2,
            side,
            side
        )
        painter.setPen(QColor("#222"))
        painter.setFont(QFont("Arial", int(side * 0.12), QFont.Bold))
        painter.drawText(textRect.adjusted(0, -int(side * 0.08), 0, 0), Qt.AlignCenter, f"{self.value} %")

        painter.setFont(QFont("Arial", int(side * 0.075)))
        # ★ 如果 subtitle 为空，则不显示 "/" 和副标题
        if self.subtitle:
            bottom_text = f"{self.title}/{self.subtitle}"
        else:
            bottom_text = self.title
        painter.drawText(
            textRect.adjusted(0, int(side * 0.55), 0, 0),
            Qt.AlignHCenter | Qt.AlignTop,
            bottom_text
        )


# ================= 单个电池图元（矮小+小凸起版） =================
class BatteryCell(QWidget):
    clicked = Signal(str)

    def __init__(self, value, charging=False, mode="", name=""):
        super().__init__()
        self.value = value
        self.charging = charging
        self.mode = mode          # "SoC" / "Temp" / "Volt" / "SoH"
        self.name = name          # 例："1", "25"

        # 高度增加以放置底部编号
        self.setFixedSize(14, 32)
        self.setMouseTracking(True)

        # 提取数字编号（从名称中获取纯数字部分）
        try:
            num_str = ''.join(ch for ch in self.name if ch.isdigit())
            self.index = int(num_str) if num_str else 0
        except:
            self.index = 0

    def setValue(self, value):
        """更新电池数值并刷新显示"""
        self.value = value
        self.update()  # 触发重绘
    def get_tooltip_text(self):
        unit = ""
        if self.mode == "SoC": unit = " %"
        elif self.mode == "Volt": unit = " mV"
        elif self.mode == "Temp": unit = " ℃"
        elif self.mode == "SoH": unit = " %"
        return f"<b>{self.name}</b><br>值：{self.value}{unit}"

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.name)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        QToolTip.showText(QCursor.pos(), self.get_tooltip_text(), self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # 颜色设定（依据《分布诊断.xlsx》）
        color = QColor("#2ECC71")   # 正常：绿色

        # ================= SoC =================
        if self.mode == "SoC":
            # 严重
            if self.value <= 10:
                color = QColor("#E74C3C")
            # 一般
            elif self.value <= 20:
                color = QColor("#F39C12")
            # 正常
            else:
                color = QColor("#2ECC71")

        # ================= 温度 =================
        elif self.mode == "Temp":
            # 严重过温 >=55℃
            if self.value >= 55:
                color = QColor("#E74C3C")
            # 一般过温 >=50℃
            elif self.value >= 50:
                color = QColor("#F39C12")
            # 严重低温 <=-36℃
            elif self.value <= -36:
                color = QColor("#E74C3C")
            # 一般低温 <=-31℃
            elif self.value <= -31:
                color = QColor("#F39C12")
            else:
                color = QColor("#2ECC71")

        # ================= 电压 =================
        elif self.mode == "Volt":
            # 单位 mV
            # 严重过压 >=4300
            if self.value >= 4300:
                color = QColor("#E74C3C")
            # 一般过压 >=4250
            elif self.value >= 4250:
                color = QColor("#F39C12")
            # 严重欠压 <=2500
            elif self.value <= 2500:
                color = QColor("#E74C3C")
            # 一般欠压 <=2800
            elif self.value <= 2800:
                color = QColor("#F39C12")
            else:
                color = QColor("#2ECC71")
        # ================= SoH =================
        elif self.mode == "SoH":
            # 严重老化
            if self.value <= 70:
                color = QColor("#E74C3C")
            # 一般老化
            elif self.value <= 80:
                color = QColor("#F39C12")
            else:
                color = QColor("#2ECC71")

        # ---- 电池主体 ----
        p.setBrush(color)
        p.setPen(Qt.NoPen)

        # 主体矩形 (x=2, y=6, w=10, h=16)
        p.drawRoundedRect(2, 6, 10, 16, 2, 2)

        # 上方小凸起 (x=5, y=3, w=3, h=2)
        p.drawRoundedRect(5, 3, 3, 2, 1, 1)

        # ---- 充电闪电 (仅 SoC 模式) ----
        if self.charging and self.mode == "SoC":
            p.setPen(QPen(QColor("white"), 1))
            # 闪电线条（在电池内部）
            p.drawLine(7, 6, 5.5, 12)
            p.drawLine(7, 6, 6.5, 12)
            p.drawLine(5.5, 12, 9.5, 12)
            p.drawLine(8, 12, 7, 18)
            p.drawLine(9.5, 12, 7, 18)

        # ---- 底部数字编号 ----
        p.setPen(QColor(160, 160, 160))                # 浅灰色
        font = QFont("Arial", 7)
        p.setFont(font)
        # 绘制区域为整个 widget 底部约 10 像素高度
        text_rect = self.rect().adjusted(0, 22, 0, 0)
        p.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, str(self.index))

class TrendChartWidget(QWidget):
    """上下两个独立折线图：SoC 和 SoH（极简放大版）"""

    # =====================================================
    # 中文
    # =====================================================

    class UITextZH:
        SOC_CURVE = "SoC状态曲线"
        SOH_CURVE = "SoH状态曲线"

    # =====================================================
    # 英文
    # =====================================================

    class UITextEN:
        SOC_CURVE = "SoC Trend"
        SOH_CURVE = "SoH Trend"

    def __init__(self, parent=None):
        super().__init__()

        import pyqtgraph as pg

        self.ui_text = self.UITextZH

        # 全局风格
        pg.setConfigOption("foreground", "k")
        pg.setConfigOption("background", "w")

        # 主布局
        self.layout = QVBoxLayout(self)

        self.layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        self.layout.setSpacing(1)

        # =================================================
        # SoC
        # =================================================

        self.label_soc = QLabel(
            self.ui_text.SOC_CURVE
        )

        self.label_soc.setAlignment(
            Qt.AlignCenter
        )

        self.label_soc.setStyleSheet("""
            font-weight: bold;
            font-size: 11px;
            margin: 0;
            padding: 0;
        """)

        self.layout.addWidget(
            self.label_soc
        )

        self.soc_plot = pg.PlotWidget()

        self.soc_plot.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding
        )

        # 网格
        self.soc_plot.showGrid(
            x=True,
            y=True,
            alpha=0.2
        )

        # 边框
        self.soc_plot.getPlotItem().getViewBox().setBorder(
            pg.mkPen("#D0D0D0")
        )

        # 删除标题但保留坐标轴
        self.soc_plot.setLabel("left", "")
        self.soc_plot.setLabel("bottom", "")

        # 坐标轴样式
        self.soc_plot.getAxis("bottom").setStyle(
            tickTextOffset=2
        )

        self.soc_plot.getAxis("left").setStyle(
            tickTextOffset=2,
            autoExpandTextSpace=False
        )

        # Y轴百分号
        self.soc_plot.getAxis("left").setTicks([
            [
                (0, "0%"),
                (20, "20%"),
                (40, "40%"),
                (60, "60%"),
                (80, "80%"),
                (100, "100%")
            ]
        ])

        # 去边距
        self.soc_plot.getPlotItem().layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        self.soc_plot.getPlotItem().setContentsMargins(
            0,
            0,
            0,
            0
        )

        # 锁定 Y 轴
        self.soc_plot.setYRange(0, 100)

        self.soc_plot.setLimits(
            yMin=0,
            yMax=100,
            minYRange=100,
            maxYRange=100,
            xMin=0
        )

        # 禁止 Y 轴缩放
        self.soc_plot.getViewBox().setMouseEnabled(
            x=True,
            y=False
        )

        # 曲线
        self.soc_curve = self.soc_plot.plot(
            [],
            [],
            pen=pg.mkPen("#3498DB", width=2)
        )

        self.layout.addWidget(
            self.soc_plot,
            1
        )

        # =================================================
        # SoH
        # =================================================

        self.label_soh = QLabel(
            self.ui_text.SOH_CURVE
        )

        self.label_soh.setAlignment(
            Qt.AlignCenter
        )

        self.label_soh.setStyleSheet("""
            font-weight: bold;
            font-size: 11px;
            margin: 0;
            padding: 0;
        """)

        self.layout.addWidget(
            self.label_soh
        )

        self.soh_plot = pg.PlotWidget()

        self.soh_plot.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding
        )

        # 网格
        self.soh_plot.showGrid(
            x=True,
            y=True,
            alpha=0.2
        )

        # 边框
        self.soh_plot.getPlotItem().getViewBox().setBorder(
            pg.mkPen("#D0D0D0")
        )

        # 删除标题但保留坐标轴
        self.soh_plot.setLabel("left", "")
        self.soh_plot.setLabel("bottom", "")

        # 坐标轴样式
        self.soh_plot.getAxis("bottom").setStyle(
            tickTextOffset=2
        )

        self.soh_plot.getAxis("left").setStyle(
            tickTextOffset=2,
            autoExpandTextSpace=False
        )

        # Y轴百分号
        self.soh_plot.getAxis("left").setTicks([
            [
                (0, "0%"),
                (20, "20%"),
                (40, "40%"),
                (60, "60%"),
                (80, "80%"),
                (100, "100%")
            ]
        ])

        # 去边距
        self.soh_plot.getPlotItem().layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        self.soh_plot.getPlotItem().setContentsMargins(
            0,
            0,
            0,
            0
        )

        # 锁定 Y 轴
        self.soh_plot.setYRange(0, 100)

        self.soh_plot.setLimits(
            yMin=0,
            yMax=100,
            minYRange=100,
            maxYRange=100,
            xMin=0
        )

        # 禁止 Y 轴缩放
        self.soh_plot.getViewBox().setMouseEnabled(
            x=True,
            y=False
        )

        # 曲线
        self.soh_curve = self.soh_plot.plot(
            [],
            [],
            pen=pg.mkPen("#2ECC71", width=2)
        )

        self.layout.addWidget(
            self.soh_plot,
            1
        )

    # =====================================================
    # 语言切换
    # =====================================================

    def switch_language(self, language="zh"):

        if language == "en":

            self.ui_text = self.UITextEN

        else:

            self.ui_text = self.UITextZH

        self.retranslate_ui()

    # =====================================================
    # 刷新文本
    # =====================================================

    def retranslate_ui(self):

        self.label_soc.setText(
            self.ui_text.SOC_CURVE
        )

        self.label_soh.setText(
            self.ui_text.SOH_CURVE
        )

    # =====================================================
    # 更新数据
    # =====================================================

    def update_data(
            self,
            soc_history,
            soh_history,
            max_history_len=20
    ):
        """更新图表数据"""

        # SoC
        x_soc = list(range(len(soc_history)))

        self.soc_curve.setData(
            x_soc,
            soc_history
        )

        # SoH
        x_soh = list(range(len(soh_history)))

        self.soh_curve.setData(
            x_soh,
            soh_history
        )

        max_len = max(
            len(soc_history),
            len(soh_history),
            1
        )

        x_max = max(
            max_history_len,
            max_len
        ) - 1

        # X轴固定从0开始
        self.soc_plot.setXRange(
            0,
            x_max,
            padding=0
        )

        self.soh_plot.setXRange(
            0,
            x_max,
            padding=0
        )

        # 强制限制 X轴 >= 0
        self.soc_plot.setLimits(
            xMin=0
        )

        self.soh_plot.setLimits(
            xMin=0
        )