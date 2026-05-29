# pages/overall_status.py

import random
from datetime import datetime
from typing import List
from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QGridLayout,
    QFrame,
    QGraphicsDropShadowEffect
)
from widgets import CircularGauge, BatteryCell, TrendChartWidget

# 中文文本
class UITextZH:
    # 页面标题
    PAGE_TITLE = "整体电池状态概览"
    # 总览信息
    TOTAL_BATTERY_COUNT = "总电池数量"
    TOTAL_CHIP_COUNT = "总芯片数量"
    # 仪表盘
    SOC = "SoC"
    SOH = "SoH"
    TOTAL_ENERGY = "总电量"
    HEALTH_STATUS = "健康状态"
    # 容量
    TOTAL_CHARGE_CAPACITY = "总充电容量"
    TOTAL_DISCHARGE_CAPACITY = "总放电容量"
    # 诊断
    OVERALL_DIAGNOSIS = "整体诊断"
    FAULT_LEVEL = "故障等级"
    FAULT_CODE = "故障码"
    # 整包
    PACK_SOC = "整包SOC"
    PACK_SOH = "整包SOH"
    # 温度
    TEMP_STAT = "温度统计"
    TEMP_AVG = "平均"
    TEMP_MAX = "最高"
    TEMP_MIN = "最低"
    # 电压
    VOLT_STAT = "电压统计"
    VOLT_AVG = "平均"
    VOLT_MAX = "最高"
    VOLT_MIN = "最低"
    # 系统信息
    SOFTWARE_VERSION = "软件版本"
    CPU_USAGE = "CPU使用率"
    CONNECTION_STATUS = "连接状态"
    LAST_UPDATE_TIME = "最后更新时间"
    # 连接状态
    STATUS_CONNECTED = "已连接"
    STATUS_CONNECTING = "连接中"
    STATUS_DISCONNECTED = "未连接"
    STATUS_OFFLINE = "离线"
    # 诊断信息
    DIAG_SYSTEM_OK = "系统健康"
    DIAG_HIGH_TEMP = "警告：存在高温电池"
    DIAG_LOW_SOC = "警告：存在低电量电池"
    DIAG_LOW_SOH = "警告：电池健康状态下降"
    DIAG_OVER_TEMP = "严重告警：电池过温"
    # 随机模拟诊断
    DIAG_LOW_BATTERY = "注意：部分电池电量过低"
    DIAG_TEMP_HIGH = "警告：存在电池温度过高"
    DIAG_SOH_DROP = "提示：整体健康状态下降"
    # 矩阵标题
    MATRIX_SOC = "SoC电量分布（%）"
    MATRIX_TEMP = "温度分布（℃）"
    MATRIX_VOLT = "电压分布（mV）"
    # 图例
    LEGEND_TEXT = (
        "颜色说明：绿 → 正常 | 黄 → 轻微报警 <br>"
        "| 红 → 严重报警"
    )
    # 电池名称
    BATTERY_NAME = "电池"
    # 趋势图
    TREND_SOC = "整体 SoC (%)"
    TREND_SOH = "整体 SoH (%)"
    TREND_TITLE = "整体 SoC / SoH 趋势"
    TREND_X = "历史采样点 (最近→最旧)"
    TREND_Y = "百分比 (%)"

