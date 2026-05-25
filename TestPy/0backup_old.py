import sys
import numpy as np
from PySide6.QtWidgets import QComboBox
from PySide6.QtWidgets import QTabWidget
from PySide6.QtWidgets import QToolTip

from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QHBoxLayout, QVBoxLayout, QGridLayout,
    QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QPen, QColor, QFont
import pyqtgraph as pg


# ================= 吸附显示最近数据点 =================
class SnapScatterItem(pg.ScatterPlotItem):
    def __init__(self, x, y, fmt="x={:.2f}\ny={:.2f}", threshold=0.5):
        super().__init__(x=x, y=y, size=3, brush=pg.mkBrush(0, 0, 0))

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

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # ---------- 基础尺寸 ----------
        side = min(self.width(), self.height())
        center_x = self.width() // 2
        center_y = self.height() // 2

        # ---------- 圆环绘制区域 ----------
        circleRect = QRect(
            center_x - side // 2,
            center_y - side // 2,
            side,
            side
        ).adjusted(15, 15, -15, -15)

        painter.setPen(QPen(QColor("#DDDDDD"), 12))
        painter.drawEllipse(circleRect)

        color = QColor("#2ECC71") if self.value >= 70 else QColor("#F1C40F")
        painter.setPen(QPen(color, 12))
        painter.drawArc(
            circleRect,
            90 * 16,
            int(-360 * self.value / 100) * 16
        )

        # ---------- 文本绘制区域（独立于圆） ----------
        textRect = QRect(
            center_x - side // 2,
            center_y - side // 2,
            side,
            side
        )

        # 百分比（真正几何居中）
        painter.setPen(QColor("#222"))
        painter.setFont(QFont("Arial", int(side * 0.12), QFont.Bold))
        painter.drawText(textRect.adjusted(0, -int(side * 0.08), 0, 0), Qt.AlignCenter, f"{self.value} %")

        # 中文说明（居中，位于百分比下方）
        painter.setFont(QFont("Arial", int(side * 0.075)))
        painter.drawText(
            textRect.adjusted(0, int(side * 0.55), 0, 0),
            Qt.AlignHCenter | Qt.AlignTop,
            f"{self.title}/{self.subtitle}"
        )

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("电池监控系统")
        self.resize(800, 600)

        main_layout = QVBoxLayout(self)

        # ===== 顶部导航栏（页签）=====
        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.North)  # 页签在顶部
        tabs.setMovable(False)

        # ===== 单体监测页（你原来的整页）=====
        single_page = BatteryMonitorUI()

        # ===== 整体情况页（空白）=====
        overall_page = OverallStatusPage()

        setting_page = SettingUI()
        # ===== 加入页签 =====
        tabs.addTab(overall_page, "整体情况")
        tabs.addTab(single_page, "单体监测")
        tabs.addTab(setting_page, "配置管理")
        main_layout.addWidget(tabs)

