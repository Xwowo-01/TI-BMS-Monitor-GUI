# pages/overall_status.py
import sys
import random
from datetime import datetime
from typing import List

import numpy as np
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QPainter
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QGridLayout,
    QFrame, QSizePolicy, QGraphicsDropShadowEffect
)
from PySide6.QtCharts import QChartView, QChart, QLineSeries, QValueAxis

from widgets import CircularGauge, BatteryCell, TrendChartWidget


class OverallStatusData:
    """存储整体状态页面的所有数据（含单体电池数组）"""

    def __init__(self):
        # 基础信息
        self.total_battery_count = 26
        self.total_chip_count = 1

        # 单体数据（各 26 个值）
        self.cell_soc: List[int] = []      # 电量百分比 0~100
        self.cell_temp: List[float] = []   # 温度 ℃
        self.cell_volt: List[float] = []   # 电压 (V)

        # 整体统计值（由单体数据计算得出）
        self.total_soc_percent = 0
        self.total_soh_percent = 88
        self.total_remaining_energy_mah = 0
        self.max_energy_percent = 0
        self.max_energy_mah = 0
        self.min_energy_percent = 0
        self.min_energy_mah = 0

        self.overall_diagnosis = "系统健康。"
        self.max_soh_percent = 96
        self.min_soh_percent = 81

        self.avg_temp_c = 0.0
        self.max_temp_c = 0.0
        self.min_temp_c = 0.0

        self.avg_voltage_v = 0.0
        self.max_voltage_v = 0.0
        self.min_voltage_v = 0.0

        # 系统信息
        self.software_version = "v1.2.3"
        self.connection_status = "已连接"
        self.last_update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 历史数据（用于折线图）
        self.soc_history: List[int] = []
        self.soh_history: List[int] = []
        self.max_history_len = 20

        self._randomize_cells()
        self._update_statistics_from_cells()
        self.add_current_to_history()

    def _randomize_cells(self):
        """生成随机单体电池数据"""
        self.cell_soc = [random.randint(40, 100) for _ in range(26)]
        self.cell_temp = [round(random.uniform(25.0, 45.0), 1) for _ in range(26)]
        # 电压范围 3.2V ~ 4.2V
        self.cell_volt = [round(random.uniform(3.2, 4.2), 2) for _ in range(26)]

    def _update_statistics_from_cells(self):
        """根据单体电池数据计算左侧面板所需的所有统计值"""
        avg_soc = sum(self.cell_soc) / len(self.cell_soc)
        self.total_soc_percent = round(avg_soc)
        self.max_energy_percent = max(self.cell_soc)
        self.min_energy_percent = min(self.cell_soc)

        nominal_cap_per_cell = 4000
        total_nominal_cap = nominal_cap_per_cell * self.total_battery_count
        self.total_remaining_energy_mah = int(total_nominal_cap * avg_soc / 100)
        self.max_energy_mah = int(nominal_cap_per_cell * self.max_energy_percent / 100)
        self.min_energy_mah = int(nominal_cap_per_cell * self.min_energy_percent / 100)

        self.avg_temp_c = round(sum(self.cell_temp) / len(self.cell_temp), 1)
        self.max_temp_c = max(self.cell_temp)
        self.min_temp_c = min(self.cell_temp)

        self.avg_voltage_v = round(sum(self.cell_volt) / len(self.cell_volt), 2)
        self.max_voltage_v = max(self.cell_volt)
        self.min_voltage_v = min(self.cell_volt)

        self.total_soh_percent = random.randint(75, 99)
        self.max_soh_percent = min(100, self.total_soh_percent + random.randint(0, 8))
        self.min_soh_percent = max(50, self.total_soh_percent - random.randint(0, 15))

        if self.min_energy_percent < 20:
            self.overall_diagnosis = "注意：部分电池电量过低"
        elif self.max_temp_c > 42:
            self.overall_diagnosis = "警告：存在电池温度过高"
        elif self.total_soh_percent < 80:
            self.overall_diagnosis = "提示：整体健康状态下降"
        else:
            self.overall_diagnosis = "系统健康。"

    def randomize(self):
        """随机生成全部新数据（模拟数据更新）"""
        self._randomize_cells()
        self._update_statistics_from_cells()

        self.software_version = f"v{random.randint(1,3)}.{random.randint(0,5)}.{random.randint(0,9)}"
        self.connection_status = random.choice(["已连接", "连接中", "离线"])
        self.last_update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.add_current_to_history()

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


