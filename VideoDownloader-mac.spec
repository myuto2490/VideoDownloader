# -*- mode: python ; coding: utf-8 -*-
# macOS 用 PyInstaller spec  ->  dist/VideoDownloader.app を生成する。
#   python -m PyInstaller VideoDownloader-mac.spec --noconfirm
import os

icon = 'icon.icns' if os.path.isfile('icon.icns') else None

a = Analysis(
    ['video_downloader.py'],
    pathex=[],
    binaries=[],
    datas=[],
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
    name='VideoDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,      # Finder からの起動でファイル引数を受け取れるように
    target_arch=None,         # 実行環境のアーキテクチャ（Apple Silicon なら arm64）
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='VideoDownloader',
)

app = BUNDLE(
    coll,
    name='VideoDownloader.app',
    icon=icon,
    bundle_identifier='com.myuto2490.videodownloader',
    info_plist={
        'CFBundleName': 'Video Downloader',
        'CFBundleDisplayName': 'Video Downloader',
        'CFBundleShortVersionString': '1.1.0',
        'CFBundleVersion': '1.1.0',
        'NSHighResolutionCapable': True,
        # ライト/ダークのシステム外観に自動追従する（旧 Aqua 固定にしない）
        'NSRequiresAquaSystemAppearance': False,
        'LSMinimumSystemVersion': '11.0',
        'NSHumanReadableCopyright': 'MIT License',
    },
)
