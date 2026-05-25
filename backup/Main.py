# main.py
import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QTabWidget
from PySide6.QtCore import QTimer
from datetime import datetime

from bms_data import BMSData   # 假设外部存在，保留导入
from pages import BatteryMonitorUI, OverallStatusPage, SettingUI
from can_receiver import CANReceiver   # 新增导入


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.bms = BMSData()   # ⭐ 核心
        self.setWindowTitle("电池监控系统")
        self.resize(800, 600)

        main_layout = QVBoxLayout(self)

        # ===== 顶部导航栏（页签）=====
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        self.tabs.setMovable(False)

        self.single_page = BatteryMonitorUI()
        self.overall_page = OverallStatusPage()
        self.setting_page = SettingUI()

        self.tabs.addTab(self.overall_page, "整体情况")
        self.tabs.addTab(self.single_page, "单体监测")
        self.tabs.addTab(self.setting_page, "配置管理")

        main_layout.addWidget(self.tabs)

        # 信号连接：点击电池方块跳转
        self.overall_page.cellClicked.connect(self.jump_to_single_monitor)

        # ===== 启动 CAN 接收器 =====
        self.can_receiver = None
        try:
            self.can_receiver = CANReceiver()
            # 连接新信号：收到解码后的信号数据，刷新整体状态页
            self.can_receiver.data_updated.connect(self.on_can_data_updated)
            # 保留原信号：单纯通知有报文，用来更新时间（不管解码是否成功）
            self.can_receiver.message_received.connect(self.on_can_message_received)
        except Exception as e:
            print(f"无法启动 CAN 接收: {e}")

    def on_can_data_updated(self, signal_dict):
        """
        收到 DBC 解码后的信号字典，更新 OverallStatusPage 的数据并刷新显示。
        """
        data = self.overall_page.data
        updated = False

        # SOC 百分比 (DBC: EISPackSOC, unit: %)
        if 'EISPackSOC' in signal_dict:
            data.total_soc_percent = int(signal_dict['EISPackSOC'])  # 取整，保持 int 类型
            updated = True

        # SOH 百分比 (DBC: BatSOH, unit: %)
        if 'BatSOH' in signal_dict:
            data.total_soh_percent = int(signal_dict['BatSOH'])
            updated = True

        # 最高单体电压 (DBC: MaxCellVoltage, unit: mV → 转换为 V)
        if 'MaxCellVoltage' in signal_dict:
            data.max_voltage_v = signal_dict['MaxCellVoltage'] / 1000.0
            updated = True

        # 最低单体电压 (DBC: MinCellVoltage, unit: mV → V)
        if 'MinCellVoltage' in signal_dict:
            data.min_voltage_v = signal_dict['MinCellVoltage'] / 1000.0
            updated = True

        # 平均单体电压 (DBC: AveCellVoltage, unit: mV → V)
        if 'AveCellVoltage' in signal_dict:
            data.avg_voltage_v = signal_dict['AveCellVoltage'] / 1000.0
            updated = True

        if updated:
            self.overall_page.update_display()

    def on_can_message_received(self):
        """只要收到任意 CAN 报文（无论能否解码），都刷新最后更新时间"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.overall_page.update_last_update_time(now_str)

    def jump_to_single_monitor(self, battery_name):
        self.tabs.setCurrentWidget(self.single_page)
        print("跳转到实时监测页，电池：", battery_name)

    def closeEvent(self, event):
        """窗口关闭时停止 CAN 接收"""
        if self.can_receiver:
            self.can_receiver.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())