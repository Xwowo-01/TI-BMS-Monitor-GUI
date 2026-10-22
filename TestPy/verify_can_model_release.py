"""Verify the source, UI and dependencies of a release without extra dist files."""
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
from PySide6.QtCore import QSettings


def normalize(code):
    return code.replace(co_filename='verified-source.py', co_consts=tuple(
        normalize(item) if isinstance(item, types.CodeType) else item for item in code.co_consts))


def dlls(directory):
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob('*.dll')}


def main():
    release = root / 'dist/BootloaderFix_20261022_v6/BatteryMonitor'
    assert sorted(path.name for path in release.iterdir()) == ['BatteryMonitor.exe', '_internal']
    exe = release / 'BatteryMonitor.exe'
    archive = CArchiveReader(str(exe))
    pyz = archive.open_embedded_archive(next(name for name in archive.toc if name.endswith('.pyz')))
    names = ('Main', 'can_config', 'can_receiver', 'vector_utils', 'uds.uds_flasher',
             'uds.vector_transport', 'pages.setting', 'pages.bootloader_page')
    for name in names:
        source = root / (name.replace('.', '/') + '.py')
        code = marshal.loads(archive.extract(name)) if name == 'Main' else pyz.extract(name)
        assert normalize(code) == normalize(compile(source.read_bytes(), str(source), 'exec')), name
    settings = QSettings('BatteryMonitor', 'CANConfig')
    saved_settings = {key: settings.value(key) for key in settings.allKeys()}
    report = verify_release(release, root / 'build/release-startup-smoke-v6.json')
    settings.sync()
    assert saved_settings == {key: settings.value(key) for key in settings.allKeys()}, 'Self-test changed saved CAN settings'
    assert report['can_interface_choices'] == ['vector_vn1630a', 'vector_vn1610', 'pcan']
    assert report['bootloader_has_model_control'] is False
    previous = root / 'dist/BootloaderFix_20261021_v5_VN1610/BatteryMonitor'
    assert dlls(release) == dlls(previous), 'Unexpected DLL dependency changes'
    result = dict(directory=str(release),
                  git_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
                  embedded_sources=list(names), startup=report, unchanged_dlls=len(dlls(release)),
                  package_entries=[path.name for path in release.iterdir()],
                  exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
                  hardware_full_flash=False)
    (root / 'build/release-verification-v6.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'startup'},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