# English
class UITextEN:
    # 页面标题
    PAGE_TITLE = "Overall Battery Status"
    # 总览信息
    TOTAL_BATTERY_COUNT = "Total Battery Count"
    TOTAL_CHIP_COUNT = "Total Chip Count"
    # 仪表盘
    SOC = "State of Charge"
    SOH = "State of Health"
    TOTAL_ENERGY = ""
    HEALTH_STATUS = ""
    # 容量
    TOTAL_CHARGE_CAPACITY = "Total Charge Capacity"
    TOTAL_DISCHARGE_CAPACITY = "Total Discharge Capacity"
    # 诊断
    OVERALL_DIAGNOSIS = "Overall Diagnosis"
    FAULT_LEVEL = "Fault Level"
    FAULT_CODE = "Fault Code"
    # 整包
    PACK_SOC = "Pack SOC"
    PACK_SOH = "Pack SOH"
    # 温度
    TEMP_STAT = "Temperature Statistics"
    TEMP_AVG = "Average"
    TEMP_MAX = "Maximum"
    TEMP_MIN = "Minimum"
    # 电压
    VOLT_STAT = "Voltage Statistics"
    VOLT_AVG = "Average"
    VOLT_MAX = "Maximum"
    VOLT_MIN = "Minimum"
    # 系统信息
    SOFTWARE_VERSION = "Software Version"
    CPU_USAGE = "CPU Usage"
    CONNECTION_STATUS = "Connection Status"
    LAST_UPDATE_TIME = "Last Update Time"
    # 连接状态
    STATUS_CONNECTED = "Connected"
    STATUS_CONNECTING = "Connecting"
    STATUS_DISCONNECTED = "Disconnected"
    STATUS_OFFLINE = "Offline"
    # 诊断信息
    DIAG_SYSTEM_OK = "System Healthy"
    DIAG_HIGH_TEMP = "Warning: High Temperature Battery"
    DIAG_LOW_SOC = "Warning: Low Battery SOC"
    DIAG_LOW_SOH = "Warning: Battery SOH Decreased"
    DIAG_OVER_TEMP = "Critical Warning: Battery Overheated"
    # 随机模拟诊断
    DIAG_LOW_BATTERY = "Notice: Some Batteries Are Low"
    DIAG_TEMP_HIGH = "Warning: Battery Temperature High"
    DIAG_SOH_DROP = "Notice: Overall Health Declined"
    # 矩阵标题
    MATRIX_SOC = "SoC Distribution (%)"
    MATRIX_TEMP = "Temperature Distribution (℃)"
    MATRIX_VOLT = "Voltage Distribution (mV)"
    # 图例
    LEGEND_TEXT = (
        "Color Guide: Green → Normal | Yellow → Warning <br>"
        "| Red → Critical Error"
    )
    # 电池名称
    BATTERY_NAME = "Battery"
    # 趋势图
    TREND_SOC = "Overall SoC (%)"
    TREND_SOH = "Overall SoH (%)"
    TREND_TITLE = "Overall SoC / SoH Trend"
    TREND_X = "History Samples (Newest → Oldest)"
    TREND_Y = "Percentage (%)"

