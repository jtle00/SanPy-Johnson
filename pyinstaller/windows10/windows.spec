# -*- mode: python ; coding: utf-8 -*-


block_cipher = None


a = Analysis(
    ['..\\..\\sanpy\\interface\\sanpy_app.py'],
    pathex=[],
    binaries=[],
    datas=[('libblosc2.dll', 'tables'),
        ('..\\..\\sanpy\\interface\\icons\\sanpy_transparent.png', '.'), # window icon
        ('..\\..\\sanpy\\_userFiles','_userFiles'),
        ('..\\..\\sanpy\\detection-presets', 'detection-presets')],
    hiddenimports=['tables', 'pkg_resources'],
    hookspath=[],
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
    name='SanPy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='..\\..\\sanpy\\interface\\icons\\sanpy_transparent.icns', # Desktop Icon
)

