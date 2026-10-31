# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 —— 程序收纳盒
用法： python -m PyInstaller build.spec --noconfirm --clean
产物： dist\程序收纳盒.exe（单文件、独立、无需 Python 环境）
"""
import os

# 兼容两种调用位置（src 目录内 / 上级目录）
HERE = os.path.abspath(os.getcwd())
if not os.path.isfile(os.path.join(HERE, "src", "main.py")):
    HERE = os.path.dirname(os.path.abspath(os.getcwd()))
SRC = os.path.join(HERE, "src")
ASSETS = os.path.join(SRC, "assets")

block_cipher = None

a = Analysis(
    [os.path.join(SRC, "main.py")],
    pathex=[SRC],
    binaries=[],
    datas=[(os.path.join(ASSETS, "*"), "assets")],
    hiddenimports=["windnd", "pythoncom", "pywintypes", "win32com",
                   "win32com.client", "win32com.client.dynamic"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="程序收纳盒",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ASSETS, "launcher_orange.ico"),
)
