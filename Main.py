# main.py
from PySide6.QtCore import QSettings
import os
import sys
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


# =========================================================
# 中文文本
# =========================================================

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


# =========================================================
# English
# =========================================================

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

        # =====================================================
        # Tab
        # =====================================================

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

        # =====================================================
        # 语言切换监听
        # =====================================================

        language_manager.language_changed.connect(
            self.switch_language
        )

        # =====================================================
        # 初始化页面语言
        # （不要依赖 signal 初始化）
        # =====================================================

        self.switch_language(
            saved_language
        )

        # =====================================================
        # 信号
        # =====================================================
        self.bootloader_page.starting_flash.connect(self.stop_can_for_flash)
        self.bootloader_page.finished_flash.connect(self.restart_can_after_flash)
        self.overall_page.cellClicked.connect(
            self.jump_to_single_monitor
        )
        self.setting_page.reconnect_requested.connect(
            self.reconnect_can
        )

        dbc_path = os.path.join(
            os.path.dirname(__file__),
            "System3.dbc"
        )

        self.can_receiver = None

        # =====================================================
        # 初始化 CAN
        # =====================================================

        try:

            # =====================================================
            # 读取历史 CAN 配置
            # =====================================================

            settings = QSettings(
                "BatteryMonitor",
                "CANConfig"
            )

            app_name = settings.value(
                "app_name",
                "VectorTest"
            )

            channel = int(
                settings.value(
                    "channel",
                    0
                )
            )

            arb_bitrate = int(
                settings.value(
                    "arb_bitrate",
                    1000000
                )
            )

            data_bitrate = int(
                settings.value(
                    "data_bitrate",
                    1000000
                )
            )

            # =====================================================
            # 创建 CANReceiver
            # =====================================================

            self.can_receiver = CANReceiver(
                app_name=app_name,
                channel=channel,
                arb_bitrate=arb_bitrate,
                data_bitrate=data_bitrate,
                dbc_path=dbc_path
            )

            self.can_receiver.data_updated.connect(
                self.on_can_data_updated
            )

            self.can_receiver.message_received.connect(
                self.on_can_message_received
            )

            self.overall_page.update_display()

        except Exception as e:

            print(
                f"{self.current_text.CAN_INIT_FAILED}: {e}"
            )

            self.overall_page.data.connection_status = "offline"

            self.overall_page.update_display()

    # =========================================================
    # 语言切换
    # =========================================================

    def switch_language(self, language):

        if language == "en":
            self.current_text = UITextEN
        else:
            self.current_text = UITextZH

        self.update_ui_text()

        # 通知单体监测页面
        self.single_page.switch_language(language)

        # 通知 Bootloader 页面
        self.bootloader_page.switch_language(language)

        # 通知整体页面
        self.overall_page.switch_language(language)

    # =========================================================
    # 更新 UI 文本
    # =========================================================

    def update_ui_text(self):

        self.setWindowTitle(
            self.current_text.WINDOW_TITLE
        )

        self.tabs.setTabText(
            0,
            self.current_text.TAB_OVERVIEW
        )

        self.tabs.setTabText(
            1,
            self.current_text.TAB_SINGLE
        )

        self.tabs.setTabText(
            2,
            self.current_text.TAB_SETTING
        )

        self.tabs.setTabText(
            3,
            self.current_text.TAB_BOOTLOADER
        )

    # =========================================================
    # Bootloader 刷写前后 CAN 处理
    # =========================================================

    def stop_can_for_flash(self):
        """停止 CANReceiver，为刷写释放 Vector 通道"""
        if self.can_receiver:
            self.can_receiver.stop()
            self.can_receiver = None
            print("CAN 接收已停止，为刷写释放资源")

    def restart_can_after_flash(self, success):
        """刷写完成后重新初始化 CANReceiver"""
        if success:
            dbc_path = os.path.join(os.path.dirname(__file__), "System3.dbc")
            try:
                self.can_receiver = CANReceiver(dbc_path=dbc_path)
                self.can_receiver.data_updated.connect(self.on_can_data_updated)
                self.can_receiver.message_received.connect(self.on_can_message_received)
                self.overall_page.data.connection_status = "connected"
                self.overall_page.update_display()
                print("CANReceiver 已重新初始化")
            except Exception as e:
                print(f"{self.current_text.CAN_INIT_FAILED}: {e}")
                self.overall_page.data.connection_status = "offline"
                self.overall_page.update_display()

 # =========================================================
 # CAN 数据更新
 # =========================================================

    def on_can_data_updated(self, signal_dict):

        data = self.overall_page.data

        updated = False

        # =====================================================
        # 电池数量 / 芯片数量
        # =====================================================

        if 'Conn1Number' in signal_dict:

            data.total_chip_count = int(
                signal_dict['Conn1Number']
            )

            updated = True

        if 'Conn2Number' in signal_dict:

            data.total_battery_count = int(
                signal_dict['Conn2Number']
            )

            updated = True

        # =====================================================
        # 原始 Pack SOC / SOH
        # =====================================================

        if 'PackSOC' in signal_dict:

            data.pack_soc = round(
                signal_dict['PackSOC'],
                1
            )

            updated = True

        if 'BatSOH' in signal_dict:

            data.pack_soh = round(
                signal_dict['BatSOH'],
                1
            )

            updated = True

        # =====================================================
        # EIS 修正后的 SOC / SOH
        # =====================================================

        if 'EISPackSOC' in signal_dict:

            data.eis_pack_soc = int(
                signal_dict['EISPackSOC']
            )

            updated = True

        if 'EISBatSOH' in signal_dict:

            data.eis_bat_soh = int(
                signal_dict['EISBatSOH']
            )

            updated = True

        # =====================================================
        # 累计充放电容量
        # =====================================================

        if 'BatSumChrgCap' in signal_dict:

            data.total_charge_capacity = round(
                signal_dict['BatSumChrgCap'],
                2
            )

            updated = True

        if 'BatSumDisChrgCap' in signal_dict:

            data.total_discharge_capacity = round(
                signal_dict['BatSumDisChrgCap'],
                2
            )

            updated = True

        # =====================================================
        # 温度统计
        # =====================================================

        if 'BatAvgTemp' in signal_dict:

            data.avg_temp_c = round(
                signal_dict['BatAvgTemp'],
                1
            )

            updated = True

        if 'BatMaxTemp' in signal_dict:

            data.max_temp_c = round(
                signal_dict['BatMaxTemp'],
                1
            )

            updated = True

        if 'BatMinTemp' in signal_dict:

            data.min_temp_c = round(
                signal_dict['BatMinTemp'],
                1
            )

            updated = True

        # =====================================================
        # 电压统计
        # =====================================================

        if 'AveCellVoltage' in signal_dict:

            data.avg_voltage_v = round(
                signal_dict['AveCellVoltage'] / 1000.0,
                3
            )

            updated = True

        if 'MaxCellVoltage' in signal_dict:

            data.max_voltage_v = round(
                signal_dict['MaxCellVoltage'] / 1000.0,
                3
            )

            updated = True

        if 'MinCellVoltage' in signal_dict:

            data.min_voltage_v = round(
                signal_dict['MinCellVoltage'] / 1000.0,
                3
            )

            updated = True

        # =====================================================
        # 软件版本
        # =====================================================

        if 'BMS_SoftVer' in signal_dict:

            data.software_version = (
                f"v{int(signal_dict['BMS_SoftVer'])}"
            )

            updated = True

        # =====================================================
        # 自动刷新
        # =====================================================

        if updated:
            # 修改：收到第一条有效数据后，将连接状态设为“已连接”
            if data.connection_status != "connected":
                data.connection_status = "connected"

            data.recalculate_statistics()

            data.last_update_time = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            data.add_current_to_history()

            self.overall_page.update_display()

            self.overall_page.update_all_matrices()

            self.overall_page.update_trend_chart()

    # =========================================================
    # CAN 报文接收
    # =========================================================

    def on_can_message_received(self):

        now_str = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        self.overall_page.update_last_update_time(
            now_str
        )

    # =========================================================
    # 跳转单体监测页
    # =========================================================

    def jump_to_single_monitor(self, battery_name):

        self.tabs.setCurrentWidget(
            self.single_page
        )

        print(
            f"{self.current_text.JUMP_TO_MONITOR}: {battery_name}"
        )

    # =========================================================
    # 关闭
    # =========================================================

    def closeEvent(self, event):

        if self.can_receiver:
            self.can_receiver.stop()

        super().closeEvent(event)

    def reconnect_can(
            self,
            app_name,
            channel,
            arb_bitrate,
            data_bitrate
    ):

        print("开始重新连接 CAN...")

        # =============================================
        # 停止旧连接
        # =============================================

        if self.can_receiver:
            self.can_receiver.stop()

            self.can_receiver = None

        dbc_path = os.path.join(
            os.path.dirname(__file__),
            "System3.dbc"
        )

        # =============================================
        # 创建新连接
        # =============================================

        try:

            self.can_receiver = CANReceiver(
                app_name=app_name,
                channel=channel,
                arb_bitrate=arb_bitrate,
                data_bitrate=data_bitrate,
                dbc_path=dbc_path
            )

            self.can_receiver.data_updated.connect(
                self.on_can_data_updated
            )

            self.can_receiver.message_received.connect(
                self.on_can_message_received
            )

            self.overall_page.data.connection_status = (
                "connected"
            )

            self.overall_page.update_display()

            print("CAN 重连成功")

        except Exception as e:

            print(f"CAN 重连失败: {e}")

            self.overall_page.data.connection_status = (
                "offline"
            )

            self.overall_page.update_display()


# =============================================================
# Main
# =============================================================

if __name__ == "__main__":

    app = QApplication(sys.argv)

    w = MainWindow()

    w.show()

    sys.exit(app.exec())
