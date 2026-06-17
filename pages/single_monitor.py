# pages/single_monitor.py
import sys
import random
from typing import List, Optional
from datetime import datetime
import numpy as np

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QGridLayout,
    QFrame,
    QGroupBox,
    QComboBox,
    QSizePolicy
)

import pyqtgraph as pg

from widgets import CircularGauge, SnapScatterItem

# ===================== 数据类 =====================
class SingleCellStatusData:
    """单电池监控数据，包含26个电池的所有状态及历史曲线数据"""
    def __init__(self):
        self.num_cells = 26
        self.max_history = 10000  # 最多保存10000个历史点

        # 当前实时数据
        self.cell_soc: List[int] = [0] * self.num_cells          # 0-100
        self.cell_remaining_cap: List[int] = [0] * self.num_cells # mAh
        self.cell_full_cap: List[int] = [4000] * self.num_cells   # 固定4000mAh
        self.cell_temp: List[float] = [0.0] * self.num_cells      # ℃
        self.cell_voltage: List[float] = [0.0] * self.num_cells   # V

        # 历史数据：每个电池一个列表，存储 (timestamp, value) 元组
        self.voltage_hist: List[List[tuple]] = [[] for _ in range(self.num_cells)]
        self.temp_hist: List[List[tuple]] = [[] for _ in range(self.num_cells)]

        # 采集状态（全局统一）
        self.vt_status = "idle"        # idle / running
        self.eis_status = "idle"       # idle / waiting / done
        self.vt_samples = 0
        self.vt_time_sec = 0
        self.record_start_time = None   # 记录开始时间戳（秒）
        self.recorded_count = 0         # 已记录样本点数

        # EIS 数据：每个电池一个列表，存储 (freq, real, imag)
        self.eis_data: List[List[tuple]] = [[] for _ in range(self.num_cells)]
        self.eis_finish_received = False
        self.eis_has_data = False

        # 初始化随机数据（当前值），实际项目中注释掉
        # self.randomize_data()

    # ---------- VT 历史记录 ----------
    def clear_history(self):
        """清空所有历史数据，重置记录状态"""
        for i in range(self.num_cells):
            self.voltage_hist[i].clear()
            self.temp_hist[i].clear()
        self.vt_samples = 0
        self.vt_time_sec = 0
        self.recorded_count = 0
        self.record_start_time = None

    def record_current_data(self, timestamp: float):
        """
        将当前所有电池的电压和温度添加到历史中
        :param timestamp: 当前时间戳（秒，从 epoch 开始）
        """
        if self.vt_status != "running":
            return  # 非采集状态不记录

        # 记录开始时间
        if self.record_start_time is None:
            self.record_start_time = timestamp

        # 计算经过时间（秒）
        self.vt_time_sec = round(timestamp - self.record_start_time, 1)
        self.vt_samples += 1

        # 将当前值添加到每个电池的历史
        for i in range(self.num_cells):
            # 电压
            self.voltage_hist[i].append((self.vt_time_sec, self.cell_voltage[i]))
            if len(self.voltage_hist[i]) > self.max_history:
                self.voltage_hist[i].pop(0)
            # 温度
            self.temp_hist[i].append((self.vt_time_sec, self.cell_temp[i]))
            if len(self.temp_hist[i]) > self.max_history:
                self.temp_hist[i].pop(0)

    # ---------- EIS 数据管理 ----------
    def clear_eis_data(self):
        """清空所有 EIS 数据，重置标志"""
        for i in range(self.num_cells):
            self.eis_data[i].clear()
        self.eis_finish_received = False
        self.eis_has_data = False

    def add_eis_point(self, cell_num: int, freq: float, real: float, imag: float) -> bool:
        """
        添加一个 EIS 数据点
        :param cell_num: 电池编号 1-26
        :param freq: 频率 (Hz)
        :param real: 实部
        :param imag: 虚部
        """
        idx = cell_num - 1
        if 0 <= idx < self.num_cells:
            self.eis_data[idx].append((freq, real, imag))
            self.eis_has_data = True
            return True
        return False

    def set_eis_finish(self):
        """标记 EIS 采集完成（收到 EISFinish=1）"""
        self.eis_finish_received = True

    def get_eis_data(self, cell_index: int) -> List[tuple]:
        """返回指定电池的 EIS 数据列表 [(freq, real, imag), ...]"""
        if 0 <= cell_index < self.num_cells:
            return self.eis_data[cell_index]
        return []

    # ---------- 随机数据生成（测试用，可忽略） ----------
    def randomize_data(self):
        """生成随机数据，模拟真实电池状态"""
        for i in range(self.num_cells):
            soc = random.randint(20, 95)
            self.cell_soc[i] = soc
            self.cell_remaining_cap[i] = int(self.cell_full_cap[i] * soc / 100)
            self.cell_temp[i] = round(random.uniform(20, 45), 1)
            self.cell_voltage[i] = round(random.uniform(3.2, 4.2), 3)

    def update_random(self):
        """随机更新所有电池数据（模拟实时变化）"""
        for i in range(self.num_cells):
            delta = random.randint(-3, 3)
            new_soc = max(0, min(100, self.cell_soc[i] + delta))
            self.cell_soc[i] = new_soc
            self.cell_remaining_cap[i] = int(self.cell_full_cap[i] * new_soc / 100)
            temp_delta = random.uniform(-0.5, 0.5)
            new_temp = max(15, min(50, self.cell_temp[i] + temp_delta))
            self.cell_temp[i] = round(new_temp, 1)
            volt_delta = random.uniform(-0.02, 0.02)
            new_volt = max(3.0, min(4.5, self.cell_voltage[i] + volt_delta))
            self.cell_voltage[i] = round(new_volt, 3)

    def add_bulk_data(self, timestamp: float, voltage_list: List[float], temp_list: List[float]):
        """
        一次性添加所有电池在某一时刻的电压和温度数据
        """
        if len(voltage_list) != self.num_cells or len(temp_list) != self.num_cells:
            raise ValueError("voltage_list and temp_list must have length 26")
        for i in range(self.num_cells):
            self.voltage_hist[i].append((timestamp, voltage_list[i]))
            if len(self.voltage_hist[i]) > self.max_history:
                self.voltage_hist[i].pop(0)
            self.temp_hist[i].append((timestamp, temp_list[i]))
            if len(self.temp_hist[i]) > self.max_history:
                self.temp_hist[i].pop(0)

    def get_voltage_history(self, cell_index: int) -> List[tuple]:
        if 0 <= cell_index < self.num_cells:
            return self.voltage_hist[cell_index]
        return []

    def get_temp_history(self, cell_index: int) -> List[tuple]:
        if 0 <= cell_index < self.num_cells:
            return self.temp_hist[cell_index]
        return []

