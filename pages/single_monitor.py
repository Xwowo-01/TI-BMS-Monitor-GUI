# pages/single_monitor.py

import sys
import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QGridLayout,
    QFrame,
    QComboBox,
    QSizePolicy
)

import pyqtgraph as pg

from widgets import CircularGauge, SnapScatterItem


# =========================================================
# 中文文本
# =========================================================

class UITextZH:

    WINDOW_TITLE = "电池监控系统"

    PAGE_TITLE = "实时监测(未完成)"

    # 电池组
    BATTERY_GROUP_A = "电池组 A（主电池）"
    BATTERY_GROUP_B = "电池组 B（备用）"
    BATTERY_GROUP_C = "电池组 C（动力）"
    BATTERY_GROUP_D = "电池组 D（测试）"
    BATTERY_GROUP_E = "电池组 E（扩展）"

    # SoC
    CHARGING_INFO = (
        "正在充电：是\n"
        "剩余容量：3280 mAh\n"
        "满充容量：4000 mAh"
    )

    # SoH
    BATTERY_DIAGNOSIS = "电池诊断：状态良好。"

    # 电池信息
    BATTERY_TEMP = "电池温度"
    BATTERY_VOLTAGE = "电池电压"
    BATTERY_IMPEDANCE = "电池阻抗"

    TEMP_LIMIT = "最高 42 ℃ / 最低 28 ℃"
    VOLT_LIMIT = "最高 50.2 V / 最低 44.8 V"
    IMP_LIMIT = "最高 18 mΩ / 最低 9 mΩ"

    # 芯片信息
    CHIP_ADDRESS = "芯片地址"
    CHIP_ID = "芯片 ID"
    CHIP_TEMP = "芯片温度"

    # 按钮
    RESET_CHIP = "重置芯片"
    START_BALANCE = "均衡开始"

    SHOW_BIG = "显示大图"
    RESTORE_LAYOUT = "还原布局"

    START_CAPTURE = "开始采集"

    # 图表
    VOLTAGE = "电压"
    TEMPERATURE = "温度"
    IMPEDANCE = "阻抗（奈奎斯特图）"

    TIME = "时间"

    # 仪表盘
    SOC_TITLE = "SoC"
    SOC_SUBTITLE = "荷电状态"
    SOH_TITLE = "SoH"
    SOH_SUBTITLE = "健康状态"


# =========================================================
# 英文文本
# =========================================================

class UITextEN:

    WINDOW_TITLE = "Battery Monitoring System"

    PAGE_TITLE = "Real-Time Monitor (undone)"

    # 电池组
    BATTERY_GROUP_A = "Battery Pack A (Main)"
    BATTERY_GROUP_B = "Battery Pack B (Backup)"
    BATTERY_GROUP_C = "Battery Pack C (Power)"
    BATTERY_GROUP_D = "Battery Pack D (Test)"
    BATTERY_GROUP_E = "Battery Pack E (Extended)"

    # SoC
    CHARGING_INFO = (
        "Charging: Yes\n"
        "Remaining Capacity: 3280 mAh\n"
        "Full Capacity: 4000 mAh"
    )

    # SoH
    BATTERY_DIAGNOSIS = "Battery Diagnosis: Healthy."

    # 电池信息
    BATTERY_TEMP = "Battery Temperature"
    BATTERY_VOLTAGE = "Battery Voltage"
    BATTERY_IMPEDANCE = "Battery Impedance"

    TEMP_LIMIT = "Max 42 ℃ / Min 28 ℃"
    VOLT_LIMIT = "Max 50.2 V / Min 44.8 V"
    IMP_LIMIT = "Max 18 mΩ / Min 9 mΩ"

    # 芯片信息
    CHIP_ADDRESS = "Chip Address"
    CHIP_ID = "Chip ID"
    CHIP_TEMP = "Chip Temperature"

    # 按钮
    RESET_CHIP = "Reset Chip"
    START_BALANCE = "Start Balancing"

    SHOW_BIG = "Expand"
    RESTORE_LAYOUT = "Restore"

    START_CAPTURE = "Start Capture"

    # 图表
    VOLTAGE = "Voltage"
    TEMPERATURE = "Temperature"
    IMPEDANCE = "Impedance (Nyquist)"

    TIME = "Time"

    # 仪表盘
    SOC_TITLE = "State of Charge"
    SOC_SUBTITLE = ""
    SOH_TITLE = "State of Health"
    SOH_SUBTITLE = ""


