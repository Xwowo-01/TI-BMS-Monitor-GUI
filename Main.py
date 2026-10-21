# main.py
import vector_utils
vector_utils.prepare_vector_dll()  # 必须在首次 import can.interfaces.vector 之前调用

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
    QHBoxLayout,
    QTabWidget,
    QLabel,
    QFrame
)
from pages import (
    BatteryMonitorUI,
    OverallStatusPage,
    SettingUI,
    BootloaderPage
)
from can_receiver import CANReceiver
from language_manager import language_manager
import theme
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
    WINDOW_SUBTITLE = "Battery Management System · CAN FD 监控上位机"
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
    WINDOW_SUBTITLE = "Battery Management System · CAN FD Monitor"
    TAB_OVERVIEW = "Overview"
    TAB_SINGLE = "Single Monitor"
    TAB_SETTING = "Settings"
    TAB_BOOTLOADER = "Bootloader"
    STATUS_CONNECTED = "Connected"
    STATUS_OFFLINE = "Offline"
    CAN_INIT_FAILED = "CAN initialization failed"
    JUMP_TO_MONITOR = "Jump to monitor page, battery"

class MainWindow(QWidget):
    def __init__(self, connect_can=True):
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
        self.setObjectName("Root")
        self.setMinimumSize(1024, 680)
        self.resize(1280, 800)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 顶部标题栏 + 连接状态
        main_layout.addWidget(self._build_header())

        # 页面容器：四周留白，让卡片与窗口边缘分离
        tabs_container = QWidget()
        tc_layout = QVBoxLayout(tabs_container)
        tc_layout.setContentsMargins(16, 12, 16, 16)
        tc_layout.setSpacing(0)
        # Tab
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        self.tabs.setMovable(False)
        self.tabs.setDocumentMode(True)
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
        tc_layout.addWidget(self.tabs)
        main_layout.addWidget(tabs_container, 1)
        # 语言切换监听
        language_manager.language_changed.connect(self.switch_language)
        # 初始化页面语言
        self.switch_language(saved_language)
        # 信号
        self.bootloader_page.starting_flash.connect(self.stop_can_for_flash)
        self.bootloader_page.finished_flash.connect( self.restart_can_after_flash)
        self.overall_page.cellClicked.connect(self.jump_to_single_monitor)
        self.setting_page.reconnect_requested.connect(self.reconnect_can)
        self.single_page.eis_start_requested.connect(self.send_eis_start)
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
            self.can_interface = settings.value("can_interface","vector")
            app_name = settings.value("app_name","VectorTest")
            channel = int(settings.value("channel",0))
            arb_bitrate = int(settings.value("arb_bitrate",1000000))
            data_bitrate = int(settings.value("data_bitrate",1000000))
            self.dbc_path = resource_path("System3.dbc")
            if connect_can:
                self.can_receiver = CANReceiver(
                    app_name=app_name,
                    channel=channel,
                    arb_bitrate=arb_bitrate,
                    data_bitrate=data_bitrate,
                    dbc_path=self.dbc_path,
                    interface=self.can_interface
                )
                self.can_receiver.data_updated.connect(self.on_can_data_updated)
                self.can_receiver.message_received.connect(self.on_can_message_received)
                self.can_receiver.raw_message.connect(self.bootloader_page.on_raw_message)
            self.overall_page.update_display()
        except Exception as e:
            print(f"{self.current_text.CAN_INIT_FAILED}: {e}")
            self.overall_page.data.connection_status = ("offline")
            self.overall_page.update_display()

        self._update_header_status()

    # 构建顶部标题栏
    def _build_header(self):
        header = QFrame()
        header.setObjectName("HeaderBar")
        header.setFixedHeight(58)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(22, 0, 22, 0)
        hl.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(1)
        self.header_title = QLabel(self.current_text.WINDOW_TITLE)
        self.header_title.setObjectName("HeaderTitle")
        left.addWidget(self.header_title)
        self.header_subtitle = QLabel(self.current_text.WINDOW_SUBTITLE)
        self.header_subtitle.setObjectName("HeaderSubtitle")
        left.addWidget(self.header_subtitle)
        hl.addLayout(left)
        hl.addStretch(1)

        self.header_status_dot = theme.StatusDot(theme.COLORS["text_muted"], 9)
        self.header_status_label = QLabel(self.current_text.STATUS_OFFLINE)
        self.header_status_label.setObjectName("HeaderSubtitle")
        self.header_status_label.setStyleSheet("color:#cbd5e1; font-size:12px;")
        hl.addWidget(self.header_status_dot)
        hl.addWidget(self.header_status_label)
        return header

    # 更新顶栏连接状态
    def _update_header_status(self):
        status = self.overall_page.data.connection_status
        self.header_status_dot.set_color(
            theme.STATUS_COLOR.get(status, theme.COLORS["text_muted"])
        )
        if status == "connected":
            text = self.current_text.STATUS_CONNECTED
        elif status == "offline":
            text = self.current_text.STATUS_OFFLINE
        else:
            text = status
        self.header_status_label.setText(text)

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
        self.header_title.setText(self.current_text.WINDOW_TITLE)
        self.header_subtitle.setText(self.current_text.WINDOW_SUBTITLE)
        self.tabs.setTabText(0,self.current_text.TAB_OVERVIEW)
        self.tabs.setTabText(1,self.current_text.TAB_SINGLE)
        self.tabs.setTabText(2,self.current_text.TAB_SETTING)
        self.tabs.setTabText(3,self.current_text.TAB_BOOTLOADER)
        self._update_header_status()

    # 低频刷新UI
    def refresh_ui(self):
        try:
            self.overall_page.update_display()
            self.overall_page.update_all_matrices()
            self.single_page.update_data_display()   # 刷新单体页面左侧数据
            self._update_header_status()
        except Exception as e:
            print(f"UI刷新错误: {e}")

    # 低频刷新趋势图（Overall 趋势 + Single 电压温度图）
    def refresh_chart(self):
        try:
            self.overall_page.update_trend_chart()
            self.single_page.refresh_plots()   # 每秒更新单体电压/温度曲线
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
                settings = QSettings("BatteryMonitor", "CANConfig")
                self.can_interface = settings.value("can_interface", "vector")
                app_name = settings.value("app_name", "VectorTest")
                channel = int(settings.value("channel", 0))
                arb_bitrate = int(settings.value("arb_bitrate", 1000000))
                data_bitrate = int(settings.value("data_bitrate", 1000000))
                self.can_receiver = CANReceiver(
                    app_name=app_name,
                    channel=channel,
                    arb_bitrate=arb_bitrate,
                    data_bitrate=data_bitrate,
                    dbc_path=dbc_path,
                    interface=self.can_interface
                )
                self.can_receiver.data_updated.connect(self.on_can_data_updated)
                self.can_receiver.message_received.connect(self.on_can_message_received)
                self.can_receiver.raw_message.connect(self.bootloader_page.on_raw_message)
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
        single_data = self.single_page.data  # 获取单体数据对象
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
                soc_val = int(signal_dict[signal_name])
                data.cell_soc[i] = soc_val
                # 同步到 SingleMonitor 数据
                single_data.cell_soc[i] = soc_val
                single_data.cell_remaining_cap[i] = int(
                    single_data.cell_full_cap[i] * soc_val / 100
                )
                updated = True

        # 26节单体温度
        for i in range(26):
            signal_name = f"CellTemp{i + 1}"
            if signal_name in signal_dict:
                temp_val = round(signal_dict[signal_name], 1)
                data.cell_temp[i] = temp_val
                single_data.cell_temp[i] = temp_val
                updated = True

        # 26节单体电压
        for i in range(26):
            signal_name = f"CellVoltage{i + 1}"
            if signal_name in signal_dict:
                volt_val = round(signal_dict[signal_name] / 1000.0, 3)
                data.cell_volt[i] = volt_val
                single_data.cell_voltage[i] = volt_val
                updated = True

        # 故障诊断
        if 'BatFaultCode1' in signal_dict:
            data.fault_code = int(signal_dict['BatFaultCode1'])
            updated = True
        if 'BatFaultLevel' in signal_dict:
            data.fault_level = int(signal_dict['BatFaultLevel'])
            updated = True

        # ---------- EIS 数据解析（报文 ID 440） ----------
        # # ---------- 优化后的 EIS 日志 ----------
        # cell = signal_dict.get('Bat_EIS_CelNum')
        # freq = signal_dict.get('Bat_EIS_Freq')
        # real = signal_dict.get('BatCell_EIS_Z_Real')
        # imag = signal_dict.get('BatCell_EIS_Z_Imag')
        # finish = signal_dict.get('EISFinish')
        # # 判断是否为有效数据点（编号 1~26，且实部或虚部至少一个非零）
        # has_valid_data = (cell is not None and 1 <= cell <= 26 and (real != 0 or imag != 0))
        # # 仅当有有效数据点或完成标志时打印
        # if has_valid_data or finish is not None:
        #     parts = []
        #     if has_valid_data:
        #         parts.append(f"电池{cell}, 频率{freq}Hz, 实部{real}, 虚部{imag}")
        #     if finish is not None:
        #         # 将 finish 转为字符串并去除可能的前后空格，便于阅读
        #         finish_str = str(finish).strip()
        #         parts.append(f"完成状态: {finish_str}")
        #     print("EIS:", " | ".join(parts))

        # 解析 EIS 数据点（实部虚部）
        if 'Bat_EIS_CelNum' in signal_dict and 'BatCell_EIS_Z_Real' in signal_dict and 'BatCell_EIS_Z_Imag' in signal_dict:
            cell_num = int(signal_dict['Bat_EIS_CelNum'])
            # 频率因子 0.01，单位 Hz
            freq = signal_dict.get('Bat_EIS_Freq', 0.0)
            real = signal_dict['BatCell_EIS_Z_Real']
            imag = signal_dict['BatCell_EIS_Z_Imag']
            self.single_page.receive_eis_point(cell_num, freq, real, imag)

        # 解析 EIS 完成标志
        if 'EISFinish' in signal_dict:
            finish_str = str(signal_dict['EISFinish']).strip()
            if finish_str == 'Sampling Completed':
                self.single_page.on_eis_finish()

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

            # 如果 SingleMonitor 处于采集状态，记录当前数据到历史
            if single_data.vt_status == "running":
                single_data.record_current_data(now)

    # CAN 报文接收
    def on_can_message_received(self):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.overall_page.update_last_update_time(now_str)

    # 跳转单体监测页
    def jump_to_single_monitor(self, battery_name):
        self.tabs.setCurrentWidget(self.single_page)
        # 同步单体页下拉框到点击的电芯序号
        try:
            num = int(''.join(ch for ch in battery_name if ch.isdigit()))
            count = self.single_page.battery_select.count()
            if count > 0:
                self.single_page.battery_select.setCurrentIndex(
                    max(0, min(num - 1, count - 1))
                )
        except ValueError:
            pass

    # 发送 EIS 启动报文
    def send_eis_start(self):
        """由上位机向 BMS 发送 EIS 启动报文（CPU_UASGE，ID 0x11）。
        信号 EIS Start 位于字节 0 位 7（1 bit），置 1 触发 EIS 采集。"""
        if self.can_receiver:
            data = [0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
            if self.can_receiver.send_message(0x11, data):
                print("EIS 启动报文已发送 (0x11)")
            else:
                print("EIS 启动报文发送失败：CAN 未连接")
        else:
            print("EIS 启动报文发送失败：CAN 未连接")

    # 关闭
    def closeEvent(self, event):
        if self.can_receiver:
            self.can_receiver.stop()
        super().closeEvent(event)

    # CAN 重连
    def reconnect_can(
            self,
            interface,
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
        self.can_interface = interface
        try:
            self.can_receiver = CANReceiver(
                app_name=app_name,
                channel=channel,
                arb_bitrate=arb_bitrate,
                data_bitrate=data_bitrate,
                dbc_path=dbc_path,
                interface=interface
            )
            self.can_receiver.data_updated.connect(self.on_can_data_updated)
            self.can_receiver.message_received.connect(self.on_can_message_received)
            self.can_receiver.raw_message.connect(self.bootloader_page.on_raw_message)
            self.overall_page.data.connection_status = ("connected")
            self.overall_page.update_display()
            print("CAN 重连成功")
        except Exception as e:
            print(f"CAN 重连失败: {e}")
            self.overall_page.data.connection_status = ("offline")
            self.overall_page.update_display()

# Main
if __name__ == "__main__":
    smoke_test = '--startup-smoke-test' in sys.argv
    if smoke_test:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication(sys.argv)
    app.setStyleSheet(theme.APP_STYLESHEET)
    w = MainWindow(connect_can=not smoke_test)
    w.show()
    # show 后再强制一次初始尺寸，确保布局稳定后仍为 1280x800
    QTimer.singleShot(0, lambda: w.resize(1280, 800))
    if smoke_test:
        smoke_checks = {}
        # 启动已打包 EXE、创建全部页面并跑事件循环，不连接 CAN 硬件。
        def write_smoke_result():
            import ctypes
            import json
            from pathlib import Path
            from PySide6.QtCore import qVersion

            modules = {}
            if os.name == 'nt':
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
                kernel.GetModuleHandleW.restype = ctypes.c_void_p
                kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                                       ctypes.c_uint]
                kernel.GetModuleFileNameW.restype = ctypes.c_uint
                for name in ('Qt6Core.dll', 'icuuc.dll', 'VCRUNTIME140.dll'):
                    handle = kernel.GetModuleHandleW(name)
                    if handle:
                        buffer = ctypes.create_unicode_buffer(32768)
                        kernel.GetModuleFileNameW(handle, buffer, len(buffer))
                        modules[name] = buffer.value
            target = Path(sys.argv[sys.argv.index('--startup-smoke-test') + 1])
            target.write_text(json.dumps({
                'status': 'ok' if all(smoke_checks.values()) else 'failed',
                'frozen': bool(getattr(sys, 'frozen', False)),
                'qt_version': qVersion(), 'tabs': w.tabs.count(),
                'can_connected': w.can_receiver is not None,
                'loaded_modules': modules,
                'bootloader_button_checks': smoke_checks,
            }, ensure_ascii=False, indent=2), encoding='utf-8')
            app.quit()

        def check_bootloader_buttons():
            import tempfile
            from pathlib import Path

            page = w.bootloader_page
            page.start_btn.click()
            smoke_checks['no_file_click'] = (
                page.current_ui.PLEASE_SELECT_BIN in page.log_text.toPlainText()
                and callable(page.thread) and page._flash_thread is None)
            original_bus = can.interface.Bus
            bus_calls = []

            def reject_hardware(**kwargs):
                bus_calls.append(kwargs)
                raise RuntimeError('STARTUP_SMOKE_NO_HARDWARE')

            report_path = Path(sys.argv[sys.argv.index('--startup-smoke-test') + 1])
            with tempfile.NamedTemporaryFile(dir=report_path.parent, suffix='.bin',
                                             delete=False) as firmware:
                firmware.write(bytes(range(16)))
                firmware_path = Path(firmware.name)

            def after_failed_flash(success):
                can.interface.Bus = original_bus
                firmware_path.unlink()
                smoke_checks['failed_flash_recovers'] = (
                    not success and bool(bus_calls) and page._flash_thread is None
                    and page.start_btn.isEnabled() and page.file_btn.isEnabled()
                    and callable(page.thread)
                    and 'STARTUP_SMOKE_NO_HARDWARE' in page.log_text.toPlainText())
                write_smoke_result()

            page.finished_flash.connect(after_failed_flash)
            page.bin_file = str(firmware_path)
            page.log_checkbox.setChecked(False)
            # 失败总线工厂在 QThread 启动前替换，整个自检不会接触 CAN 硬件。
            can.interface.Bus = reject_hardware
            page.start_btn.click()

        QTimer.singleShot(300, check_bootloader_buttons)
    sys.exit(app.exec())