# 数据
class OverallStatusData:
    def __init__(self):
        self.total_battery_count = 0
        self.total_chip_count = 0
        self.cell_soc: List[int] = [0] * 26
        self.cell_temp: List[float] = [0.0] * 26
        self.cell_volt: List[float] = [0.0] * 26
        self.pack_soc = 0
        self.pack_soh = 0
        self.eis_pack_soc = 0
        self.eis_bat_soh = 0
        self.total_charge_capacity = 0
        self.total_discharge_capacity = 0
        self.total_soc_percent = 0
        self.total_soh_percent = 0
        self.total_remaining_energy_mah = 0
        self.max_energy_percent = 0
        self.max_energy_mah = 0
        self.min_energy_percent = 0
        self.min_energy_mah = 0
        self.overall_diagnosis = "--"
        self.max_soh_percent = 96
        self.min_soh_percent = 81
        self.avg_temp_c = 0.0
        self.max_temp_c = 0.0
        self.min_temp_c = 0.0
        self.avg_voltage_v = 0.0
        self.max_voltage_v = 0.0
        self.min_voltage_v = 0.0
        self.software_version = "v0.0.0"
        self.cpu_usage_percent = 0
        self.connection_status = "disconnected"
        self.last_update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.soc_history: List[int] = []
        self.soh_history: List[int] = []
        self.max_history_len = 20
        self.add_current_to_history()
        self.fault_code = -1
        self.fault_level = 0
    # 统计
    def recalculate_statistics(self):
        valid_soc = [v for v in self.cell_soc if v >= 0]
        if not valid_soc:
            self.overall_diagnosis = ""
            return
        self.max_energy_percent = max(valid_soc)
        self.min_energy_percent = min(valid_soc)
        nominal_cap_per_cell = 4000
        self.max_energy_mah = int(nominal_cap_per_cell * self.max_energy_percent / 100)
        self.min_energy_mah = int(nominal_cap_per_cell * self.min_energy_percent / 100)
        avg_soc = sum(valid_soc) / len(valid_soc)
        total_nominal_cap = (nominal_cap_per_cell * self.total_battery_count)
        self.total_remaining_energy_mah = int(total_nominal_cap * avg_soc / 100)
        valid_temp = [v for v in self.cell_temp if v > -50]
        if valid_temp:
            self.avg_temp_c = round(sum(valid_temp) / len(valid_temp),1)
            self.max_temp_c = round(max(valid_temp),1)
            self.min_temp_c = round(min(valid_temp),1)
        valid_volt = [v for v in self.cell_volt if v > 0]
        if valid_volt:
            self.avg_voltage_v = round(sum(valid_volt) / len(valid_volt),3)
            self.max_voltage_v = round(max(valid_volt),3)
            self.min_voltage_v = round(min(valid_volt),3)
        self.max_soh_percent = min(100,self.total_soh_percent + 3)
        self.min_soh_percent = max(0,self.total_soh_percent - 3)

    # 历史
    def add_current_to_history(self):
        self.soc_history.append(self.total_soc_percent)
        self.soh_history.append(self.total_soh_percent)
        if len(self.soc_history) > self.max_history_len:
            self.soc_history.pop(0)
        if len(self.soh_history) > self.max_history_len:
            self.soh_history.pop(0)

    def get_soc_history(self):
        return self.soc_history.copy()

    def get_soh_history(self):
        return self.soh_history.copy()