class OverallStatusPage(QWidget):
    cellClicked = Signal(str)

    def __init__(self):
        super().__init__()
        self.data = OverallStatusData()

        self.soc_cells = []
        self.temp_cells = []
        self.volt_cells = []

        self._setup_ui()
        self.update_display()
        self.update_all_matrices()
        self.update_trend_chart()

    def _setup_ui(self):
        main = QHBoxLayout(self)
        main.setStretch(0, 1)
        main.setStretch(1, 2)

        # ================= 左侧统计面板 =================
        left = QWidget()
        lv = QVBoxLayout(left)

        title = QLabel("整体电池状态概览")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        lv.addWidget(title)

        self.summary_label = QLabel()
        self.summary_label.setFont(QFont("Arial", 11))
        lv.addWidget(self.summary_label)

        gauge_layout = QGridLayout()
        gauge_layout.setHorizontalSpacing(20)
        gauge_layout.setVerticalSpacing(10)

        self.total_energy_gauge = CircularGauge("SoC", "总电量", 0)
        self.total_soh_gauge = CircularGauge("SoH", "健康状态", 0)

        self.total_energy_label = QLabel()
        self.total_energy_label.setFont(QFont("Arial", 9))
        self.total_soh_label = QLabel()
        self.total_soh_label.setFont(QFont("Arial", 9))

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
        for text in ["软件版本", "连接状态", "最后更新时间"]:
            lbl = QLabel()
            lbl.setFont(QFont("Arial", 10))
            info_layout.addWidget(lbl)
            self.info_labels.append(lbl)

        bottom_layout.addLayout(info_layout)
        bottom_layout.addStretch()

        self.start_btn = QPushButton("开始定时监测")
        self.start_btn.clicked.connect(self.on_start_monitor)
        bottom_layout.addWidget(self.start_btn)

        lv.addSpacing(25)
        lv.addLayout(bottom_layout)
        lv.addStretch()
        main.addWidget(left)

        # ================= 右侧区域 =================
        right = QWidget()
        right_layout = QGridLayout(right)
        right_layout.setSpacing(12)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 1. SoC 矩阵
        soc_widget, self.soc_cells = self._create_matrix_block_with_cells(
            title="电量分布（SoC）",
            values=self.data.cell_soc,
            mode="SoC"
        )
        # 2. 温度矩阵
        temp_widget, self.temp_cells = self._create_matrix_block_with_cells(
            title="温度分布（℃）",
            values=self.data.cell_temp,
            mode="Temp"
        )
        # 3. 电压矩阵 —— 传入毫伏 (mV)
        volt_values_mv = [int(v * 1000) for v in self.data.cell_volt]   # V → mV
        volt_widget, self.volt_cells = self._create_matrix_block_with_cells(
            title="电压分布（mV）",
            values=volt_values_mv,
            mode="Volt"
        )
        # 4. 折线图
        self.trend_chart = TrendChartWidget()
        chart_widget = self.trend_chart

        right_layout.addWidget(soc_widget, 0, 0)
        right_layout.addWidget(temp_widget, 0, 1)
        right_layout.addWidget(volt_widget, 1, 0)
        right_layout.addWidget(chart_widget, 1, 1)

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

        label = QLabel(title)
        label.setFont(QFont("Arial", 13, QFont.Bold))
        layout.addWidget(label)

        grid = QGridLayout()
        grid.setSpacing(5)
        cells = []
        rows, cols = 4, 7   # 4行7列，容纳26个电池
        for idx in range(26):
            val = values[idx] if idx < len(values) else 0
            cell = BatteryCell(
                value=val,
                charging=False,
                mode=mode,
                name=f"电池{idx+1}"
            )
            row = idx // cols
            col = idx % cols
            grid.addWidget(cell, row, col)
            cells.append(cell)
            cell.clicked.connect(self.cellClicked.emit)

        layout.addLayout(grid)

        legend = QLabel("颜色说明：绿 → 正常    黄 → 偏高/偏低    红 → 异常")
        legend.setStyleSheet("color: gray; font-size: 10px; margin-top: 6px;")
        layout.addWidget(legend)

        return outer, cells

    def _create_trend_chart(self):
        self.soc_series = QLineSeries()
        self.soc_series.setName("整体 SoC (%)")
        self.soc_series.setColor(QColor(52, 152, 219))
        self.soh_series = QLineSeries()
        self.soh_series.setName("整体 SoH (%)")
        self.soh_series.setColor(QColor(46, 204, 113))

        chart = QChart()
        chart.addSeries(self.soc_series)
        chart.addSeries(self.soh_series)
        chart.setTitle("整体 SoC / SoH 趋势")
        chart.setAnimationOptions(QChart.SeriesAnimations)
        chart.setTheme(QChart.ChartThemeLight)

        axis_x = QValueAxis()
        axis_x.setTitleText("历史采样点 (最近→最旧)")
        axis_x.setLabelFormat("%d")
        axis_x.setRange(0, self.data.max_history_len)

        axis_y = QValueAxis()
        axis_y.setTitleText("百分比 (%)")
        axis_y.setRange(0, 100)

        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)

        self.soc_series.attachAxis(axis_x)
        self.soc_series.attachAxis(axis_y)
        self.soh_series.attachAxis(axis_x)
        self.soh_series.attachAxis(axis_y)

        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.Antialiasing)
        chart_view.setMinimumHeight(260)
        chart_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        frame = QFrame()
        frame.setStyleSheet("background-color: white; border-radius: 8px;")
        shadow = QGraphicsDropShadowEffect(frame)
        shadow.setBlurRadius(16)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 60))
        frame.setGraphicsEffect(shadow)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.addWidget(chart_view)
        return frame

    def update_display(self):
        self.summary_label.setText(
            f"<span style='color:green'>总电池数量：</span><span style='color:black'>{self.data.total_battery_count}</span><br>"
            f"<span style='color:green'>总芯片数量：</span><span style='color:black'>{self.data.total_chip_count}</span>"
        )
        self.total_energy_gauge.setValue(self.data.total_soc_percent)
        self.total_soh_gauge.setValue(self.data.total_soh_percent)

        self.total_energy_label.setText(
            f"<span style='color:green'>总剩余电量：</span><span style='color:black'>{self.data.total_remaining_energy_mah} mAh</span><br>"
            f"<span style='color:green'>最高电量：</span><span style='color:black'>{self.data.max_energy_percent}% ({self.data.max_energy_mah} mAh)</span><br>"
            f"<span style='color:green'>最低电量：</span><span style='color:black'>{self.data.min_energy_percent}% ({self.data.min_energy_mah} mAh)</span>"
        )
        self.total_soh_label.setText(
            f"<span style='color:green'>整体诊断：</span><span style='color:black'>{self.data.overall_diagnosis}</span><br>"
            f"<span style='color:green'>最高 SoH：</span><span style='color:black'>{self.data.max_soh_percent}%</span><br>"
            f"<span style='color:green'>最低 SoH：</span><span style='color:black'>{self.data.min_soh_percent}%</span>"
        )
        self.temp_label.setText(
            f"<span style='color:green'>温度统计：</span><br>"
            f"<span style='color:green'>平均：</span><span style='color:black'>{self.data.avg_temp_c} ℃</span><br>"
            f"<span style='color:green'>最高：</span><span style='color:black'>{self.data.max_temp_c} ℃</span><br>"
            f"<span style='color:green'>最低：</span><span style='color:black'>{self.data.min_temp_c} ℃</span>"
        )
        self.volt_label.setText(
            f"<span style='color:green'>电压统计：</span><br>"
            f"<span style='color:green'>平均：</span><span style='color:black'>{self.data.avg_voltage_v} V</span><br>"
            f"<span style='color:green'>最高：</span><span style='color:black'>{self.data.max_voltage_v} V</span><br>"
            f"<span style='color:green'>最低：</span><span style='color:black'>{self.data.min_voltage_v} V</span>"
        )
        self.info_labels[0].setText(
            f"<span style='color:gray'>软件版本：</span><span style='color:black'>{self.data.software_version}</span>"
        )
        self.info_labels[1].setText(
            f"<span style='color:gray'>连接状态：</span><span style='color:black'>{self.data.connection_status}</span>"
        )
        self.info_labels[2].setText(
            f"<span style='color:gray'>最后更新时间：</span><span style='color:black'>{self.data.last_update_time}</span>"
        )

    def update_all_matrices(self):
        # SoC 矩阵
        for idx, cell in enumerate(self.soc_cells):
            if idx < len(self.data.cell_soc):
                cell.setValue(self.data.cell_soc[idx])
        # 温度矩阵
        for idx, cell in enumerate(self.temp_cells):
            if idx < len(self.data.cell_temp):
                cell.setValue(self.data.cell_temp[idx])
        # 电压矩阵：将伏特转换为毫伏 (mV)
        for idx, cell in enumerate(self.volt_cells):
            if idx < len(self.data.cell_volt):
                cell.setValue(int(self.data.cell_volt[idx] * 1000))

    def update_trend_chart(self):
        """刷新双趋势图"""
        soc_hist = self.data.get_soc_history()
        soh_hist = self.data.get_soh_history()
        self.trend_chart.update_data(soc_hist, soh_hist, self.data.max_history_len)

    def update_last_update_time(self, time_str):
        self.data.last_update_time = time_str
        self.info_labels[2].setText(
            f"<span style='color:gray'>最后更新时间：</span><span style='color:black'>{time_str}</span>"
        )

    def on_start_monitor(self):
        self.data.randomize()
        self.update_display()
        self.update_all_matrices()
        self.update_trend_chart()