# ================= 主界面1 =================
class BatteryMonitorUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("电池监控系统")
        self.resize(800, 600)

        pg.setConfigOption("foreground", "k")
        pg.setConfigOption("background", "w")

        self.expanded_frame = None

        main = QHBoxLayout(self)
        main.setStretch(0, 1)
        main.setStretch(1, 3)

        # ================= 左侧 =================
        left = QWidget()
        lv = QVBoxLayout(left)

        title = QLabel("实时监测")
        title.setFont(QFont("Arial", 16, QFont.Bold))

        lv.addWidget(title)

        # --- 电池选择框 ---
        battery_select = QComboBox()
        battery_select.addItems([
            "电池组 A（主电池）",
            "电池组 B（备用）",
            "电池组 C（动力）",
            "电池组 D（测试）",
            "电池组 E（扩展）"
        ])
        battery_select.setMinimumHeight(32)
        lv.addWidget(battery_select)
        # --- SoC ---
        soc_layout = QHBoxLayout()
        self.soc_charge_label = QLabel()
        self.soc_charge_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.soc_charge_label.setText(
            "正在充电：是\n"
            "剩余容量：3280 mAh\n"
            "满充容量：4000 mAh"
        )

        soc_layout.addWidget(CircularGauge("SoC", "荷电状态", 82), stretch=1)
        soc_layout.addWidget(self.soc_charge_label)
        lv.addLayout(soc_layout)

        # --- SoH ---
        soh_layout = QHBoxLayout()
        self.soh_diag_label = QLabel("电池诊断：状态良好。")
        self.soh_diag_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        soh_layout.addWidget(CircularGauge("SoH", "健康状态", 91), stretch=1)
        soh_layout.addWidget(self.soh_diag_label)
        lv.addLayout(soh_layout)

        # --- 电池信息 ---
        info = QFrame()
        grid = QGridLayout(info)

        data = [
            ("电池温度", "36 ℃", "最高 42 ℃ / 最低 28 ℃"),
            ("电池电压", "48.6 V", "最高 50.2 V / 最低 44.8 V"),
            ("电池阻抗", "12 mΩ", "最高 18 mΩ / 最低 9 mΩ"),
        ]

        for i, (name, value, limit) in enumerate(data):
            # 左侧名称
            grid.addWidget(QLabel(name), i, 0)

            # 右侧：主值 + 小字
            value_layout = QHBoxLayout()

            val_label = QLabel(value)
            val_label.setFont(QFont("Arial", 12, QFont.Bold))

            limit_label = QLabel(f"({limit})")
            limit_label.setFont(QFont("Arial", 9))
            limit_label.setStyleSheet("color: gray;")

            value_layout.addWidget(val_label)
            value_layout.addWidget(limit_label)
            value_layout.addStretch()

            grid.addLayout(value_layout, i, 1)

        lv.addWidget(info)

        # --- 芯片信息栏 ---
        chip = QFrame()
        chip.setFrameShape(QFrame.StyledPanel)
        chip_layout = QGridLayout(chip)

        chip_layout.addWidget(QLabel("芯片地址"), 0, 0)
        chip_layout.addWidget(QLabel("0x1A"), 0, 1)

        chip_layout.addWidget(QLabel("芯片 ID"), 1, 0)
        chip_layout.addWidget(QLabel("BMS-CHIP-01"), 1, 1)

        chip_layout.addWidget(QLabel("芯片温度"), 2, 0)
        chip_layout.addWidget(QLabel("42 ℃"), 2, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(QPushButton("重置芯片"))
        btn_layout.addWidget(QPushButton("均衡开始"))

        chip_layout.addLayout(btn_layout, 3, 0, 1, 2)
        lv.addWidget(chip)

        lv.addStretch()

        # ================= 右侧 =================
        self.right = QWidget()
        self.right.setStyleSheet("background-color: #F3F3F3;")
        self.right_layout = QVBoxLayout(self.right)

        self.voltage = self.create_time_plot("电压", "V")
        self.temp = self.create_time_plot("温度", "℃")
        self.impedance = self.create_nyquist_plot()

        self.frames = [self.voltage, self.temp, self.impedance]
        self.restore_layout()

        main.addWidget(left)
        main.addWidget(self.right)

    # ================= 布局控制 =================
    def restore_layout(self):
        self.clear()
        self.expanded_frame = None
        self.soc_charge_label.show()
        self.soh_diag_label.show()
        for f in self.frames:
            f.expand_btn.setText("显示大图")
            self.right_layout.addWidget(f, stretch=1)

    def expand(self, frame):
        if self.expanded_frame == frame:
            self.restore_layout()
            return
        self.clear()
        self.expanded_frame = frame
        #self.soc_charge_label.hide()
        #self.soh_diag_label.hide()
        frame.expand_btn.setText("还原布局")
        self.right_layout.addWidget(frame, stretch=2)

        bottom = QHBoxLayout()
        for f in self.frames:
            if f != frame:
                f.expand_btn.setText("显示大图")
                bottom.addWidget(f, stretch=1)
        self.right_layout.addLayout(bottom, stretch=1)

    def clear(self):
        while self.right_layout.count():
            item = self.right_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
            elif item.layout():
                while item.layout().count():
                    w = item.layout().takeAt(0).widget()
                    if w:
                        w.setParent(None)

    # ================= 图表（不改） =================
    def create_time_plot(self, title, ylab):
        frame = QFrame()
        v = QVBoxLayout(frame)
        plot = pg.PlotWidget(title=title)
        plot.setLabel("left", ylab)
        plot.setLabel("bottom", "Time")
        plot.showGrid(x=True, y=True, alpha=0.2)
        x = np.arange(50)
        y = np.random.normal(0, 1, 50)
        plot.plot(x, y, pen=pg.mkPen("k", width=2))
        scatter = SnapScatterItem(x, y)
        plot.addItem(scatter)
        plot.addItem(scatter.text)

        btns = QHBoxLayout()
        expand = QPushButton("显示大图")
        expand.clicked.connect(lambda: self.expand(frame))
        frame.expand_btn = expand
        btns.addWidget(QPushButton("开始采集"))
        btns.addWidget(expand)
        btns.addStretch()

        v.addWidget(plot, stretch=1)
        v.addLayout(btns)
        return frame

    def create_nyquist_plot(self):
        frame = QFrame()
        v = QVBoxLayout(frame)
        plot = pg.PlotWidget(title="阻抗（奈奎斯特图）")
        plot.setLabel("left", "Im(Z)")
        plot.setLabel("bottom", "Re(Z)")
        plot.showGrid(x=True, y=True, alpha=0.2)
        t = np.linspace(0, np.pi, 40)
        re = 20 + 10 * np.cos(t)
        im = -10 * np.sin(t)
        plot.plot(re, im, pen=pg.mkPen("k", width=2))
        scatter = SnapScatterItem(re, im, "Re={:.2f}\nIm={:.2f}", 1.0)
        plot.addItem(scatter)
        plot.addItem(scatter.text)

        btns = QHBoxLayout()
        expand = QPushButton("显示大图")
        expand.clicked.connect(lambda: self.expand(frame))
        frame.expand_btn = expand
        btns.addWidget(QPushButton("开始采集"))
        btns.addWidget(expand)
        btns.addStretch()

        v.addWidget(plot, stretch=1)
        v.addLayout(btns)
        return frame

# ================= 主界面2：整体情况页 =================
class OverallStatusPage(QWidget):
    def __init__(self):
        super().__init__()

        main = QHBoxLayout(self)
        main.setStretch(0, 1)
        main.setStretch(1, 2)

        # ================= 左侧：统计信息 =================
        left = QWidget()
        lv = QVBoxLayout(left)

        title = QLabel("整体电池状态概览")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        lv.addWidget(title)

        summary = QLabel(
            "总电池数量：30\n"
            "总芯片数量：6"
        )
        summary.setFont(QFont("Arial", 11))
        lv.addWidget(summary)

        # 左侧两个环形图对齐
        gauge_layout = QGridLayout()
        gauge_layout.setHorizontalSpacing(20)
        gauge_layout.setVerticalSpacing(10)

        total_energy_gauge = CircularGauge("SoC", "总电量", 76)
        total_soh_gauge = CircularGauge("SoH", "健康状态", 88)

        total_energy_label = QLabel(
            "总剩余电量：22800 mAh\n"
            "最高电量：92% (3680 mAh)\n"
            "最低电量：48% (1920 mAh)"
        )
        total_energy_label.setFont(QFont("Arial", 9))
        total_energy_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        total_soh_label = QLabel(
            "整体诊断：系统健康。\n"
            "最高 SoH：96%\n"
            "最低 SoH：81%"
        )
        total_soh_label.setFont(QFont("Arial", 9))
        total_soh_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        gauge_layout.addWidget(total_energy_gauge, 0, 0)
        gauge_layout.addWidget(total_energy_label, 0, 1)
        gauge_layout.addWidget(total_soh_gauge, 1, 0)
        gauge_layout.addWidget(total_soh_label, 1, 1)
        gauge_layout.setColumnStretch(0, 1)
        gauge_layout.setColumnStretch(1, 2)

        lv.addLayout(gauge_layout)

        # ================= 温度、电压水平排列 =================
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(20)

        temp_label = QLabel(
            "温度统计：\n"
            "平均：34 ℃\n最高：41 ℃\n最低：27 ℃"
        )
        temp_label.setFont(QFont("Arial", 10))
        temp_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        volt_label = QLabel(
            "电压统计：\n"
            "平均：3.72 V\n最高：3.89 V\n最低：3.41 V"
        )
        volt_label.setFont(QFont("Arial", 10))
        volt_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        stats_layout.addWidget(temp_label)
        stats_layout.addWidget(volt_label)
        lv.addLayout(stats_layout)

        # ================= 状态信息 + 按钮 =================
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(5)
        # 信息标签纵向排列
        info_layout = QVBoxLayout()
        for text in ["软件版本：v1.2.3", "连接状态：已连接", "最后更新时间：2026-01-18 10:35"]:
            lbl = QLabel(text)
            lbl.setFont(QFont("Arial", 10))
            lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            info_layout.addWidget(lbl)

        bottom_layout.addLayout(info_layout)  # 加入水平布局的左侧
        bottom_layout.addStretch()

        # 按钮
        start_btn = QPushButton("开始定时监测")
        bottom_layout.addWidget(start_btn)

        lv.addSpacing(35)  # 高度15像素
        lv.addLayout(bottom_layout)

        lv.addStretch()
        main.addWidget(left)
        # ================= 右侧：2x2 四块方阵 =================
        right = QWidget()
        right_widget = QWidget()  # 外层 QWidget
        rv = QGridLayout(right_widget)  # QGridLayout 放在 QWidget 上
        rv.setSpacing(10)
        rv.setContentsMargins(0, 0, 0, 0)

        # 创建四个方阵
        soc_block = self.create_matrix_block(
            title="电量分布（SoC）",
            values=np.random.randint(40, 100, 30),
            show_charge=True,
            mode="SoC"
        )
        temp_block = self.create_matrix_block(
            title="温度分布（℃）",
            values=np.random.randint(25, 45, 30),
            show_charge=False,
            mode="Temp"
        )
        volt_block = self.create_matrix_block(
            title="电压分布（V）",
            values=np.random.randint(340, 390, 30),
            show_charge=False,
            mode="Volt"
        )
        soh_block = self.create_matrix_block(
            title="健康状态分布（SoH）",
            values=np.random.randint(75, 100, 30),
            show_charge=False,
            mode="SoH"
        )

        # 网格 2x2
        rv.addWidget(soc_block, 0, 0)
        rv.addWidget(temp_block, 0, 1)
        rv.addWidget(volt_block, 1, 0)
        rv.addWidget(soh_block, 1, 1)

        # 最后添加右侧 QWidget 到 main
        main.addWidget(right_widget)

    # ================= 方阵块 =================
    def create_matrix_block(self, title, values, show_charge=False, mode="SoC"):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(frame)
        v.setContentsMargins(2, 2, 2, 2)

        label = QLabel(title)
        label.setFont(QFont("Arial", 13, QFont.Bold))
        v.addWidget(label)

        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)

        # 每行 10 个
        for i, val in enumerate(values):
            cell = BatteryCell(
                value=val,
                charging=(show_charge and i % 4 == 0),
                mode=mode,
                name=f"电池{i + 1}"
            )
            grid.addWidget(cell, i // 10, i % 10)

        v.addLayout(grid)

        # 图例
        legend_text = "颜色说明：绿 → 正常    黄 → 偏高/偏低    红 → 异常"
        legend = QLabel(legend_text)
        legend.setStyleSheet("color: gray; font-size: 10px;")
        v.addWidget(legend)

        return frame

# ================= 主界面3 =================
class SettingUI(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)

        label = QLabel("配置情况（空白页）")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: gray; font-size: 16px;")

        layout.addStretch()
        layout.addWidget(label)
        layout.addStretch()


# ================= 单个电池图元（矮小+小凸起版） =================
class BatteryCell(QWidget):
    def __init__(self, value, charging=False, mode="", name=""):
        super().__init__()
        self.value = value
        self.charging = charging
        self.mode = mode  # "SoC" / "Temp" / "Volt" / "SoH"
        self.name = name  # 电池名称
        self.setFixedSize(14, 24)  # 电池宽14，高24

        # 启用鼠标追踪，否则 enterEvent 不会触发
        self.setMouseTracking(True)

    # 生成 tooltip 文本
    def get_tooltip_text(self):
        unit = ""
        if self.mode == "SoC": unit = " %"
        elif self.mode == "Volt": unit = " ×0.01 V"
        elif self.mode == "Temp": unit = " ℃"
        elif self.mode == "SoH": unit = " %"
        return f"<b>{self.name}</b><br>值：{self.value}{unit}"

    # 鼠标悬停事件
    def enterEvent(self, event):
        # 悬浮显示 tooltip，立即出现
        QToolTip.showText(QCursor.pos(), self.get_tooltip_text(), self)
        super().enterEvent(event)

    # 鼠标移出事件
    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)

    # 绘制电池
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # 默认绿色
        color = QColor("#2ECC71")

        # 根据模式和数值设置颜色
        if self.mode == "SoC":
            if self.value < 50:
                color = QColor("#E74C3C")
            elif self.value < 75:
                color = QColor("#F1C40F")
        elif self.mode == "Temp":
            if self.value < 25 or self.value > 42:
                color = QColor("#E74C3C")
            elif 25 <= self.value < 30 or 40 < self.value <= 42:
                color = QColor("#F1C40F")
        elif self.mode == "Volt":
            if self.value < 350 or self.value > 390:
                color = QColor("#E74C3C")
            elif 350 <= self.value < 360 or 380 < self.value <= 390:
                color = QColor("#F1C40F")
        elif self.mode == "SoH":
            if self.value < 80:
                color = QColor("#E74C3C")
            elif 80 <= self.value < 90:
                color = QColor("#F1C40F")

        # 绘制大长方体
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(2, 6, 10, 16, 2, 2)

        # 绘制上方小凸起
        p.drawRoundedRect(5, 3, 3, 2, 1, 1)
        a = 2
        # 绘制充电闪电（仅 SoC 模式）
        if self.charging and self.mode == "SoC":
            p.setPen(QPen(QColor("white"), 1))
            p.drawLine(7, 6+a, 5.5, 12+a)
            p.drawLine(7, 6+a, 6.5, 12+a)
            p.drawLine(5.5, 12+a, 9.5, 12+a)
            p.drawLine(8, 12+a, 7, 18+a)
            p.drawLine(9.5, 12+a, 7, 18+a)








if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