class BatteryMonitorUI(QWidget):

    def __init__(self):
        super().__init__()

        # 当前语言
        self.ui_text = UITextZH

        self.setWindowTitle(
            self.ui_text.WINDOW_TITLE
        )

        self.resize(800, 600)

        pg.setConfigOption("foreground", "k")
        pg.setConfigOption("background", "w")

        self.expanded_frame = None

        self.setup_ui()

    # =====================================================
    # UI
    # =====================================================

    def setup_ui(self):

        main = QHBoxLayout(self)

        main.setStretch(0, 1)
        main.setStretch(1, 3)

        # =================================================
        # LEFT
        # =================================================

        left = QWidget()

        lv = QVBoxLayout(left)

        # 标题
        self.title_label = QLabel(
            self.ui_text.PAGE_TITLE
        )

        self.title_label.setFont(
            QFont("Arial", 16, QFont.Bold)
        )

        lv.addWidget(self.title_label)

        # =================================================
        # 电池选择
        # =================================================

        self.battery_select = QComboBox()

        self.update_battery_combo()

        self.battery_select.setMinimumHeight(32)

        lv.addWidget(
            self.battery_select
        )

        # =================================================
        # SoC
        # =================================================

        soc_layout = QHBoxLayout()

        self.soc_charge_label = QLabel()
        self.soc_charge_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.soc_charge_label.setText(self.ui_text.CHARGING_INFO)

        self.soc_gauge = CircularGauge(
            self.ui_text.SOC_TITLE,  # 使用 UIText 常量
            self.ui_text.SOC_SUBTITLE,
            82
        )

        soc_layout.addWidget(self.soc_gauge)
        soc_layout.addWidget(self.soc_charge_label)
        soc_layout.addStretch()
        lv.addLayout(soc_layout)

        # =================================================
        # SoH
        # =================================================
        soh_layout = QHBoxLayout()

        self.soh_diag_label = QLabel(self.ui_text.BATTERY_DIAGNOSIS)
        self.soh_diag_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.soh_gauge = CircularGauge(
            self.ui_text.SOH_TITLE,  # 使用 UIText 常量
            self.ui_text.SOH_SUBTITLE,
            91
        )

        soh_layout.addWidget(self.soh_gauge)
        soh_layout.addWidget(self.soh_diag_label)
        soh_layout.addStretch()
        lv.addLayout(soh_layout)

        # =================================================
        # 电池信息
        # =================================================

        info = QFrame()

        grid = QGridLayout(info)

        self.info_data = [
            (
                self.ui_text.BATTERY_TEMP,
                "36 ℃",
                self.ui_text.TEMP_LIMIT
            ),
            (
                self.ui_text.BATTERY_VOLTAGE,
                "48.6 V",
                self.ui_text.VOLT_LIMIT
            ),
            (
                self.ui_text.BATTERY_IMPEDANCE,
                "12 mΩ",
                self.ui_text.IMP_LIMIT
            ),
        ]

        self.info_name_labels = []
        self.info_limit_labels = []

        for i, (name, value, limit) in enumerate(self.info_data):

            name_label = QLabel(name)

            self.info_name_labels.append(
                name_label
            )

            grid.addWidget(
                name_label,
                i,
                0
            )

            value_layout = QHBoxLayout()

            val_label = QLabel(value)

            val_label.setFont(
                QFont("Arial", 12, QFont.Bold)
            )

            limit_label = QLabel(
                f"({limit})"
            )

            limit_label.setFont(
                QFont("Arial", 9)
            )

            limit_label.setStyleSheet(
                "color: gray;"
            )

            self.info_limit_labels.append(
                limit_label
            )

            value_layout.addWidget(
                val_label
            )

            value_layout.addWidget(
                limit_label
            )

            value_layout.addStretch()

            grid.addLayout(
                value_layout,
                i,
                1
            )

        lv.addWidget(info)

        # =================================================
        # 芯片信息
        # =================================================

        chip = QFrame()

        chip.setFrameShape(
            QFrame.StyledPanel
        )

        chip_layout = QGridLayout(chip)

        self.chip_addr_label = QLabel(
            self.ui_text.CHIP_ADDRESS
        )

        self.chip_id_label = QLabel(
            self.ui_text.CHIP_ID
        )

        self.chip_temp_label = QLabel(
            self.ui_text.CHIP_TEMP
        )

        chip_layout.addWidget(
            self.chip_addr_label,
            0,
            0
        )

        chip_layout.addWidget(
            QLabel("0x1A"),
            0,
            1
        )

        chip_layout.addWidget(
            self.chip_id_label,
            1,
            0
        )

        chip_layout.addWidget(
            QLabel("BMS-CHIP-01"),
            1,
            1
        )

        chip_layout.addWidget(
            self.chip_temp_label,
            2,
            0
        )

        chip_layout.addWidget(
            QLabel("42 ℃"),
            2,
            1
        )

        btn_layout = QHBoxLayout()

        self.reset_btn = QPushButton(
            self.ui_text.RESET_CHIP
        )

        self.balance_btn = QPushButton(
            self.ui_text.START_BALANCE
        )

        btn_layout.addWidget(
            self.reset_btn
        )

        btn_layout.addWidget(
            self.balance_btn
        )

        chip_layout.addLayout(
            btn_layout,
            3,
            0,
            1,
            2
        )

        lv.addWidget(chip)

        lv.addStretch()

        # =================================================
        # RIGHT
        # =================================================

        self.right = QWidget()

        self.right.setStyleSheet(
            "background-color: #F3F3F3;"
        )

        self.right_layout = QVBoxLayout(
            self.right
        )

        self.voltage = self.create_time_plot(
            self.ui_text.VOLTAGE,
            "V"
        )

        self.temp = self.create_time_plot(
            self.ui_text.TEMPERATURE,
            "℃"
        )

        self.impedance = self.create_nyquist_plot()

        self.frames = [
            self.voltage,
            self.temp,
            self.impedance
        ]

        self.restore_layout()

        main.addWidget(left)
        main.addWidget(self.right)

    # =====================================================
    # 更新电池下拉框
    # =====================================================

    def update_battery_combo(self):

        self.battery_select.clear()

        self.battery_select.addItems([
            self.ui_text.BATTERY_GROUP_A,
            self.ui_text.BATTERY_GROUP_B,
            self.ui_text.BATTERY_GROUP_C,
            self.ui_text.BATTERY_GROUP_D,
            self.ui_text.BATTERY_GROUP_E
        ])

    # =====================================================
    # 语言切换
    # =====================================================

    def switch_language(self, language="zh"):

        if language == "en":

            self.ui_text = UITextEN

        else:

            self.ui_text = UITextZH

        self.retranslate_ui()

    # =====================================================
    # 刷新UI文本
    # =====================================================

    def retranslate_ui(self):

        self.setWindowTitle(
            self.ui_text.WINDOW_TITLE
        )

        self.title_label.setText(
            self.ui_text.PAGE_TITLE
        )

        self.update_battery_combo()

        self.soc_charge_label.setText(
            self.ui_text.CHARGING_INFO
        )

        self.soh_diag_label.setText(
            self.ui_text.BATTERY_DIAGNOSIS
        )

        info_titles = [
            self.ui_text.BATTERY_TEMP,
            self.ui_text.BATTERY_VOLTAGE,
            self.ui_text.BATTERY_IMPEDANCE
        ]

        info_limits = [
            self.ui_text.TEMP_LIMIT,
            self.ui_text.VOLT_LIMIT,
            self.ui_text.IMP_LIMIT
        ]

        for i in range(3):
            self.info_name_labels[i].setText(
                info_titles[i]
            )
            self.info_limit_labels[i].setText(
                f"({info_limits[i]})"
            )

        self.chip_addr_label.setText(
            self.ui_text.CHIP_ADDRESS
        )
        self.chip_id_label.setText(
            self.ui_text.CHIP_ID
        )
        self.chip_temp_label.setText(
            self.ui_text.CHIP_TEMP
        )

        self.reset_btn.setText(
            self.ui_text.RESET_CHIP
        )
        self.balance_btn.setText(
            self.ui_text.START_BALANCE
        )

        for frame in self.frames:
            if frame.expand_btn.text() in [
                UITextZH.SHOW_BIG,
                UITextEN.SHOW_BIG
            ]:
                frame.expand_btn.setText(
                    self.ui_text.SHOW_BIG
                )
            else:
                frame.expand_btn.setText(
                    self.ui_text.RESTORE_LAYOUT
                )
            frame.capture_btn.setText(
                self.ui_text.START_CAPTURE
            )

        # ---- 更新图表标题和轴标签 ----
        self.voltage.plot.setTitle(self.ui_text.VOLTAGE)
        self.voltage.plot.setLabel("bottom", self.ui_text.TIME)

        self.temp.plot.setTitle(self.ui_text.TEMPERATURE)
        self.temp.plot.setLabel("bottom", self.ui_text.TIME)

        self.impedance.plot.setTitle(self.ui_text.IMPEDANCE)

        # ★ 更新仪表盘文本
        self.soc_gauge.set_texts(
            self.ui_text.SOC_TITLE,
            self.ui_text.SOC_SUBTITLE
        )
        self.soh_gauge.set_texts(
            self.ui_text.SOH_TITLE,
            self.ui_text.SOH_SUBTITLE
        )

    # =====================================================
    # 布局控制
    # =====================================================

    def restore_layout(self):

        self.clear()

        self.expanded_frame = None

        self.soc_charge_label.show()

        self.soh_diag_label.show()

        for f in self.frames:

            f.expand_btn.setText(
                self.ui_text.SHOW_BIG
            )

            self.right_layout.addWidget(
                f,
                stretch=1
            )

    def expand(self, frame):

        if self.expanded_frame == frame:

            self.restore_layout()

            return

        self.clear()

        self.expanded_frame = frame

        frame.expand_btn.setText(
            self.ui_text.RESTORE_LAYOUT
        )

        self.right_layout.addWidget(
            frame,
            stretch=2
        )

        bottom = QHBoxLayout()

        for f in self.frames:

            if f != frame:

                f.expand_btn.setText(
                    self.ui_text.SHOW_BIG
                )

                bottom.addWidget(
                    f,
                    stretch=1
                )

        self.right_layout.addLayout(
            bottom,
            stretch=1
        )

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

    # =====================================================
    # 图表
    # =====================================================

    def create_time_plot(self, title, ylab):

        frame = QFrame()

        v = QVBoxLayout(frame)

        plot = pg.PlotWidget(title=title)

        plot.setLabel(
            "left",
            ylab
        )

        plot.setLabel(
            "bottom",
            self.ui_text.TIME
        )

        plot.showGrid(
            x=True,
            y=True,
            alpha=0.2
        )

        x = np.arange(50)

        y = np.random.normal(
            0,
            1,
            50
        )

        plot.plot(
            x,
            y,
            pen=pg.mkPen("#2ECC71", width=2)
        )

        scatter = SnapScatterItem(
            x,
            y,
            "value={:.2f}\ntime={:.2f}",
            1.0
        )

        plot.addItem(scatter)

        plot.addItem(scatter.text)

        btns = QHBoxLayout()

        expand = QPushButton(
            self.ui_text.SHOW_BIG
        )

        expand.clicked.connect(
            lambda: self.expand(frame)
        )

        frame.expand_btn = expand

        capture_btn = QPushButton(
            self.ui_text.START_CAPTURE
        )

        frame.capture_btn = capture_btn

        btns.addWidget(
            capture_btn
        )

        btns.addWidget(
            expand
        )

        btns.addStretch()

        v.addWidget(
            plot,
            stretch=1
        )

        v.addLayout(btns)

        # ★ 保存 plot 对象的引用，供语言切换时更新标题/轴标签
        frame.plot = plot

        return frame

    def create_nyquist_plot(self):

        frame = QFrame()

        v = QVBoxLayout(frame)

        plot = pg.PlotWidget(
            title=self.ui_text.IMPEDANCE
        )

        plot.setLabel(
            "left",
            "Im(Z)"
        )

        plot.setLabel(
            "bottom",
            "Re(Z)"
        )

        plot.showGrid(
            x=True,
            y=True,
            alpha=0.2
        )

        t = np.linspace(
            0,
            np.pi,
            40
        )

        re = 20 + 10 * np.cos(t)

        im = -10 * np.sin(t)

        plot.plot(
            re,
            im,
            pen=pg.mkPen("#2ECC71", width=2)
        )

        scatter = SnapScatterItem(
            re,
            im,
            "Re={:.2f}\nIm={:.2f}",
            1.0
        )

        plot.addItem(scatter)

        plot.addItem(scatter.text)

        btns = QHBoxLayout()

        expand = QPushButton(
            self.ui_text.SHOW_BIG
        )

        expand.clicked.connect(
            lambda: self.expand(frame)
        )

        frame.expand_btn = expand

        capture_btn = QPushButton(
            self.ui_text.START_CAPTURE
        )

        frame.capture_btn = capture_btn

        btns.addWidget(
            capture_btn
        )

        btns.addWidget(
            expand
        )

        btns.addStretch()

        v.addWidget(
            plot,
            stretch=1
        )

        v.addLayout(btns)

        # ★ 保存 plot 对象的引用
        frame.plot = plot

        return frame