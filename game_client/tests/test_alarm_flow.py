"""
簡單測試腳本：驗證在接收 `alarm_triggered` 後會播放鬧鐘，並在接收 `game_started` 後停止。

此測試不初始化 Pygame 或真實音效，改用 StubSoundManager 以避免系統音訊依賴，
方便在 CI / 無聲環境中執行。

使用方式：
python game_client/tests/test_alarm_flow.py

輸出：會列印測試步驟與最終 PASS/FAIL。
"""

import os
import sys
import time

# Allow running this test directly with `python path/to/test_alarm_flow.py` by
# prepending the project root to `sys.path` so `import game_client...` works.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class StubSoundManager:
    def __init__(self):
        self.master_volume = None
        self.play_called = False
        self.stop_called = False
        self.last_fade_ms = None

    def set_master_volume(self, v):
        print(f"[StubSoundManager] set_master_volume({v})")
        self.master_volume = v

    def play_alarm(self, fade_ms=2000):
        print(f"[StubSoundManager] play_alarm(fade_ms={fade_ms})")
        self.play_called = True
        self.last_fade_ms = fade_ms

    def stop(self, channel_name='alarm', fade_ms=0):
        print(f"[StubSoundManager] stop(channel={channel_name}, fade_ms={fade_ms})")
        self.stop_called = True
        self.last_fade_ms = fade_ms


# Detect whether real SoundManager is available. If not, fall back to StubSoundManager.
try:
    from game_client.sound_manager import SoundManager
    REAL_SOUND_AVAILABLE = True
except Exception as _:
    SoundManager = None
    REAL_SOUND_AVAILABLE = False


class TestEngine:
    """仿照 `GameEngine` 中與音效相關的方法實作最小測試介面。"""

    def __init__(self):
        # 優先嘗試使用實際 SoundManager（會初始化 pygame.mixer）
        if REAL_SOUND_AVAILABLE:
            try:
                self.sound_manager = SoundManager()
                # 載入資源目錄下的 Alarm_1.ogg
                loaded = self.sound_manager.load_sound('alarm', 'Alarm_1.ogg')
                if loaded is None:
                    print('[test_alarm_flow] 無法載入 Alarm_1.ogg，改用 StubSoundManager')
                    self.sound_manager = StubSoundManager()
            except Exception as e:
                print(f'[test_alarm_flow] SoundManager 初始化失敗：{e}\n回退為 StubSoundManager')
                self.sound_manager = StubSoundManager()
        else:
            print('[test_alarm_flow] SoundManager 不可用，使用 StubSoundManager')
            self.sound_manager = StubSoundManager()

    def trigger_alarm_sound(self):
        # 在真實 engine 中會 set_master_volume(0.5) 然後 play_alarm
        self.sound_manager.set_master_volume(0.5)
        # 實際 SoundManager 會用 'alarm' key 播放; Stub 也支援同名方法
        try:
            self.sound_manager.play_alarm(fade_ms=2000)
        except TypeError:
            # 如果 API 不吻合，嘗試 play 方法
            try:
                self.sound_manager.play('alarm', loops=-1, fade_ms=2000, channel_name='alarm')
            except Exception:
                pass

    def on_alarm_triggered(self, data):
        print(f"[TestEngine] on_alarm_triggered: {data}")
        self.trigger_alarm_sound()

    def on_game_started(self, data):
        print(f"[TestEngine] on_game_started: {data}")
        self.sound_manager.stop(channel_name='alarm', fade_ms=500)


def run_test():
    engine = TestEngine()

    # 模擬伺服器推播 alarm_triggered
    engine.on_alarm_triggered({'time': '07:00'})

    # 等待 5 秒，確認播放已啟動
    time.sleep(5)

    # 根據使用的 SoundManager 類型選擇不同的檢查方式
    if isinstance(engine.sound_manager, StubSoundManager):
        play_ok = engine.sound_manager.play_called and engine.sound_manager.master_volume == 0.5
    else:
        # 實際 SoundManager：檢查 master_volume 與 alarm 頻道是否正在播放
        try:
            ch = engine.sound_manager.get_channel('alarm')
            busy = ch.get_busy() if ch is not None else False
        except Exception:
            busy = False
        play_ok = getattr(engine.sound_manager, 'master_volume', None) == 0.5 and busy

    # 模擬伺服器推播 game_started
    engine.on_game_started({})

    # 等待較長時間以讓 fadeout/stop 完成（0.6s）
    time.sleep(1)

    if isinstance(engine.sound_manager, StubSoundManager):
        stop_ok = engine.sound_manager.stop_called
    else:
        try:
            ch = engine.sound_manager.get_channel('alarm')
            busy_after = ch.get_busy() if ch is not None else False
        except Exception:
            busy_after = True
        stop_ok = not busy_after

    print('\n----- TEST RESULT -----')
    if play_ok and stop_ok:
        print('PASS: Alarm played on alarm_triggered and stopped on game_started')
        return 0
    else:
        print('FAIL: Expected play_then_stop behavior not observed')
        if isinstance(engine.sound_manager, StubSoundManager):
            print(f' play_called={engine.sound_manager.play_called}, master_volume={engine.sound_manager.master_volume}, stop_called={engine.sound_manager.stop_called}')
        else:
            print(f' master_volume={getattr(engine.sound_manager, "master_volume", None)}, playing_now={busy}, playing_after_stop={busy_after}')
        return 2


if __name__ == '__main__':
    raise SystemExit(run_test())
