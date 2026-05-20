"""
Client Entry Point
負責系統初始化、防休眠、連線與啟動引擎。
"""
import sys
import os

# 確保當前路徑在 Python 搜尋路徑中，防止 import 失敗
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from system import prevent_sleep, allow_sleep
from engine import GameEngine

def main():
    # 1. 系統準備：防止電腦睡著
    prevent_sleep()
    
    try:
        # 2. 啟動遊戲引擎
        print("[系統] 正在啟動遊戲引擎...")
        app = GameEngine()
        app.run()
    except Exception as e:
        print(f"[崩潰] 遊戲發生錯誤：{e}")
        # 可以在這裡加入寫入 Log 檔案的邏輯
    finally:
        # 3. 關閉程式時恢復休眠設定
        allow_sleep()
        print("[系統] 程式結束，恢復休眠設定")

if __name__ == "__main__":
    main()
