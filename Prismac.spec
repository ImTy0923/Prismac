# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['Prismac.py'],
    pathex=[],
    binaries=[],
    datas=[('backgrounds', 'backgrounds'), ('chaos', 'chaos'), ('credits', 'credits'), ('effects', 'effects'), ('fonts', 'fonts'), ('gems', 'gems'), ('music', 'music'), ('soundeffects', 'soundeffects'), ('Title', 'Title')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Prismac',
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
    icon=['Game ICNS/Prismac-Mac.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Prismac',
)
app = BUNDLE(
    coll,
    name='Prismac.app',
    icon='Game ICNS/Prismac-Mac.icns',
    bundle_identifier=None,
)
