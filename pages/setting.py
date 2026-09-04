# pages/setting.py
import sys
from PySide6.QtCore import (
    Qt,
    Signal,
    QSettings,
    QObject,
    Slot
)
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QPushButton,
    QHBoxLayout,
    QLineEdit,
    QFormLayout,
    QTextEdit
)

from language_manager import language_manager
import theme


# 日志重定向类（线程安全）
class LogRedirector(QObject):
    """将 stdout/stderr 重定向到 UI 信号"""
    log_signal = Signal(str)
    def __init__(self):
        super().__init__()
        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr

    def write(self, text):
        if text and text.strip():
            # 发射信号，在主线程更新 UI
            self.log_signal.emit(text)
        # 同时输出到原始控制台（可选，保留控制台输出）
        if self._old_stdout:
            self._old_stdout.write(text)

    def flush(self):
        if self._old_stdout:
            self._old_stdout.flush()

    def start_redirect(self):
        sys.stdout = self
        sys.stderr = self

    def stop_redirect(self):
        sys.stdout = self._old_stdout
        sys.stderr = self._old_stderr


# 中文文本
class UITextZH:
    PAGE_TEXT = "配置情况（待补充）"
    LANGUAGE_TITLE = "语言"
    SWITCH_ZH = "中文"
    SWITCH_EN = "English"
    APP_NAME = "应用名"
    CHANNEL = "通道"
    ARB_BITRATE = "仲裁域波特率"
    DATA_BITRATE = "数据域波特率"
    RECONNECT_CAN = "重新连接 CAN"
    LOG_TITLE = "实时日志"
    SECTION_CAN = "CAN 配置"
    SECTION_LOG = "实时日志"
    CAN_HELP = "CAN 通道与波特率参数，需与总线及 Vector 硬件配置一致"
    LOG_HELP = "程序运行日志（stdout / stderr 实时捕获）"
    APP_NAME_HINT = "Vector Hardware Config 中创建的应用名"
    CHANNEL_HINT = "通道序号（0 对应 CH1）"
    ARB_HINT = "仲裁域波特率（bps）"
    DATA_HINT = "数据域波特率（bps，CAN FD）"


# English 文本
class UITextEN:
    PAGE_TEXT = "Configuration Page (To Be Added)"
    LANGUAGE_TITLE = "Language"
    SWITCH_ZH = "中文"
    SWITCH_EN = "English"
    APP_NAME = "App Name"
    CHANNEL = "Channel"
    ARB_BITRATE = "Arbitration Bitrate"
    DATA_BITRATE = "Data Bitrate"
    RECONNECT_CAN = "Reconnect CAN"
    LOG_TITLE = "Live Log"
    SECTION_CAN = "CAN Configuration"
    SECTION_LOG = "Live Log"
    CAN_HELP = "CAN channel and bitrate parameters, must match the bus and Vector hardware config"
    LOG_HELP = "Live application log (stdout / stderr capture)"
    APP_NAME_HINT = "Application name created in Vector Hardware Config"
    CHANNEL_HINT = "Channel index (0 = CH1)"
    ARB_HINT = "Arbitration bitrate (bps)"
    DATA_HINT = "Data bitrate (bps, CAN FD)"