# ===================== UI 文本 =====================
class UITextZH:
    WINDOW_TITLE = "电池监控系统"
    PAGE_TITLE = "实时监测(仅示例)"
    BATTERY_LABEL = "电池"
    CHARGING_INFO_CAP = "剩余容量"
    CHARGING_INFO_FULL = "满充容量"
    BATTERY_TEMP = "电池温度"
    BATTERY_VOLTAGE = "电池电压"
    VOLTAGE = "电压"
    TEMPERATURE = "温度"
    IMPEDANCE = "阻抗（奈奎斯特图）"
    TIME = "时间"
    SOC_TITLE = "SoC"
    SOC_SUBTITLE = "荷电状态"
    SHOW_BIG = "放大显示"
    RESTORE_LAYOUT = "还原布局"
    ACQ_VT_TITLE = "电压温度采集"
    ACQ_EIS_TITLE = "EIS采集"
    ACQ_STATUS_IDLE = "空闲"
    ACQ_STATUS_RUNNING = "持续采集中"
    ACQ_EIS_STATUS_WAITING = "等待结果中"
    ACQ_EIS_STATUS_RECEIVING = "结果接收中"
    ACQ_EIS_STATUS_DONE = "EIS采集完成"
    ACQ_SAMPLES = "样本点："
    ACQ_TIME = "时间："
    ACQ_STATUS_PREFIX = "状态："
    ACQ_BTN_START = "开始采集"
    ACQ_BTN_STOP = "停止采集"

