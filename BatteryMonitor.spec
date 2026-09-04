# -*- mode: python ; coding: utf-8 -*-
import os

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
    upx=True,
    console=False,
    icon='appicon.ico'   # ⭐ EXE图标
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name='BatteryMonitor'
)
