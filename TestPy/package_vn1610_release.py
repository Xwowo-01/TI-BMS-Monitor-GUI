"""Verify the v5 onedir release and write provenance; does not make a ZIP.

Run with the same project Python after PyInstaller finishes and Git is committed.
No CAN hardware is opened by the frozen startup smoke check.
"""
from datetime import datetime
import hashlib
import json
import marshal
from pathlib import Path
import subprocess
import sys
import types

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from PyInstaller.archive.readers import CArchiveReader
from TestPy.verify_release import verify_release


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(code):
    constants = tuple(normalize(item) if isinstance(item, types.CodeType) else item
                      for item in code.co_consts)
    return code.replace(co_filename='verified-source.py', co_consts=constants)


def main():
    release = root / 'dist/BootloaderFix_20261021_v5_VN1610/BatteryMonitor'
    exe = release / 'BatteryMonitor.exe'
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    archive = CArchiveReader(str(exe))
    pyz = archive.open_embedded_archive(next(name for name in archive.toc if name.endswith('.pyz')))
    sources = {'Main': root / 'Main.py', 'uds.uds_flasher': root / 'uds/uds_flasher.py',
               'uds.vector_transport': root / 'uds/vector_transport.py',
               'pages.bootloader_page': root / 'pages/bootloader_page.py'}
    for name, path in sources.items():
        code = marshal.loads(archive.extract(name)) if name == 'Main' else pyz.extract(name)
        assert normalize(code) == normalize(compile(path.read_bytes(), str(path), 'exec')), name
    startup = verify_release(release, root / 'build/release-startup-smoke-v5-vn1610.json')
    (release / 'STARTUP_CHECK.json').write_text(json.dumps(startup, ensure_ascii=False, indent=2),
                                              encoding='utf-8')
    link = json.loads((root / 'build/VN1610_v5_validation/link_20261021_185611_819033.json')
                      .read_text(encoding='utf-8'))
    assert link['mode'] == 'link' and link['success'] and link['serial'] == 26774
    assert link['response'][:2] == [0x50, 0x03]
    assert link['stats']['error_frames'] == link['stats']['driver_errors'] == 0
    (release / 'VN1610_CONNECTION_CHECK.json').write_text(json.dumps(link, ensure_ascii=False, indent=2),
                                                        encoding='utf-8')
    previous = root / 'dist/BootloaderFix_20261021_v4/BatteryMonitor'
    old_dlls = {str(path.relative_to(previous)): sha256(path) for path in previous.rglob('*.dll')}
    new_dlls = {str(path.relative_to(release)): sha256(path) for path in release.rglob('*.dll')}
    assert old_dlls == new_dlls, 'Unexpected DLL dependency changes versus v4'
    info = dict(release='BatteryMonitor_20261021_v5_VN1610', git_commit=commit,
                built_at=datetime.now().astimezone().isoformat(),
                bootloader_revision='2026-10-21-vn1610-v5',
                profile=dict(model='VN1610', serial=26774, physical_port=1,
                             bitrate=1000000, fd=False, application_mapping=False),
                validation=dict(offline_tests=61, protocol_tests=28, gui_tests=8,
                                vector_adapter_tests=25, frozen_startup=True,
                                embedded_sources=list(sources),
                                hardware_link=True, hardware_full_flash=False,
                                unchanged_dlls=len(new_dlls)),
                sha256={str(path.relative_to(root)): sha256(path)
                        for path in [exe, *sources.values()]})
    (release / 'RELEASE_INFO.json').write_text(json.dumps(info, ensure_ascii=False, indent=2),
                                             encoding='utf-8')
    (release / '使用说明.txt').write_text(f'''BMS Bootloader v5 / VN1610（2026-10-21）
本地 Git：{commit}

运行本目录的 BatteryMonitor.exe，保留同目录 _internal 文件夹。
进入 Bootloader 页面，选择 BIN，保持“使用 VN1610（26774）”选中，然后开始刷写。
默认使用序列号 26774 的 VN1610、物理 CAN1、1 Mbps、传统 CAN。
此模式直接选择硬件，不依赖 VectorTest 应用注册或配置管理中的 CAN 参数。
未找到指定序列号或检测到打开的设备/端口不符时会报错停止。
刷写前退出旧版上位机并断开其他占用 CAN1 的客户端，保证可设置正确波特率。
完整日志默认保存，日志开头显示绝对路径，包含全部 CAN 连续帧和错误信息。

如取消“使用 VN1610（26774）”，恢复沿用配置管理中的 Vector 应用、通道和速率；
这时可手动选择原有 CAN-FD 模式。本次的 VN1610 固定配置始终使用传统 CAN。

本次修改：
1. 新增当前 VN1610 的固定刷写配置，复核实际序列号、硬件类型、物理端口和活动速率。
2. 接收线程立即处理已排队的芯片状态、发送完成及应答事件；只有队列为空才等待。
   避免状态事件被当作空队列而延迟处理后续 UDS 应答或流控。
3. 保留严格 ISO-TP 流控、块序号及 UDS 应答校验，详细日志默认开启。
   未改变安全访问、擦除范围、下载地址及固件内容。

验证：61 项离线测试通过；其中包括模拟 XL 驱动完成整个刷写流程并逐字节核对固件。
真实 VN1610 CAN1 已用新版代码收到 50 03 应答，发送完成回执 1 次、总线/驱动错误 0。
EXE 内嵌源码已核对，已实际启动 EXE 检查 Qt DLL 和刷写按钮路径。
按照你的要求，未执行实机擦除、下载和复位，完整刷写由你在上位机操作。
本版与 v4 的全部 DLL 完全相同，未增加运行库；没有生成 ZIP。
''', encoding='utf-8-sig')
    print(json.dumps(dict(directory=str(release), git_commit=commit, dlls=len(new_dlls),
                          files=sum(path.is_file() for path in release.rglob('*')),
                          bytes=sum(path.stat().st_size for path in release.rglob('*') if path.is_file()),
                          exe_sha256=sha256(exe), frozen_startup='passed'),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
