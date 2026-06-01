"""
game_client 端的資源根目錄解析工具。

game_client 的多個模組（renderer / sound_manager / visual_registry）都用
os.path.dirname(__file__) 推算 assets 目錄。這在開發模式正確，但 PyInstaller
打包後 __file__ 指向被攤平的位置（_MEIPASS 根），不再是放 assets 的
game_client 子目錄，導致圖片 / 音效 / 字體找不到。

此函式統一回傳「game_client 資源根」：
  - frozen：assets 由 spec 放在 _MEIPASS/game_client 底下。
  - 開發模式：就是本檔（game_client/）所在目錄。
呼叫端把原本的 os.path.dirname(__file__) 換成 game_client_dir() 即可。
"""
import os
import sys


def game_client_dir():
    """回傳 game_client 資源根目錄（其下有 assets/、games/）。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "game_client")
    return os.path.dirname(os.path.abspath(__file__))
