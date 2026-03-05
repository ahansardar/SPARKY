# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules('actions')
hiddenimports += collect_submodules('agent')
hiddenimports += collect_submodules('memory')
hiddenimports += collect_submodules('src.llm')
hiddenimports += collect_submodules('requests')


a = Analysis(
    ['src\\ai_agent.py'],
    pathex=['.', '.\\src'],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('config', 'config'),
        ('ffmpeg-8.0.1-essentials_build', 'ffmpeg-8.0.1-essentials_build'),
        ('models', 'models'),
        ('piper', 'piper'),
        ('memory\\long_term.json', 'memory'),
        ('requirements.txt', '.'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SPARKY',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['installer\\SPARKY.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SPARKY',
)