class UITextEN:
    WINDOW_TITLE = "Battery Monitoring System"
    PAGE_TITLE = "Real-Time Monitor (Sample Only)"
    BATTERY_LABEL = "Battery"
    CHARGING_INFO_CAP = "Remaining Capacity"
    CHARGING_INFO_FULL = "Full Capacity"
    BATTERY_TEMP = "Battery Temperature"
    BATTERY_VOLTAGE = "Battery Voltage"
    VOLTAGE = "Voltage"
    TEMPERATURE = "Temperature"
    IMPEDANCE = "Impedance (Nyquist)"
    TIME = "Time"
    SOC_TITLE = "State of Charge"
    SOC_SUBTITLE = ""
    SHOW_BIG = "Expand"
    RESTORE_LAYOUT = "Restore"
    ACQ_VT_TITLE = "Voltage/Temp Acquisition"
    ACQ_EIS_TITLE = "EIS Acquisition"
    ACQ_STATUS_IDLE = "Idle"
    ACQ_STATUS_RUNNING = "Acquiring"
    ACQ_EIS_STATUS_WAITING = "Waiting for result"
    ACQ_EIS_STATUS_RECEIVING = "Receiving data"
    ACQ_EIS_STATUS_DONE = "EIS Completed"
    ACQ_SAMPLES = "Samples:"
    ACQ_TIME = "Time:"
    ACQ_STATUS_PREFIX = "Status:"
    ACQ_BTN_START = "Start"
    ACQ_BTN_STOP = "Stop"

