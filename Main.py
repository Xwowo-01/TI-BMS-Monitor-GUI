# main.py
import can
import can.interfaces.vector  # 显式导入，解决打包问题
from PySide6.QtCore import QSettings, QTimer
import os
import sys
import time
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QTabWidget
)
from pages import (
    BatteryMonitorUI,
    OverallStatusPage,
    SettingUI,
    BootloaderPage
)
from can_receiver import CANReceiver
from language_manager import language_manager
import sys
import os

def resource_path(relative_path):
    """兼容 PyInstaller"""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# 中文文本
class UITextZH:
    WINDOW_TITLE = "电池监控系统"
    TAB_OVERVIEW = "整体情况"
    TAB_SINGLE = "单体监测"
    TAB_SETTING = "配置管理"
    TAB_BOOTLOADER = "程序刷写"
    STATUS_CONNECTED = "已连接"
    STATUS_OFFLINE = "离线"
    CAN_INIT_FAILED = "CAN 初始化失败"
    JUMP_TO_MONITOR = "跳转到实时监测页，电池"

# English
class UITextEN:
    WINDOW_TITLE = "Battery Monitoring System"
    TAB_OVERVIEW = "Overview"
    TAB_SINGLE = "Single Monitor"
    TAB_SETTING = "Settings"
    TAB_BOOTLOADER = "Bootloader"
    STATUS_CONNECTED = "Connected"
    STATUS_OFFLINE = "Offline"
    CAN_INIT_FAILED = "CAN initialization failed"
    JUMP_TO_MONITOR = "Jump to monitor page, battery"

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        from PySide6.QtGui import QIcon
        self.setWindowIcon(QIcon(resource_path("appicon.ico")))
        self.current_text = UITextZH
        settings = QSettings(
            "BatteryMonitor",
            "CANConfig"
        )
        saved_language = settings.value(
            "language",
            "zh"
        )
        if saved_language == "en":
            self.current_text = UITextEN
        else:
            self.current_text = UITextZH
        self.setWindowTitle(
            self.current_text.WINDOW_TITLE
        )
        self.resize(800, 600)
        main_layout = QVBoxLayout(self)
        # Tab
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        self.tabs.setMovable(False)
        self.single_page = BatteryMonitorUI()
        self.overall_page = OverallStatusPage()
        self.setting_page = SettingUI()
        self.bootloader_page = BootloaderPage()
        self.tabs.addTab(
            self.overall_page,
            self.current_text.TAB_OVERVIEW
        )
        self.tabs.addTab(
            self.single_page,
            self.current_text.TAB_SINGLE
        )
        self.tabs.addTab(
            self.setting_page,
            self.current_text.TAB_SETTING
        )
        self.tabs.addTab(
            self.bootloader_page,
            self.current_text.TAB_BOOTLOADER
        )
        main_layout.addWidget(self.tabs)
        # 语言切换监听
        language_manager.language_changed.connect(self.switch_language)
        # 初始化页面语言
        self.switch_language(saved_language)
        # 信号
        self.bootloader_page.starting_flash.connect(self.stop_can_for_flash)
        self.bootloader_page.finished_flash.connect( self.restart_can_after_flash)
        self.overall_page.cellClicked.connect(self.jump_to_single_monitor)
        self.setting_page.reconnect_requested.connect(self.reconnect_can)
        self.can_receiver = None
        # UI刷新限频
        self.last_history_update = 0
        self.ui_refresh_timer = QTimer()
        self.ui_refresh_timer.timeout.connect(self.refresh_ui)
        # 5FPS
        self.ui_refresh_timer.start(200)
        self.chart_refresh_timer = QTimer()
        self.chart_refresh_timer.timeout.connect(self.refresh_chart)
        # 趋势图 1FPS
        self.chart_refresh_timer.start(1000)
        # 初始化 CAN
        try:
            settings = QSettings( "BatteryMonitor","CANConfig")
            app_name = settings.value("app_name","VectorTest")
            channel = int(settings.value("channel",0))
            arb_bitrate = int(settings.value("arb_bitrate",1000000))
            data_bitrate = int(settings.value("data_bitrate",1000000))
            self.dbc_path = resource_path("System3.dbc")
            self.can_receiver = CANReceiver(
                app_name=app_name,
                channel=channel,
                arb_bitrate=arb_bitrate,
                data_bitrate=data_bitrate,
                dbc_path=self.dbc_path
            )
            self.can_receiver.data_updated.connect(self.on_can_data_updated)
            self.can_receiver.message_received.connect(self.on_can_message_received)
            self.overall_page.update_display()
        except Exception as e:
            print(f"{self.current_text.CAN_INIT_FAILED}: {e}")
            self.overall_page.data.connection_status = ("offline")
            self.overall_page.update_display()

    # 语言切换
    def switch_language(self, language):
        if language == "en":
            self.current_text = UITextEN
        else:
            self.current_text = UITextZH
        self.update_ui_text()
        self.single_page.switch_language(language)
        self.bootloader_page.switch_language(language)
        self.overall_page.switch_language(language)

    # 更新 UI 文本
    def update_ui_text(self):
        self.setWindowTitle(self.current_text.WINDOW_TITLE)
        self.tabs.setTabText(0,self.current_text.TAB_OVERVIEW)
        self.tabs.setTabText(1,self.current_text.TAB_SINGLE)
        self.tabs.setTabText(2,self.current_text.TAB_SETTING)
        self.tabs.setTabText(3,self.current_text.TAB_BOOTLOADER)

    # 低频刷新UI
    def refresh_ui(self):
        try:
            self.overall_page.update_display()
            self.overall_page.update_all_matrices()
        except Exception as e:
            print(f"UI刷新错误: {e}")

    # 低频刷新趋势图
    def refresh_chart(self):
        try:
            self.overall_page.update_trend_chart()
        except Exception as e:
            print(f"趋势图刷新错误: {e}")

    # Bootloader 刷写前后 CAN 处理
    def stop_can_for_flash(self):
        if self.can_receiver:
            self.can_receiver.stop()
            self.can_receiver = None
            print("CAN 接收已停止，为刷写释放资源")

    def restart_can_after_flash(self, success):
        if success:
            dbc_path = self.dbc_path
            try:
                self.can_receiver = CANReceiver(dbc_path=dbc_path)
                self.can_receiver.data_updated.connect(self.on_can_data_updated)
                self.can_receiver.message_received.connect(self.on_can_message_received)
                self.overall_page.data.connection_status = ("connected")
                self.overall_page.update_display()
                print("CANReceiver 已重新初始化")

            except Exception as e:
                print(f"{self.current_text.CAN_INIT_FAILED}: {e}")
                self.overall_page.data.connection_status = ("offline")
                self.overall_page.update_display()

    # CAN 数据更新
    def on_can_data_updated(self, signal_dict):
        data = self.overall_page.data
        updated = False
        # 电池数量 / 芯片数量
        if 'Conn1Number' in signal_dict:
            data.total_chip_count = int(signal_dict['Conn1Number'])
            updated = True

        if 'Conn2Number' in signal_dict:
            data.total_battery_count = int(signal_dict['Conn2Number'])
            updated = True

        # SOC / SOH
        if 'PackSOC' in signal_dict:
            data.pack_soc = round(signal_dict['PackSOC'],1)
            data.total_soc_percent = data.pack_soc
            updated = True

        if 'BatSOH' in signal_dict:
            data.pack_soh = round(signal_dict['BatSOH'],1)
            data.total_soh_percent = data.pack_soh
            updated = True

        # EIS
        if 'EISPackSOC' in signal_dict:
            data.eis_pack_soc = int(signal_dict['EISPackSOC'])
            updated = True

        if 'EISBatSOH' in signal_dict:
            data.eis_bat_soh = int(signal_dict['EISBatSOH'])
            updated = True

        # 容量
        if 'BatSumChrgCap' in signal_dict:
            data.total_charge_capacity = round(signal_dict['BatSumChrgCap'],2)
            updated = True

        if 'BatSumDisChrgCap' in signal_dict:
            data.total_discharge_capacity = round(signal_dict['BatSumDisChrgCap'],2)
            updated = True

        # 温度统计
        if 'BatAvgTemp' in signal_dict:
            data.avg_temp_c = round(signal_dict['BatAvgTemp'],1)
            updated = True

        if 'BatMaxTemp' in signal_dict:
            data.max_temp_c = round(signal_dict['BatMaxTemp'],1)
            updated = True

        if 'BatMinTemp' in signal_dict:
            data.min_temp_c = round(signal_dict['BatMinTemp'],1)
            updated = True

        # 电压统计
        if 'AveCellVoltage' in signal_dict:
            data.avg_voltage_v = round(signal_dict['AveCellVoltage'] / 1000.0,3)
            updated = True

        if 'MaxCellVoltage' in signal_dict:
            data.max_voltage_v = round(signal_dict['MaxCellVoltage'] / 1000.0,3)
            updated = True

        if 'MinCellVoltage' in signal_dict:
            data.min_voltage_v = round(signal_dict['MinCellVoltage'] / 1000.0,3)
            updated = True

        # 软件版本
        if 'BMS_SoftVer' in signal_dict:
            ver = int(signal_dict['BMS_SoftVer'])
            # 防御一下范围
            ver = max(0, min(ver, 256))
            major = ver // 100
            minor = (ver // 10) % 10
            patch = ver % 10
            data.software_version = f"v{major}.{minor}.{patch}"
            updated = True

        # CPU 使用率
        if 'CPU_USE' in signal_dict:
            data.cpu_usage_percent = int(signal_dict['CPU_USE'])
            updated = True

        # 26节单体 SoC
        for i in range(26):
            signal_name = f"CellSOC{i + 1}"
            if signal_name in signal_dict:
                data.cell_soc[i] = int(signal_dict[signal_name])
                updated = True

        # 26节单体温度
        for i in range(26):
            signal_name = f"CellTemp{i + 1}"
            if signal_name in signal_dict:
                data.cell_temp[i] = round(signal_dict[signal_name],1)
                updated = True

        # 26节单体电压
        for i in range(26):
            signal_name = f"CellVoltage{i + 1}"
            if signal_name in signal_dict:
                data.cell_volt[i] = round(signal_dict[signal_name] / 1000.0,3)
                updated = True

        # 故障诊断
        if 'BatFaultCode1' in signal_dict:
            data.fault_code = int(signal_dict['BatFaultCode1'])
            updated = True
        if 'BatFaultLevel' in signal_dict:
            data.fault_level = int(signal_dict['BatFaultLevel'])
            updated = True

        # 数据更新（不直接刷新UI）
        if updated:
            if data.connection_status != "connected":
                data.connection_status = "connected"
            data.recalculate_statistics()
            data.last_update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 趋势记录限频
            now = time.time()
            if now - self.last_history_update >= 1.0:
                data.add_current_to_history()
                self.last_history_update = now

    # CAN 报文接收
    def on_can_message_received(self):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.overall_page.update_last_update_time(now_str)

    # 跳转单体监测页
    def jump_to_single_monitor(self, battery_name):
        self.tabs.setCurrentWidget(self.single_page)
        print(
            f"{self.current_text.JUMP_TO_MONITOR}: "
            f"{battery_name}"
        )

    # 关闭
    def closeEvent(self, event):
        if self.can_receiver:
            self.can_receiver.stop()
        super().closeEvent(event)

    # CAN 重连
    def reconnect_can(
            self,
            app_name,
            channel,
            arb_bitrate,
            data_bitrate
    ):
        print("开始重新连接 CAN...")
        if self.can_receiver:
            self.can_receiver.stop()
            self.can_receiver = None
        dbc_path = self.dbc_path
        try:
            self.can_receiver = CANReceiver(
                app_name=app_name,
                channel=channel,
                arb_bitrate=arb_bitrate,
                data_bitrate=data_bitrate,
                dbc_path=dbc_path
            )
            self.can_receiver.data_updated.connect(self.on_can_data_updated)
            self.can_receiver.message_received.connect(self.on_can_message_received)
            self.overall_page.data.connection_status = ("connected")
            self.overall_page.update_display()
            print("CAN 重连成功")
        except Exception as e:
            print(f"CAN 重连失败: {e}")
            self.overall_page.data.connection_status = ("offline")
            self.overall_page.update_display()

# Main
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())