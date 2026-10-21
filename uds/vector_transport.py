"""Audit the Vector XL boundary without retrying or reordering CAN frames.

python-can 4.6.1's public VectorBus.send() discards the XL accepted count.
Keep the use of its protected _send_sequence() isolated here and test against
the installed driver adapter. TX completion events remain separate from UDS ACKs.
"""
import threading

import can
from can.interfaces.vector import VectorBus
from can.interfaces.vector.canlib import get_channel_configs
from can.interfaces.vector import xldefine


class VectorTransport:
    def __init__(self, bus, log):
        if not isinstance(bus, VectorBus) or not callable(getattr(bus, '_send_sequence', None)):
            raise can.CanInitializationError('Vector 发送适配器不兼容，停止刷写')
        self.bus = bus
        self.log = log
        self._bus_off = threading.Event()
        self.last_state = 'unknown'
        # These are the non-message event hooks offered by VectorBus.
        bus.handle_can_event = self.handle_can_event
        bus.handle_canfd_event = self.handle_canfd_event

    def describe(self):
        bus = self.bus
        self.log(f"VECTOR_PORT：channel_info={bus.channel_info!r} "
                 f"mask=0x{bus.mask:X} init_access=0x{bus.permission_mask:X} "
                 f"logical_to_mask={bus.channel_masks} protocol={bus.protocol.name}")
        configs = get_channel_configs()
        selected = [cfg for cfg in configs if bus.mask & (1 << cfg.channel_index)]
        if not selected:
            raise can.CanInitializationError('未能查到已打开的 Vector 物理通道，停止刷写')
        for cfg in selected:
            params = cfg.bus_params
            active = (params.canfd if bus.protocol is can.CanProtocol.CAN_FD else params.can) if params else None
            self.log(f"VECTOR_CHANNEL：name={cfg.name!r} serial={cfg.serial_number} "
                     f"hw_type={int(cfg.hw_type)} hw_index={cfg.hw_index} "
                     f"hw_channel={cfg.hw_channel} physical_port={cfg.hw_channel + 1} "
                     f"global_index={cfg.channel_index} on_bus={cfg.is_on_bus} "
                     f"transceiver={cfg.transceiver_name!r} active_params={active!r}")
            if int(cfg.hw_type) == 1:
                raise can.CanInitializationError('当前 Vector 应用映射到虚拟通道，不会发往物理 CAN，停止刷写')
            if active and int(active.output_mode) != int(xldefine.XL_OutputMode.XL_OUTPUT_MODE_NORMAL):
                raise can.CanInitializationError(
                    f'Vector 通道输出模式为 {active.output_mode!r}，不是 NORMAL；'
                    '请检查占用通道的软件及 Vector 硬件配置')
        if bus.permission_mask != bus.mask:
            self.log('VECTOR_SHARED_CHANNEL：未获得全部通道初始化权限，当前参数由其他客户端共享；详见 active_params')

    def request_state(self):
        try:
            self.bus.xldriver.xlCanRequestChipState(self.bus.port_handle, self.bus.mask)
        except Exception as exc:
            # Some older adapters do not support querying chip state. Sending
            # must still check XL's accepted count and log any available events.
            self.log(f'VECTOR_STATE_QUERY_UNAVAILABLE：{exc!r}')

    def check_state(self):
        if self._bus_off.is_set():
            raise can.CanOperationError('Vector 控制器报告 BUS_OFF，本次刷写中止，请排查总线后重新连接')

    def send(self, message):
        self.check_state()
        accepted = self.bus._send_sequence([message])
        if accepted != 1:
            # Never retry an ambiguous driver result here: ISO-TP owns the
            # sequence and UDS owns any request/block retry.
            raise can.CanOperationError(f'Vector 驱动接受帧数异常：requested=1 accepted={accepted!r}')
        return accepted

    def _chip_state(self, event, state):
        status = state.busStatus
        names = [flag.name for flag in xldefine.XL_BusStatus if status & int(flag)]
        self.last_state = (
            f"global_index={event.chanIndex} status=0x{status:X} {'|'.join(names) or 'UNKNOWN'} "
            f"tx_errors={state.txErrorCounter} rx_errors={state.rxErrorCounter}")
        if status & int(xldefine.XL_BusStatus.XL_CHIPSTAT_BUSOFF):
            # Latch even if the hardware later recovers: do not resume a partly
            # sent programming transaction automatically.
            self._bus_off.set()
        self.log(f'CAN_CHIP_STATE：{self.last_state}')

    def handle_can_event(self, event):
        if event.tag == xldefine.XL_EventTags.XL_CHIP_STATE:
            self._chip_state(event, event.tagData.chipState)

    def handle_canfd_event(self, event):
        tags = xldefine.XL_CANFD_RX_EventTags
        if event.tag == tags.XL_CAN_EV_TAG_CHIP_STATE:
            self._chip_state(event, event.tagData.canChipState)
        elif event.tag in (tags.XL_CAN_EV_TAG_RX_ERROR, tags.XL_CAN_EV_TAG_TX_ERROR):
            self.log(f'CAN_FD_ERROR：event={tags(event.tag).name} global_index={event.chanIndex} '
                     f'error_code={event.tagData.canError.errorCode}')
