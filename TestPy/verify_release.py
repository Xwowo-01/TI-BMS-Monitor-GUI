"""Validate a frozen release by starting its EXE in an isolated environment.

Usage: python TestPy/verify_release.py path/to/BatteryMonitor report.json
No CAN hardware is opened by the startup smoke test.
"""
import json
import os
from pathlib import Path
import subprocess
import sys


def verify_release(directory, report_path):
    directory = Path(directory).resolve()
    report_path = Path(report_path).resolve()
    internal = directory / '_internal'
    for name in ('icuuc.dll', 'icuin.dll', 'icudt78.dll'):
        if (internal / name).exists():
            raise RuntimeError(f'发布包含有不应覆盖系统 ICU 的 DLL: {name}')
    environment = os.environ.copy()
    windows = Path(environment.get('SystemRoot', r'C:\Windows'))
    environment['PATH'] = os.pathsep.join([str(windows / 'System32'), str(windows)])
    environment['QT_QPA_PLATFORM'] = 'offscreen'
    for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH',
                'QT_QPA_PLATFORM_PLUGIN_PATH'):
        environment.pop(key, None)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.exists():
        raise FileExistsError(f'启动报告已存在，拒绝使用旧结果: {report_path}')
    process = subprocess.Popen(
        [str(directory / 'BatteryMonitor.exe'), '--startup-smoke-test', str(report_path)],
        cwd=directory, env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )
    try:
        code = process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
        raise RuntimeError('EXE 启动测试超时，可能停在崩溃对话框') from None
    if code != 0 or not report_path.is_file():
        raise RuntimeError(f'EXE 启动失败: exit={code}, report_exists={report_path.exists()}')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if (report['status'], report['frozen'], report['tabs'], report['can_connected']) != (
            'ok', True, 4, False):
        raise RuntimeError(f'启动测试未通过: {report}')
    if report.get('bootloader_button_checks') != {
            'no_file_click': True, 'failed_flash_recovers': True}:
        raise RuntimeError(f'刷写按钮路径验证未通过: {report}')
    core = Path(report['loaded_modules']['Qt6Core.dll']).resolve()
    if not core.is_relative_to(internal):
        raise RuntimeError(f'Qt6Core 错误地从发布包以外加载: {core}')
    icu = Path(report['loaded_modules']['icuuc.dll']).resolve()
    if not icu.is_relative_to((windows / 'System32').resolve()):
        raise RuntimeError(f'Windows ICU 加载来源错误: {icu}')
    return report


if __name__ == '__main__':
    print(json.dumps(verify_release(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=2))
