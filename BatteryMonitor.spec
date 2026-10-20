# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

# 构建时只允许项目 Python 和 Windows 系统目录参与 DLL 搜索。
# 继承开发工具的 PATH 会误收集 Poppler 的同名 ICU DLL，QtCore 所需
# 的 Windows ICU 导出函数在其中不存在，导致冻结程序启动时报错。
_windows_root = Path(os.environ.get('SystemRoot', r'C:\Windows')).resolve()
_build_path = [Path(sys.executable).parent, Path(sys.base_prefix),
               _windows_root / 'System32', _windows_root]
os.environ['PATH'] = os.pathsep.join(str(path) for path in _build_path)

block_cipher = None

# 把 Vector XL Driver Library 的 vxlapi64.dll、PCAN 的 PCANBasic.dll 一并打包（API 层 DLL）。
# 注意：这只能让 exe 自带这些 DLL（不再依赖 System32 中的拷贝），
# 真正与 CAN 硬件通信仍需要安装对应驱动（内核驱动 + 服务）。
_vector_dll = os.path.join(
    os.environ.get("SystemRoot", r"C:\Windows"), "System32", "vxlapi64.dll"
)
_pcan_dll = os.path.join(
    os.environ.get("SystemRoot", r"C:\Windows"), "System32", "PCANBasic.dll"
)
_binaries = []
if os.path.isfile(_vector_dll):
    _binaries.append((_vector_dll, '.'))
if os.path.isfile(_pcan_dll):
    _binaries.append((_pcan_dll, '.'))

a = Analysis(
    ['Main.py'],
    pathex=[],
    binaries=_binaries,
    datas=[
        ('System3.dbc', '.'),
        ('appicon.ico', '.'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'pyqtgraph',
        'can',
        'can.interfaces.vector',
        'can.interfaces.pcan',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[]
)

# Windows ICU 由操作系统提供。保留构建来源检查，防止将 PATH 中
# 的同名第三方 DLL 再次带进发布包。
_allowed_roots = (Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve(), _windows_root)
for _destination, _source, _kind in a.binaries:
    _resolved = Path(_source).resolve()
    if not any(_resolved.is_relative_to(root) for root in _allowed_roots):
        raise RuntimeError(f'发布包发现非项目/系统 DLL 来源: {_source}')
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in {'icuuc.dll', 'icuin.dll', 'icu.dll'}]

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BatteryMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='appicon.ico'   # ⭐ EXE图标
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='BatteryMonitor'
)
