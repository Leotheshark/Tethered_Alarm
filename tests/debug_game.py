"""
快速測試腳本：跳過大廳與伺服器，直接啟動遊戲視窗。
用法：python tests/debug_game.py
"""
import subprocess
import sys
import os

env = os.environ.copy()
env['DEBUG_MODE'] = '1'          # 跳過大廳，直接開視窗
env['DEBUG_MINIGAME'] = '1'      # 跳過伺服器，直接載入 reverse_pacman

# tests/ -> game_client/ -> project_root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
game_client = os.path.join(project_root, 'game_client', 'main.py')
subprocess.run([sys.executable, game_client], env=env)