# 故障信息定义
FAULT_INFO = {
    0: {"diag_zh": "系统正常", "diag_en": "System Normal", "category": 0, "code": ""},
    1: {"diag_zh": "单体电压过压", "diag_en": "Cell Overvoltage", "category": 1, "code": "P1B0D17"},
    2: {"diag_zh": "单体电压过压", "diag_en": "Cell Overvoltage", "category": 2, "code": "P1B0E1C"},
    3: {"diag_zh": "单体电压过压", "diag_en": "Cell Overvoltage", "category": 3, "code": "P0DE717"},
    4: {"diag_zh": "单体电压欠压", "diag_en": "Cell Undervoltage", "category": 1, "code": "P1B0D16"},
    5: {"diag_zh": "单体电压欠压", "diag_en": "Cell Undervoltage", "category": 2, "code": "P1B0F1C"},
    6: {"diag_zh": "单体电压欠压", "diag_en": "Cell Undervoltage", "category": 3, "code": "P0DE616"},
    7: {"diag_zh": "单体压差过大", "diag_en": "Cell Voltage Difference", "category": 2, "code": "P1B3721"},
    8: {"diag_zh": "单体压差过大", "diag_en": "Cell Voltage Difference", "category": 3, "code": "P1B1000"},
    9: {"diag_zh": "总电压过高", "diag_en": "Total Voltage Over", "category": 2, "code": "P1B3922"},
    10: {"diag_zh": "总电压过高", "diag_en": "Total Voltage Over", "category": 3, "code": "P0B26A3"},
    11: {"diag_zh": "总电压过低", "diag_en": "Total Voltage Under", "category": 2, "code": "P1B3821"},
    12: {"diag_zh": "总电压过低", "diag_en": "Total Voltage Under", "category": 3, "code": "P0B25A2"},
    13: {"diag_zh": "电池温度过高", "diag_en": "Battery Temp High", "category": 2, "code": "P1B8C00"},
    14: {"diag_zh": "电池温度过高", "diag_en": "Battery Temp High", "category": 3, "code": "P1B4F4B"},
    15: {"diag_zh": "电池温度过低", "diag_en": "Battery Temp Low", "category": 2, "code": "P1B8C00"},
    16: {"diag_zh": "电池温度过低", "diag_en": "Battery Temp Low", "category": 3, "code": "P1B8D00"},
    17: {"diag_zh": "行车放电电流过大", "diag_en": "Discharge Current Over", "category": 1, "code": "P125022"},
    18: {"diag_zh": "行车放电电流过大", "diag_en": "Discharge Current Over", "category": 2, "code": "P125122"},
    19: {"diag_zh": "行车放电电流过大", "diag_en": "Discharge Current Over", "category": 3, "code": "P1B1901"},
    20: {"diag_zh": "SOC过低", "diag_en": "Low SOC", "category": 1, "code": "P1B3621"},
    21: {"diag_zh": "SOC过低", "diag_en": "Low SOC", "category": 2, "code": "P1B3A21"},
    22: {"diag_zh": "SOC过低", "diag_en": "Low SOC", "category": 3, "code": "P0A7D00"},
}
CATEGORY_TEXT_ZH = {1: "轻微报警", 2: "一般报警", 3: "严重报警"}
CATEGORY_TEXT_EN = {1: "Slight Alarm", 2: "General Alarm", 3: "Severe Alarm"}
CATEGORY_COLOR = {1: "#f9a825", 2: "#ff6d00", 3: "#d32f2f"}  # 黄, 橙, 红
class OverallStatusPage(QWidget):
    cellClicked = Signal(str)
    def __init__(self):
        super().__init__()
        self.ui_text = UITextZH
        self.data = OverallStatusData()
        self.soc_cells = []
        self.temp_cells = []
        self.volt_cells = []
        self._setup_ui()
        self.update_display()
        self.update_all_matrices()
        self.update_trend_chart()

    # 故障信息获取
    def get_fault_info(self):
        code = self.data.fault_code
        if code is None or code == -1:
            return ("--", 0, "")
        if code < 0 or code > 22:
            code = 0
        info = FAULT_INFO.get(code, FAULT_INFO[0])
        if self.ui_text == UITextEN:
            diag_desc = info["diag_en"]
        else:
            diag_desc = info["diag_zh"]
        return diag_desc, info["category"], info["code"]

    def get_category_text(self, category):
        """根据类别返回文本（当前语言）"""
        if category == 0:
            return ""
        if self.ui_text == UITextEN:
            return CATEGORY_TEXT_EN.get(category, "")
        else:
            return CATEGORY_TEXT_ZH.get(category, "")

    def get_category_color(self, category):
        return CATEGORY_COLOR.get(category, "black")

    # UI 构建
    def _setup_ui(self):
        main = QHBoxLayout(self)
        main.setStretch(0, 1)
        main.setStretch(1, 2)
        # LEFT
        left = QWidget()
        lv = QVBoxLayout(left)
        self.title_label = QLabel(self.ui_text.PAGE_TITLE)
        self.title_label.setFont(QFont("Arial", 16, QFont.Bold))
        lv.addWidget(self.title_label)
        self.summary_label = QLabel()
        self.summary_label.setFont(QFont("Arial", 11))
        lv.addWidget(self.summary_label)
        gauge_layout = QGridLayout()
        gauge_layout.setHorizontalSpacing(20)
        gauge_layout.setVerticalSpacing(10)
        self.total_energy_gauge = CircularGauge(self.ui_text.SOC, self.ui_text.TOTAL_ENERGY, 0)
        self.total_soh_gauge = CircularGauge(self.ui_text.SOH, self.ui_text.HEALTH_STATUS, 0)
        self.total_energy_label = QLabel()
        self.total_energy_label.setFont(QFont("Arial", 9))
        self.total_soh_label = QLabel()
        self.total_soh_label.setFont(QFont("Arial", 9))
        from PySide6.QtCore import Qt
        self.total_soh_label.setTextFormat(Qt.TextFormat.RichText)
        gauge_layout.addWidget(self.total_energy_gauge, 0, 0)
        gauge_layout.addWidget(self.total_energy_label, 0, 1)
        gauge_layout.addWidget(self.total_soh_gauge, 1, 0)
        gauge_layout.addWidget(self.total_soh_label, 1, 1)
        gauge_layout.setColumnStretch(0, 1)
        gauge_layout.setColumnStretch(1, 2)
        lv.addLayout(gauge_layout)
        stats_layout = QHBoxLayout()
        self.temp_label = QLabel()
        self.temp_label.setFont(QFont("Arial", 10))
        self.volt_label = QLabel()
        self.volt_label.setFont(QFont("Arial", 10))
        stats_layout.addWidget(self.temp_label)
        stats_layout.addWidget(self.volt_label)
        lv.addLayout(stats_layout)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: rgba(200,200,200,150);")
        lv.addWidget(line)
        bottom_layout = QHBoxLayout()
        info_layout = QVBoxLayout()
        self.info_labels = []
        for _ in range(4):
            lbl = QLabel()
            lbl.setFont(QFont("Arial", 10))
            info_layout.addWidget(lbl)
            self.info_labels.append(lbl)
        bottom_layout.addLayout(info_layout)
        bottom_layout.addStretch()
        lv.addSpacing(15)
        lv.addLayout(bottom_layout)
        lv.addStretch()
        main.addWidget(left)
        # RIGHT
        right = QWidget()
        right_layout = QGridLayout(right)
        right_layout.setSpacing(12)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.soc_widget, self.soc_cells = self._create_matrix_block_with_cells(
            title=self.ui_text.MATRIX_SOC, values=self.data.cell_soc, mode="SoC"
        )
        self.temp_widget, self.temp_cells = self._create_matrix_block_with_cells(
            title=self.ui_text.MATRIX_TEMP, values=self.data.cell_temp, mode="Temp"
        )
        volt_values_mv = [int(v * 1000) for v in self.data.cell_volt]
        self.volt_widget, self.volt_cells = self._create_matrix_block_with_cells(
            title=self.ui_text.MATRIX_VOLT, values=volt_values_mv, mode="Volt"
        )
        self.trend_chart = TrendChartWidget()
        right_layout.addWidget(self.soc_widget, 0, 0)
        right_layout.addWidget(self.temp_widget, 0, 1)
        right_layout.addWidget(self.volt_widget, 1, 0)
        right_layout.addWidget(self.trend_chart, 1, 1)
        right_layout.setRowStretch(0, 1)
        right_layout.setRowStretch(1, 1)
        right_layout.setColumnStretch(0, 1)
        right_layout.setColumnStretch(1, 1)
        main.addWidget(right)

    def _create_matrix_block_with_cells(self, title, values, mode="SoC"):
        outer = QFrame()
        outer.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 8px;
            }
        """)
        shadow = QGraphicsDropShadowEffect(outer)
        shadow.setBlurRadius(16)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 60))
        outer.setGraphicsEffect(shadow)
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(12, 12, 12, 12)
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 13, QFont.Bold))
        outer.title_label = title_label
        layout.addWidget(title_label)

        grid = QGridLayout()
        grid.setSpacing(5)
        cells = []
        rows, cols = 4, 7
        for idx in range(26):
            val = values[idx] if idx < len(values) else 0
            cell = BatteryCell(
                value=val,
                charging=False,
                mode=mode,
                name=f"{self.ui_text.BATTERY_NAME}{idx + 1}"
            )
            row = idx // cols
            col = idx % cols
            grid.addWidget(cell, row, col)
            cells.append(cell)
            cell.clicked.connect(self.cellClicked.emit)
        layout.addLayout(grid)
        legend = QLabel(self.ui_text.LEGEND_TEXT)
        legend.setStyleSheet("color: gray; font-size: 10px; margin-top: 6px;")
        outer.legend_label = legend
        layout.addWidget(legend)
        return outer, cells

    # 语言切换
    def switch_language(self, language="zh"):
        if language == "en":
            self.ui_text = UITextEN
        else:
            self.ui_text = UITextZH
        self.retranslate_ui()

    def retranslate_ui(self):
        self.title_label.setText(self.ui_text.PAGE_TITLE)
        self.total_energy_gauge.set_texts(self.ui_text.SOC, self.ui_text.TOTAL_ENERGY)
        self.total_soh_gauge.set_texts(self.ui_text.SOH, self.ui_text.HEALTH_STATUS)
        self.soc_widget.title_label.setText(self.ui_text.MATRIX_SOC)
        self.temp_widget.title_label.setText(self.ui_text.MATRIX_TEMP)
        self.volt_widget.title_label.setText(self.ui_text.MATRIX_VOLT)
        self.soc_widget.legend_label.setText(self.ui_text.LEGEND_TEXT)
        self.temp_widget.legend_label.setText(self.ui_text.LEGEND_TEXT)
        self.volt_widget.legend_label.setText(self.ui_text.LEGEND_TEXT)
        for idx, cell in enumerate(self.soc_cells):
            cell.name = f"{self.ui_text.BATTERY_NAME}{idx + 1}"
        for idx, cell in enumerate(self.temp_cells):
            cell.name = f"{self.ui_text.BATTERY_NAME}{idx + 1}"
        for idx, cell in enumerate(self.volt_cells):
            cell.name = f"{self.ui_text.BATTERY_NAME}{idx + 1}"
        self.update_display()
        self.trend_chart.switch_language("en" if self.ui_text == UITextEN else "zh")

    # ---------- 更新显示 ----------
    def update_display(self):
        # 顶部摘要
        self.summary_label.setText(
            f"<span style='color:green'>{self.ui_text.TOTAL_BATTERY_COUNT}：</span>"
            f"<span style='color:black'>{self.data.total_battery_count}</span><br>"
            f"<span style='color:green'>{self.ui_text.TOTAL_CHIP_COUNT}：</span>"
            f"<span style='color:black'>{self.data.total_chip_count}</span>"
        )
        # 仪表盘
        self.total_energy_gauge.setValue(self.data.eis_pack_soc)
        self.total_soh_gauge.setValue(self.data.eis_bat_soh)
        # 左侧下半部分（容量、诊断等）
        self.total_energy_label.setText(
            f"<span style='color:green'>{self.ui_text.TOTAL_CHARGE_CAPACITY}：</span>"
            f"<span style='color:black'>{self.data.total_charge_capacity} Ah</span><br>"
            f"<span style='color:green'>{self.ui_text.TOTAL_DISCHARGE_CAPACITY}：</span>"
            f"<span style='color:black'>{self.data.total_discharge_capacity} Ah</span><br>"
            f"<span style='color:green'>{self.ui_text.PACK_SOC}：</span>"
            f"<span style='color:black'>{self.data.pack_soc} %</span>"
        )
        # ========== 故障相关显示 ==========
        diag_desc, category, fault_code_str = self.get_fault_info()
        is_fault = (self.data.fault_code is not None and 1 <= self.data.fault_code <= 22)
        # 第一行：整体诊断
        diag_line = f"<span style='color:green'>{self.ui_text.OVERALL_DIAGNOSIS}：</span>"
        diag_line += f"<span style='color:black'>{diag_desc}</span>"
        # 第二行：故障等级
        level_line = ""
        if is_fault and category > 0:
            cat_text = self.get_category_text(category)
            color = self.get_category_color(category)
            level_line = f"<br><span style='color:green'>{self.ui_text.FAULT_LEVEL}：</span>"
            level_line += f"<span style='color:{color}'>{cat_text} - 等级{self.data.fault_level}</span>"
        # 第三行：故障码
        code_line = ""
        if is_fault and fault_code_str:
            code_line = f"<br><span style='color:green'>{self.ui_text.FAULT_CODE}：</span>"
            code_line += f"<span style='color:black'>{fault_code_str}</span>"
        # 第四行：Pack SOH
        soh_line = f"<br><span style='color:green'>{self.ui_text.PACK_SOH}：</span>"
        soh_line += f"<span style='color:black'>{self.data.pack_soh} %</span>"
        # 组合所有行
        self.total_soh_label.setText(diag_line + level_line + code_line + soh_line)
        # 温度电压统计
        self.temp_label.setText(
            f"<span style='color:green'>{self.ui_text.TEMP_STAT}：</span><br>"
            f"<span style='color:green'>{self.ui_text.TEMP_AVG}：</span>"
            f"<span style='color:black'>{self.data.avg_temp_c} ℃</span><br>"
            f"<span style='color:green'>{self.ui_text.TEMP_MAX}：</span>"
            f"<span style='color:black'>{self.data.max_temp_c} ℃</span><br>"
            f"<span style='color:green'>{self.ui_text.TEMP_MIN}：</span>"
            f"<span style='color:black'>{self.data.min_temp_c} ℃</span>"
        )
        self.volt_label.setText(
            f"<span style='color:green'>{self.ui_text.VOLT_STAT}：</span><br>"
            f"<span style='color:green'>{self.ui_text.VOLT_AVG}：</span>"
            f"<span style='color:black'>{self.data.avg_voltage_v} V</span><br>"
            f"<span style='color:green'>{self.ui_text.VOLT_MAX}：</span>"
            f"<span style='color:black'>{self.data.max_voltage_v} V</span><br>"
            f"<span style='color:green'>{self.ui_text.VOLT_MIN}：</span>"
            f"<span style='color:black'>{self.data.min_voltage_v} V</span>"
        )
        # 底部信息栏
        self.info_labels[0].setText(
            f"<span style='color:gray'>{self.ui_text.SOFTWARE_VERSION}：</span>"
            f"<span style='color:black'>{self.data.software_version}</span>"
        )
        self.info_labels[1].setText(
            f"<span style='color:gray'>{self.ui_text.CONNECTION_STATUS}：</span>"
            f"<span style='color:black'>{self.get_connection_status_text()}</span>"
        )
        self.info_labels[2].setText(
            f"<span style='color:gray'>{self.ui_text.CPU_USAGE}：</span>"
            f"<span style='color:black'>{self.data.cpu_usage_percent}%</span>"
        )
        self.info_labels[3].setText(
            f"<span style='color:gray'>{self.ui_text.LAST_UPDATE_TIME}：</span>"
            f"<span style='color:black'>{self.data.last_update_time}</span>"
        )

    def update_all_matrices(self):
        for idx, cell in enumerate(self.soc_cells):
            if idx < len(self.data.cell_soc):
                cell.setValue(self.data.cell_soc[idx])
        for idx, cell in enumerate(self.temp_cells):
            if idx < len(self.data.cell_temp):
                cell.setValue(self.data.cell_temp[idx])
        for idx, cell in enumerate(self.volt_cells):
            if idx < len(self.data.cell_volt):
                cell.setValue(int(self.data.cell_volt[idx] * 1000))

    def update_trend_chart(self):
        soc_hist = self.data.get_soc_history()
        soh_hist = self.data.get_soh_history()
        self.trend_chart.update_data(soc_hist, soh_hist, self.data.max_history_len)

    def update_last_update_time(self, time_str):
        self.data.last_update_time = time_str
        self.info_labels[3].setText(
            f"<span style='color:gray'>{self.ui_text.LAST_UPDATE_TIME}：</span>"
            f"<span style='color:black'>{time_str}</span>"
        )

    def on_start_monitor(self):
        self.update_display()
        self.update_all_matrices()
        self.update_trend_chart()

    def get_connection_status_text(self):
        status_map = {
            "connected": self.ui_text.STATUS_CONNECTED,
            "connecting": self.ui_text.STATUS_CONNECTING,
            "disconnected": self.ui_text.STATUS_DISCONNECTED,
            "offline": self.ui_text.STATUS_OFFLINE
        }
        return status_map.get(self.data.connection_status, self.ui_text.STATUS_DISCONNECTED)