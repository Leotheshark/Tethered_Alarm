# PyInstaller spec for Tethered Alarm
# 單一 exe（--onedir）打包：同一支 exe 既當 server/大廳，也能用 `--game-client`
# 旗標再起一個 Pygame 遊戲進程（見 server/main.py 的 __main__ 入口分流）。
#
# Build: pyinstaller pyinstaller.spec
# 產出： dist/TetheredAlarm/TetheredAlarm.exe（連同 _internal 資料夾一起發佈）

# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

import os
from PyInstaller.utils.hooks import collect_submodules, collect_all

# SPECPATH 由 PyInstaller 在執行 spec 時注入，指向本 spec 檔所在目錄（即專案根）。
# 不可用 __file__：PyInstaller 6.x 以 exec 執行 spec，該情境下 __file__ 未定義。
base_dir = os.path.abspath(SPECPATH)

# --- 資料檔（datas）---
# 策略：把 server/ 與 game_client/ 依「原始相對結構」整包帶進 bundle，讓打包後的
# os.path.dirname(__file__) 與 base_dir/../game_client 等既有路徑邏輯原封不動成立，
# 不必改散落各處的資源讀取程式碼。
#
# game_client 的模組彼此用裸 import（from engine import ...）且引擎會動態掃描
# games/ 目錄，PyInstaller 的靜態分析抓不到，因此必須把整個 game_client 當資料帶。
datas = [
    (os.path.join(base_dir, 'server', 'static'), 'server/static'),
    (os.path.join(base_dir, 'game_client', 'assets'), 'game_client/assets'),
    (os.path.join(base_dir, 'game_client', 'games'), 'game_client/games'),
]
binaries = []
hiddenimports = []

# game_client 頂層模組（裸 import 目標）逐一列為 hiddenimport，確保被打包進 bundle。
# 註：game_client 的常數模組為 gc_constants（刻意不叫 constants，以免與 server 的
# constants.py 在打包後攤平到同一命名空間時撞名）。
hiddenimports += [
    'engine', 'renderer', 'input_handler', 'states', 'entities',
    'visual_registry', 'entity_manager', 'sound_manager', 'network',
    'system', 'gc_constants', 'gc_paths', 'sync_helpers',
]
# games/ 子模組（引擎啟動時動態 importlib 載入）。
hiddenimports += collect_submodules('games')

# uvicorn / socketio / engineio 大量使用動態 import 載入協定實作與 loop 後端，
# 必須整包收集，否則執行期才 ImportError。
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('engineio')
hiddenimports += collect_submodules('socketio')

# pywebview（Windows EdgeChromium 後端走 pythonnet/clr）與 pythonnet 是
# PyInstaller 常見踩雷點，用 collect_all 自動帶齊其 datas/binaries/submodules。
for pkg in ('webview', 'clr_loader', 'pythonnet'):
    try:
        _d, _b, _h = collect_all(pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception as _e:
        print(f"[spec] collect_all({pkg}) skipped: {_e}")

a = Analysis(
    [os.path.join(base_dir, 'server', 'main.py')],
    # pathex 同時納入專案根與 server/、game_client/：
    #   - 根目錄：讓 `from resource_path import resource_path` 找得到
    #   - server/：server 自身的 game_room / system_helper / constants 裸 import
    #   - game_client/：讓 hiddenimports 的裸 import 模組被解析
    pathex=[
        base_dir,
        os.path.join(base_dir, 'server'),
        os.path.join(base_dir, 'game_client'),
    ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TetheredAlarm',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX 對 pythonnet/pygame 的原生 DLL 偶有相容問題，關閉以求穩定（onedir 不差這點體積）。
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='TetheredAlarm',
)