# ===================== UI 主类 =====================
class BatteryMonitorUI(QWidget):
    def __init__(self):
        super().__init__()
        self.ui_text = UITextZH
        self.setWindowTitle(self.ui_text.WINDOW_TITLE)
        self.resize(800, 600)

        # 数据
        self.data = SingleCellStatusData()
        self.current_battery_index = 0  # 当前选中的电池索引

        # 图形设置
        pg.setConfigOption("foreground", "k")
        pg.setConfigOption("background", "w")

        self.expanded_frame = None
        self.setup_ui()

        # 更新初始显示
        self.on_battery_changed(0)

    def update_data_display(self):
        """更新左侧数据显示（圆环、信息、采集状态），不更新右侧图表"""
        idx = self.current_battery_index
        self.soc_gauge.setValue(self.data.cell_soc[idx])
        self.update_info_text(idx)
        self._update_acq_status()

    def setup_ui(self):
        main = QHBoxLayout(self)
        main.setStretch(0, 1)
        main.setStretch(1, 3)

        # ========== LEFT ==========
        left = QWidget()
        lv = QVBoxLayout(left)

        # 标题
        self.title_label = QLabel(self.ui_text.PAGE_TITLE)
        self.title_label.setFont(QFont("Arial", 16, QFont.Bold))
        lv.addWidget(self.title_label)

        # 电池选择
        self.battery_select = QComboBox()
        self.update_battery_combo()
        self.battery_select.setMinimumHeight(32)
        self.battery_select.currentIndexChanged.connect(self.on_battery_changed)
        lv.addWidget(self.battery_select)

        # ---------- 圆环图 + 信息（垂直居中） ----------
        soc_container = QWidget()
        soc_container_layout = QVBoxLayout(soc_container)
        soc_container_layout.setAlignment(Qt.AlignCenter)

        self.soc_gauge = CircularGauge(
            self.ui_text.SOC_TITLE,
            self.ui_text.SOC_SUBTITLE,
            0
        )
        soc_container_layout.addWidget(self.soc_gauge, alignment=Qt.AlignCenter)

        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.info_label.setTextFormat(Qt.RichText)
        self.info_label.setStyleSheet("font-size: 10pt;")
        soc_container_layout.addWidget(self.info_label, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        lv.addWidget(soc_container)
        lv.addStretch()

        # ---------- 采集控制卡片 ----------
        acq_card = QFrame()
        acq_card.setFrameShape(QFrame.StyledPanel)
        acq_card.setStyleSheet("QFrame { background-color: #f9f9f9; border: 1px solid #d0d0d0; border-radius: 4px; }")
        acq_layout = QVBoxLayout(acq_card)

        # 电压温度采集
        vt_group = QGroupBox(self.ui_text.ACQ_VT_TITLE)
        vt_layout = QVBoxLayout(vt_group)

        status_layout = QHBoxLayout()
        self.vt_status_prefix_label = QLabel(self.ui_text.ACQ_STATUS_PREFIX)
        self.vt_status_label = QLabel(self.ui_text.ACQ_STATUS_IDLE)
        status_layout.addWidget(self.vt_status_prefix_label)
        status_layout.addWidget(self.vt_status_label)
        status_layout.addStretch()
        vt_layout.addLayout(status_layout)

        data_layout = QHBoxLayout()
        self.vt_samples_prefix_label = QLabel(self.ui_text.ACQ_SAMPLES)
        self.vt_samples_label = QLabel("0")
        self.vt_time_prefix_label = QLabel(self.ui_text.ACQ_TIME)
        self.vt_time_label = QLabel("0 s")
        data_layout.addWidget(self.vt_samples_prefix_label)
        data_layout.addWidget(self.vt_samples_label)
        data_layout.addSpacing(20)
        data_layout.addWidget(self.vt_time_prefix_label)
        data_layout.addWidget(self.vt_time_label)
        data_layout.addStretch()
        vt_layout.addLayout(data_layout)

        btn_layout = QHBoxLayout()
        self.vt_start_btn = QPushButton(self.ui_text.ACQ_BTN_START)
        self.vt_stop_btn = QPushButton(self.ui_text.ACQ_BTN_STOP)
        self.vt_stop_btn.setEnabled(False)
        btn_layout.addWidget(self.vt_start_btn)
        btn_layout.addWidget(self.vt_stop_btn)
        btn_layout.addStretch()
        vt_layout.addLayout(btn_layout)

        acq_layout.addWidget(vt_group)

        # EIS采集
        eis_group = QGroupBox(self.ui_text.ACQ_EIS_TITLE)
        eis_layout = QVBoxLayout(eis_group)

        status_layout_eis = QHBoxLayout()
        self.eis_status_prefix_label = QLabel(self.ui_text.ACQ_STATUS_PREFIX)
        self.eis_status_label = QLabel(self.ui_text.ACQ_STATUS_IDLE)
        status_layout_eis.addWidget(self.eis_status_prefix_label)
        status_layout_eis.addWidget(self.eis_status_label)
        status_layout_eis.addStretch()
        eis_layout.addLayout(status_layout_eis)

        btn_layout_eis = QHBoxLayout()
        self.eis_start_btn = QPushButton(self.ui_text.ACQ_BTN_START)
        self.eis_stop_btn = QPushButton(self.ui_text.ACQ_BTN_STOP)
        self.eis_stop_btn.setEnabled(False)
        btn_layout_eis.addWidget(self.eis_start_btn)
        btn_layout_eis.addWidget(self.eis_stop_btn)
        btn_layout_eis.addStretch()
        eis_layout.addLayout(btn_layout_eis)

        acq_layout.addWidget(eis_group)

        lv.addWidget(acq_card)

        # ========== RIGHT ==========
        self.right = QWidget()
        self.right.setStyleSheet("background-color: #F3F3F3;")
        self.right_layout = QVBoxLayout(self.right)

        # 电压图、温度图、阻抗图
        self.voltage_frame = self.create_time_plot(self.ui_text.VOLTAGE, "V")
        self.temp_frame = self.create_time_plot(self.ui_text.TEMPERATURE, "℃")
        self.impedance_frame = self.create_nyquist_plot()

        self.frames = [self.voltage_frame, self.temp_frame, self.impedance_frame]
        self.restore_layout()

        main.addWidget(left)
        main.addWidget(self.right)

        # 按钮信号连接
        self.vt_start_btn.clicked.connect(self.on_vt_start)
        self.vt_stop_btn.clicked.connect(self.on_vt_stop)
        self.eis_start_btn.clicked.connect(self.on_eis_start)
        self.eis_stop_btn.clicked.connect(self.on_eis_stop)

    # ---------- 数据添加与图形刷新（外部接口） ----------
    def add_bulk_data(self, timestamp: float, voltage_list: List[float], temp_list: List[float]):
        """外部调用，一次性添加所有电池的电压和温度数据"""
        self.data.add_bulk_data(timestamp, voltage_list, temp_list)

    def refresh_plots(self):
        """外部调用，刷新图形显示（使用当前选中的电池数据）"""
        self.update_plot_for_cell(self.current_battery_index)

    # ---------- EIS 数据接收（外部接口） ----------
    def receive_eis_point(self, cell_num: int, freq: float, real: float, imag: float):
        """
        接收一个 EIS 数据点，由 main 在解析 CAN 报文时调用
        """
        if self.data.eis_status != "waiting":
            return
        self.data.add_eis_point(cell_num, freq, real, imag)
        # 不更新图形，等待完成时统一更新

    def on_eis_finish(self):
        """收到 EISFinish=1 时调用，完成采集"""
        if self.data.eis_status == "waiting":
            self.data.set_eis_finish()
            self.data.eis_status = "done"
            self._update_acq_status()
            # 更新当前电池阻抗图
            self.update_impedance_plot(self.current_battery_index)

    # ---------- 图形更新方法 ----------
    def update_plot_for_cell(self, cell_index: int):
        """更新电压和温度图的数据曲线（显示指定电池的历史数据）"""
        # 电压图
        hist = self.data.get_voltage_history(cell_index)
        if hist:
            times, vals = zip(*hist)
            self.voltage_frame.plot.curve.setData(times, vals)
        else:
            self.voltage_frame.plot.curve.setData([], [])

        # 温度图
        hist = self.data.get_temp_history(cell_index)
        if hist:
            times, vals = zip(*hist)
            self.temp_frame.plot.curve.setData(times, vals)
        else:
            self.temp_frame.plot.curve.setData([], [])

    def update_impedance_plot(self, cell_index: int = None):
        """更新奈奎斯特图（显示指定电池的 EIS 数据）"""
        if cell_index is None:
            cell_index = self.current_battery_index
        data = self.data.get_eis_data(cell_index)
        if data:
            reals = [p[1] for p in data]
            imags = [p[2] for p in data]
            self.impedance_frame.plot.curve.setData(reals, imags)
        else:
            self.impedance_frame.plot.curve.setData([], [])

    # ---------- 更新显示 ----------
    def update_display(self):
        """刷新所有UI显示（圆环、信息、采集状态等）"""
        self.on_battery_changed(self.current_battery_index)
        self._update_acq_status()

    def _update_acq_status(self):
        """根据数据类中的状态更新采集卡片"""
        # VT状态
        vt_status = self.data.vt_status
        if vt_status == "idle":
            self.vt_status_label.setText(self.ui_text.ACQ_STATUS_IDLE)
            self.vt_start_btn.setEnabled(True)
            self.vt_stop_btn.setEnabled(False)
        elif vt_status == "running":
            self.vt_status_label.setText(self.ui_text.ACQ_STATUS_RUNNING)
            self.vt_start_btn.setEnabled(False)
            self.vt_stop_btn.setEnabled(True)

        self.vt_samples_label.setText(str(self.data.vt_samples))
        self.vt_time_label.setText(f"{self.data.vt_time_sec} s")

        # EIS状态
        eis_status = self.data.eis_status
        if eis_status == "idle":
            self.eis_status_label.setText(self.ui_text.ACQ_STATUS_IDLE)
            self.eis_start_btn.setEnabled(True)
            self.eis_stop_btn.setEnabled(False)
        elif eis_status == "waiting":
            if self.data.eis_has_data:
                self.eis_status_label.setText(self.ui_text.ACQ_EIS_STATUS_RECEIVING)
            else:
                self.eis_status_label.setText(self.ui_text.ACQ_EIS_STATUS_WAITING)
            self.eis_start_btn.setEnabled(False)
            self.eis_stop_btn.setEnabled(True)
        elif eis_status == "done":
            self.eis_status_label.setText(self.ui_text.ACQ_EIS_STATUS_DONE)
            self.eis_start_btn.setEnabled(True)
            self.eis_stop_btn.setEnabled(False)

    # ---------- 采集控制槽函数 ----------
    def on_vt_start(self):
        """开始采集：清空历史，开始记录"""
        self.data.clear_history()
        self.data.vt_status = "running"
        self.data.record_start_time = None
        self._update_acq_status()

    def on_vt_stop(self):
        """停止采集：仅改变状态，保留已采集数据"""
        self.data.vt_status = "idle"
        self._update_acq_status()

    def on_eis_start(self):
        """开始 EIS 采集：清空旧数据，等待接收"""
        self.data.clear_eis_data()
        self.data.eis_status = "waiting"
        self._update_acq_status()
        self.impedance_frame.plot.curve.setData([], [])  # 清空图形

    def on_eis_stop(self):
        """手动停止 EIS 采集：回到空闲状态，保留已接收数据（可查看）"""
        self.data.eis_status = "idle"
        self._update_acq_status()

    # ---------- 电池选择与信息更新 ----------
    def on_battery_changed(self, index):
        self.current_battery_index = index
        soc = self.data.cell_soc[index]
        self.soc_gauge.setValue(soc)
        self.update_info_text(index)
        self.update_plot_for_cell(index)
        self.update_impedance_plot(index)

    def update_info_text(self, index=None):
        if index is None:
            index = self.current_battery_index
        data = self.data
        html = (
            f'<span style="font-size:10pt;">'
            f'{self.ui_text.CHARGING_INFO_CAP}：<b>{data.cell_remaining_cap[index]} mAh</b><br>'
            f'{self.ui_text.CHARGING_INFO_FULL}：<b>{data.cell_full_cap[index]} mAh</b><br>'
            f'{self.ui_text.BATTERY_TEMP}：<b>{data.cell_temp[index]} ℃</b><br>'
            f'{self.ui_text.BATTERY_VOLTAGE}：<b>{data.cell_voltage[index]:.3f} V</b>'
            f'</span>'
        )
        self.info_label.setText(html)

    def update_battery_combo(self):
        self.battery_select.clear()
        label = self.ui_text.BATTERY_LABEL
        items = [f"{label}{i}" for i in range(1, 27)]
        self.battery_select.addItems(items)

    # ---------- 语言切换 ----------
    def switch_language(self, language="zh"):
        if language == "en":
            self.ui_text = UITextEN
        else:
            self.ui_text = UITextZH
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(self.ui_text.WINDOW_TITLE)
        self.title_label.setText(self.ui_text.PAGE_TITLE)
        self.update_battery_combo()
        self.battery_select.setCurrentIndex(self.current_battery_index)
        self.update_info_text()

        # 更新采集卡片文本
        for child in self.findChildren(QGroupBox):
            title = child.title()
            if title in (UITextZH.ACQ_VT_TITLE, UITextEN.ACQ_VT_TITLE):
                child.setTitle(self.ui_text.ACQ_VT_TITLE)
            elif title in (UITextZH.ACQ_EIS_TITLE, UITextEN.ACQ_EIS_TITLE):
                child.setTitle(self.ui_text.ACQ_EIS_TITLE)

        self.vt_status_prefix_label.setText(self.ui_text.ACQ_STATUS_PREFIX)
        self.eis_status_prefix_label.setText(self.ui_text.ACQ_STATUS_PREFIX)
        self.vt_samples_prefix_label.setText(self.ui_text.ACQ_SAMPLES)
        self.vt_time_prefix_label.setText(self.ui_text.ACQ_TIME)

        self.vt_start_btn.setText(self.ui_text.ACQ_BTN_START)
        self.vt_stop_btn.setText(self.ui_text.ACQ_BTN_STOP)
        self.eis_start_btn.setText(self.ui_text.ACQ_BTN_START)
        self.eis_stop_btn.setText(self.ui_text.ACQ_BTN_STOP)

        for frame in self.frames:
            if self.expanded_frame == frame:
                frame.expand_btn.setText(self.ui_text.RESTORE_LAYOUT)
            else:
                frame.expand_btn.setText(self.ui_text.SHOW_BIG)

        self.voltage_frame.plot.setTitle(self.ui_text.VOLTAGE)
        self.voltage_frame.plot.setLabel("bottom", self.ui_text.TIME)
        self.temp_frame.plot.setTitle(self.ui_text.TEMPERATURE)
        self.temp_frame.plot.setLabel("bottom", self.ui_text.TIME)
        self.impedance_frame.plot.setTitle(self.ui_text.IMPEDANCE)

        self.soc_gauge.set_texts(
            self.ui_text.SOC_TITLE,
            self.ui_text.SOC_SUBTITLE
        )

        self._update_acq_status()
        self.update_plot_for_cell(self.current_battery_index)
        self.update_impedance_plot(self.current_battery_index)

    # ---------- 布局管理 ----------
    def restore_layout(self):
        self.clear()
        self.expanded_frame = None
        for f in self.frames:
            f.expand_btn.setText(self.ui_text.SHOW_BIG)
            self.right_layout.addWidget(f, stretch=1)

    def expand(self, frame):
        if self.expanded_frame == frame:
            self.restore_layout()
            return
        self.clear()
        self.expanded_frame = frame
        frame.expand_btn.setText(self.ui_text.RESTORE_LAYOUT)
        self.right_layout.addWidget(frame, stretch=2)
        bottom = QHBoxLayout()
        for f in self.frames:
            if f != frame:
                f.expand_btn.setText(self.ui_text.SHOW_BIG)
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

    # ---------- 创建图表 ----------
    def create_time_plot(self, title, ylab):
        """创建时间曲线图（电压/温度）"""
        frame = QFrame()
        v = QVBoxLayout(frame)
        plot = pg.PlotWidget(title=title)
        plot.setLabel("left", ylab)
        plot.setLabel("bottom", self.ui_text.TIME)
        plot.showGrid(x=True, y=True, alpha=0.2)

        curve = plot.plot([], [], pen=pg.mkPen("#2ECC71", width=2))
        plot.curve = curve

        btns = QHBoxLayout()
        expand = QPushButton(self.ui_text.SHOW_BIG)
        expand.clicked.connect(lambda: self.expand(frame))
        frame.expand_btn = expand
        btns.addWidget(expand)
        btns.addStretch()
        v.addWidget(plot, stretch=1)
        v.addLayout(btns)

        frame.plot = plot
        return frame

    def create_nyquist_plot(self):
        """奈奎斯特图（动态更新）"""
        frame = QFrame()
        v = QVBoxLayout(frame)
        plot = pg.PlotWidget(title=self.ui_text.IMPEDANCE)
        plot.setLabel("left", "Im(Z)")
        plot.setLabel("bottom", "Re(Z)")
        plot.showGrid(x=True, y=True, alpha=0.2)

        # 空曲线，带符号点
        curve = plot.plot([], [], pen=pg.mkPen("#2ECC71", width=2), symbol='o', symbolSize=6, symbolBrush='b')
        plot.curve = curve

        btns = QHBoxLayout()
        expand = QPushButton(self.ui_text.SHOW_BIG)
        expand.clicked.connect(lambda: self.expand(frame))
        frame.expand_btn = expand
        btns.addWidget(expand)
        btns.addStretch()
        v.addWidget(plot, stretch=1)
        v.addLayout(btns)

        frame.plot = plot
        return frame