class SettingUI(QWidget):
    reconnect_requested = Signal(str, int, int, int)
    def __init__(self):
        super().__init__()
        self.current_text = UITextZH
        self.settings = QSettings("BatteryMonitor", "CANConfig")
        # 日志重定向器
        self.log_redirector = LogRedirector()
        self.log_redirector.log_signal.connect(self.append_log)
        # 启动全局日志捕获（所有 print 都会进入此窗口）
        self.log_redirector.start_redirect()
        self.setup_ui()
        language_manager.language_changed.connect(self.switch_language)
        self.load_saved_config()

    # 构建 UI
    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # 顶部语言切换（右对齐）
        top_layout = QHBoxLayout()
        top_layout.addStretch(1)
        self.lang_label = QLabel(self.current_text.LANGUAGE_TITLE)
        self.lang_label.setStyleSheet("color:#475569; font-weight:600;")
        self.zh_btn = QPushButton(self.current_text.SWITCH_ZH)
        self.en_btn = QPushButton(self.current_text.SWITCH_EN)
        self.zh_btn.setCursor(Qt.PointingHandCursor)
        self.en_btn.setCursor(Qt.PointingHandCursor)
        self.zh_btn.clicked.connect(lambda: language_manager.set_language("zh"))
        self.en_btn.clicked.connect(lambda: language_manager.set_language("en"))
        top_layout.addWidget(self.lang_label)
        top_layout.addWidget(self.zh_btn)
        top_layout.addWidget(self.en_btn)
        root.addLayout(top_layout)

        main = QHBoxLayout()
        main.setSpacing(12)

        # CAN 配置卡
        self.can_card = theme.Card(self.current_text.SECTION_CAN, help_text=self.current_text.CAN_HELP)
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(12)
        self.app_name_edit = QLineEdit()
        self.channel_edit = QLineEdit()
        self.arb_bitrate_edit = QLineEdit()
        self.data_bitrate_edit = QLineEdit()
        self.app_name_edit.setToolTip(self.current_text.APP_NAME_HINT)
        self.channel_edit.setToolTip(self.current_text.CHANNEL_HINT)
        self.arb_bitrate_edit.setToolTip(self.current_text.ARB_HINT)
        self.data_bitrate_edit.setToolTip(self.current_text.DATA_HINT)
        self.app_name_label = QLabel(self.current_text.APP_NAME)
        self.channel_label = QLabel(self.current_text.CHANNEL)
        self.arb_label = QLabel(self.current_text.ARB_BITRATE)
        self.data_label = QLabel(self.current_text.DATA_BITRATE)
        form_layout.addRow(self.app_name_label, self.app_name_edit)
        form_layout.addRow(self.channel_label, self.channel_edit)
        form_layout.addRow(self.arb_label, self.arb_bitrate_edit)
        form_layout.addRow(self.data_label, self.data_bitrate_edit)
        self.can_card.add_layout(form_layout)

        self.reconnect_btn = QPushButton(self.current_text.RECONNECT_CAN)
        self.reconnect_btn.setObjectName("PrimaryButton")
        self.reconnect_btn.clicked.connect(self.on_reconnect_clicked)
        self.can_card.add_widget(self.reconnect_btn)
        self.can_card.body.addStretch(1)
        main.addWidget(self.can_card, 1)

        # 日志卡
        self.log_card = theme.Card(self.current_text.SECTION_LOG, help_text=self.current_text.LOG_HELP)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.NoWrap)
        self.log_card.add_widget(self.log_text, 1)
        main.addWidget(self.log_card, 2)

        root.addLayout(main, 1)

    # 日志槽函数（主线程安全）
    @Slot(str)
    def append_log(self, text):
        """将捕获的日志追加到文本框，并自动滚动到底部"""
        self.log_text.append(text.rstrip())
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # 加载历史配置
    def load_saved_config(self):
        app_name = self.settings.value("app_name", "VectorTest")
        channel = self.settings.value("channel", 0)
        arb_bitrate = self.settings.value("arb_bitrate", 1000000)
        data_bitrate = self.settings.value("data_bitrate", 1000000)
        self.app_name_edit.setText(str(app_name))
        self.channel_edit.setText(str(channel))
        self.arb_bitrate_edit.setText(str(arb_bitrate))
        self.data_bitrate_edit.setText(str(data_bitrate))
        saved_language = self.settings.value("language", "zh")
        language_manager.set_language(saved_language)

    # 重连按钮逻辑
    def on_reconnect_clicked(self):
        try:
            app_name = self.app_name_edit.text().strip()
            channel = int(self.channel_edit.text())
            arb_bitrate = int(self.arb_bitrate_edit.text())
            data_bitrate = int(self.data_bitrate_edit.text())
            self.settings.setValue("app_name", app_name)
            self.settings.setValue("channel", channel)
            self.settings.setValue("arb_bitrate", arb_bitrate)
            self.settings.setValue("data_bitrate", data_bitrate)
            self.reconnect_requested.emit(app_name, channel, arb_bitrate, data_bitrate)
        except Exception as e:
            print(f"参数错误: {e}")

    # 语言切换
    def switch_language(self, language):
        if language == "en":
            self.current_text = UITextEN
        else:
            self.current_text = UITextZH
        self.update_ui_text()
        self.settings.setValue("language", language)

    # 更新所有文本
    def update_ui_text(self):
        self.lang_label.setText(self.current_text.LANGUAGE_TITLE)
        self.zh_btn.setText(self.current_text.SWITCH_ZH)
        self.en_btn.setText(self.current_text.SWITCH_EN)
        self.app_name_label.setText(self.current_text.APP_NAME)
        self.channel_label.setText(self.current_text.CHANNEL)
        self.arb_label.setText(self.current_text.ARB_BITRATE)
        self.data_label.setText(self.current_text.DATA_BITRATE)
        self.reconnect_btn.setText(self.current_text.RECONNECT_CAN)
        self.can_card.title_label.setText(self.current_text.SECTION_CAN)
        self.can_card.help_label.setText(self.current_text.CAN_HELP)
        self.log_card.title_label.setText(self.current_text.SECTION_LOG)
        self.log_card.help_label.setText(self.current_text.LOG_HELP)
        self.app_name_edit.setToolTip(self.current_text.APP_NAME_HINT)
        self.channel_edit.setToolTip(self.current_text.CHANNEL_HINT)
        self.arb_bitrate_edit.setToolTip(self.current_text.ARB_HINT)
        self.data_bitrate_edit.setToolTip(self.current_text.DATA_HINT)

    # 关闭时恢复原始 stdout/stderr
    def closeEvent(self, event):
        self.log_redirector.stop_redirect()
        super().closeEvent(event)