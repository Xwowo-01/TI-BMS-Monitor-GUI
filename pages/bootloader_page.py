from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QFileDialog,
    QProgressBar,
    QCheckBox,
    QFrame
)

import os
import time
from datetime import datetime

from uds.uds_flasher import UDSFlasher
import theme

# 中文
class UITextCN:
    PAGE_TITLE = "Bootloader 刷写"
    NO_BIN_FILE = "未选择 BIN 文件"
    SELECT_BIN_FILE = "选择 BIN 文件"
    BIN_FILE_FILTER = "BIN Files (*.bin)"
    PLEASE_SELECT_BIN = "请先选择 BIN 文件"
    FILE_SIZE = "BIN 文件大小"
    FILE_SIZE_READ_FAILED = "读取失败"
    SAVE_CAN_LOG = "保存 CAN Log TXT"
    CAN_LOG_TITLE = "CAN 报文日志"
    CURRENT_STAGE = "当前阶段"
    STAGE_IDLE = "待机"
    START_FLASH = "开始刷写"
    FLASH_FINISHED = "===== 刷写完成 ====="
    FLASH_FAILED = "===== 刷写失败 ====="
    SECTION_FILE = "固件文件"
    SECTION_FLASH = "刷写控制"
    SECTION_LOG = "CAN 报文日志"
    FILE_HELP = "选择要刷写的 BIN 固件，可保存 CAN 报文日志"
    FLASH_HELP = "UDS 诊断刷写：会话切换 → 安全访问 → 擦除 → 下载 → 复位"
    LOG_HELP = "刷写过程中的 CAN 收发报文"
    MONITOR_START = "开始监听报文"
    MONITOR_STOP = "停止监听"

# English
class UITextEN:
    PAGE_TITLE = "Bootloader Flash"
    NO_BIN_FILE = "No BIN File Selected"
    SELECT_BIN_FILE = "Select BIN File"
    BIN_FILE_FILTER = "BIN Files (*.bin)"
    PLEASE_SELECT_BIN = "Please Select BIN File First"
    FILE_SIZE = "BIN File Size"
    FILE_SIZE_READ_FAILED = "Read Failed"
    SAVE_CAN_LOG = "Save CAN Log TXT"
    CAN_LOG_TITLE = "CAN Message Log"
    CURRENT_STAGE = "Current Stage"
    STAGE_IDLE = "Idle"
    START_FLASH = "Start Flash"
    FLASH_FINISHED = "===== Flash Finished ====="
    FLASH_FAILED = "===== Flash Failed ====="
    SECTION_FILE = "Firmware File"
    SECTION_FLASH = "Flash Control"
    SECTION_LOG = "CAN Message Log"
    FILE_HELP = "Select the BIN firmware to flash; optionally save CAN log"
    FLASH_HELP = "UDS flash: session → security → erase → download → reset"
    LOG_HELP = "CAN frames transmitted/received during flashing"
    MONITOR_START = "Start Monitor"
    MONITOR_STOP = "Stop Monitor"

