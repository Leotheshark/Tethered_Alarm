"""
共用的資源/執行檔路徑解析工具。

開發模式（直接 python 執行）與 PyInstaller 打包後（frozen）的目錄結構不同：
  - 開發模式：資源就在各模組旁的相對路徑（os.path.dirname(__file__)）。
  - PyInstaller --onedir：所有 datas 被攤平到一個暫存/內部根目錄，
    路徑由 sys._MEIPASS 指出，原本的 __file__ 相對結構不保證成立。

此模組統一這兩種情況：呼叫端只要傳「相對於專案根的路徑片段」，
就能拿到正確的絕對路徑，不必各自判斷是否 frozen。
"""
import os
import sys


def is_frozen():
    """判斷目前是否執行於 PyInstaller 打包後的環境。"""
    return getattr(sys, "frozen", False)


def get_base_dir():
    """回傳專案資源根目錄。

    - frozen：PyInstaller 把 datas 解到 sys._MEIPASS 指向的目錄，
      所有以「專案根」為基準加入的資源都掛在這底下。
    - 開發模式：本檔案位於專案根，dirname(__file__) 即為根目錄。
    """
    if is_frozen():
        # 正常情況下 frozen 必有 _MEIPASS；保留 fallback 以防極端打包異常時不致直接崩潰。
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(*parts):
    """組出資源的絕對路徑。

    傳入相對於專案根的路徑片段，例如：
        resource_path("game_client", "assets", "sounds", "click.ogg")
    在開發與打包兩種環境都會回傳可用的絕對路徑。
    """
    return os.path.join(get_base_dir(), *parts)