class BootloaderPage(QWidget):
    starting_flash = Signal()
    finished_flash = Signal(bool)
    current_ui = UITextCN

    def __init__(self):
        super().__init__()
        self.bin_file = ""
        # ⭐ 核心：真实阶段状态（不会被语言切换覆盖）
        self.current_stage_text = self.current_ui.STAGE_IDLE
        # 报文监听状态
        self.monitoring = False
        self._last_monitor_ts = 0.0
        self.setup_ui()

    # UI
    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # 页标题
        self.title_label = QLabel(self.current_ui.PAGE_TITLE)
        self.title_label.setFont(QFont("Arial", 15, QFont.Bold))
        self.title_label.setStyleSheet("color:#111827;")
        root.addWidget(self.title_label)

        main = QHBoxLayout()
        main.setSpacing(12)

        # LEFT
        left = QWidget()
        left.setMinimumWidth(320)
        left.setMaximumWidth(400)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        # 卡1：固件文件
        self.file_card = theme.Card(self.current_ui.SECTION_FILE, help_text=self.current_ui.FILE_HELP)
        self.file_label = QLabel(self.current_ui.NO_BIN_FILE)
        self.file_label.setWordWrap(True)
        self.file_label.setStyleSheet("color:#5b6472;")
        self.file_card.add_widget(self.file_label)
        self.file_btn = QPushButton(self.current_ui.SELECT_BIN_FILE)
        self.file_btn.clicked.connect(self.choose_file)
        self.file_card.add_widget(self.file_btn)
        self.file_size_label = QLabel(f"{self.current_ui.FILE_SIZE}：0 KB")
        self.file_size_label.setStyleSheet("color:#8a94a3; font-size:12px;")
        self.file_card.add_widget(self.file_size_label)
        self.log_checkbox = QCheckBox(self.current_ui.SAVE_CAN_LOG)
        self.file_card.add_widget(self.log_checkbox)
        left_layout.addWidget(self.file_card)

        # 卡2：刷写控制
        self.flash_card = theme.Card(self.current_ui.SECTION_FLASH, help_text=self.current_ui.FLASH_HELP)
        self.stage_label = QLabel(
            f"{self.current_ui.CURRENT_STAGE}：{self.current_stage_text}"
        )
        self.stage_label.setStyleSheet("font-size:14px; font-weight:600; color:#2563eb;")
        self.flash_card.add_widget(self.stage_label)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.flash_card.add_widget(self.progress)
        self.start_btn = QPushButton(self.current_ui.START_FLASH)
        self.start_btn.setObjectName("PrimaryButton")
        self.start_btn.clicked.connect(self.start_flash)
        self.flash_card.add_widget(self.start_btn)
        left_layout.addWidget(self.flash_card)

        left_layout.addStretch(1)
        main.addWidget(left, 1)

        # RIGHT：日志卡
        self.log_card = theme.Card(self.current_ui.SECTION_LOG, help_text=self.current_ui.LOG_HELP)
        self.monitor_btn = QPushButton(self.current_ui.MONITOR_START)
        self.monitor_btn.setObjectName("GhostButton")
        self.monitor_btn.setCheckable(True)
        self.monitor_btn.clicked.connect(self.toggle_monitor)
        self.log_card.add_header_widget(self.monitor_btn)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_card.add_widget(self.log_text, 1)
        main.addWidget(self.log_card, 2)

        root.addLayout(main, 1)

    # 语言切换
    def switch_language(self, language="cn"):
        self.current_ui = UITextEN if language.lower() == "en" else UITextCN
        ui = self.current_ui
        self.title_label.setText(ui.PAGE_TITLE)
        self.file_btn.setText(ui.SELECT_BIN_FILE)
        self.log_checkbox.setText(ui.SAVE_CAN_LOG)
        self.start_btn.setText(ui.START_FLASH)
        self.monitor_btn.setText(
            ui.MONITOR_STOP if self.monitoring else ui.MONITOR_START
        )
        self.file_card.title_label.setText(ui.SECTION_FILE)
        self.file_card.help_label.setText(ui.FILE_HELP)
        self.flash_card.title_label.setText(ui.SECTION_FLASH)
        self.flash_card.help_label.setText(ui.FLASH_HELP)
        self.log_card.title_label.setText(ui.SECTION_LOG)
        self.log_card.help_label.setText(ui.LOG_HELP)
        # ⭐ 关键修复：不再重置为 Idle，而是用真实状态
        self.stage_label.setText(
            f"{ui.CURRENT_STAGE}：{self.current_stage_text}"
        )
        if not self.bin_file:
            self.file_label.setText(ui.NO_BIN_FILE)
            self.file_size_label.setText(f"{ui.FILE_SIZE}：0 KB")
        else:
            self.update_file_size_label()

    # 文件选择
    def choose_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            self.current_ui.SELECT_BIN_FILE,
            "",
            self.current_ui.BIN_FILE_FILTER
        )
        if filename:
            self.bin_file = filename
            self.file_label.setText(filename)
            self.update_file_size_label()

    # 文件大小
    def update_file_size_label(self):
        try:
            file_size = os.path.getsize(self.bin_file)
            if file_size >= 1024 * 1024:
                size_text = f"{file_size / (1024 * 1024):.2f} MB"
            else:
                size_text = f"{file_size / 1024:.2f} KB"
            self.file_size_label.setText(
                f"{self.current_ui.FILE_SIZE}：{size_text}"
            )
        except Exception:
            self.file_size_label.setText(
                f"{self.current_ui.FILE_SIZE}：{self.current_ui.FILE_SIZE_READ_FAILED}"
            )

    # 开始刷写
    def start_flash(self):
        if not self.bin_file:
            self.log_text.append(self.current_ui.PLEASE_SELECT_BIN)
            return
        self.starting_flash.emit()
        self.progress.setValue(0)
        self.log_text.clear()
        # ⭐ 可选：进入刷写状态（真实状态）
        self.current_stage_text = "Flashing"
        self.thread = QThread()
        self.flasher = UDSFlasher(
            self.bin_file,
            self.log_checkbox.isChecked()
        )
        self.flasher.moveToThread(self.thread)
        self.thread.started.connect(self.flasher.flash)
        self.flasher.log_signal.connect(self.append_log)
        self.flasher.progress_signal.connect(self.progress.setValue)
        self.flasher.stage_signal.connect(self.update_stage)
        self.flasher.finished_signal.connect(self._flash_finished)
        self.thread.start()

    # 刷写完成
    def _flash_finished(self, success):
        if hasattr(self, "thread") and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()
        self.current_stage_text = (
            "Success" if success else "Failed"
        )
        if success:
            self.log_text.append(self.current_ui.FLASH_FINISHED)
        else:
            self.log_text.append(self.current_ui.FLASH_FAILED)
        self.finished_flash.emit(success)

    # LOG
    def append_log(self, text):
        self.log_text.append(text)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    # 阶段更新
    def update_stage(self, text):
        # ⭐ 核心：保存真实状态
        self.current_stage_text = text
        self.stage_label.setText(
            f"{self.current_ui.CURRENT_STAGE}：{text}"
        )

    # 监听开关
    def toggle_monitor(self, checked):
        self.monitoring = checked
        self.monitor_btn.setText(
            self.current_ui.MONITOR_STOP if checked else self.current_ui.MONITOR_START
        )
        if checked:
            self.log_text.append("--- 开始监听 CAN 报文 ---")
        else:
            self.log_text.append("--- 暂停监听 ---")

    # 收到原始报文（监听显示：简略 + 小号字体）
    def on_raw_message(self, msg):
        if not self.monitoring:
            return
        # 限频约 20 条/秒，避免高频刷屏
        now = time.time()
        if now - self._last_monitor_ts < 0.05:
            return
        self._last_monitor_ts = now
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        data = ' '.join(f'{b:02X}' for b in msg.data)
        line = (
            f'<span style="font-size:11px;color:#9fb3cf;">'
            f'[{ts}] RX 0x{msg.arbitration_id:X} {data}</span>'
        )
        self.log_text.append(line)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )