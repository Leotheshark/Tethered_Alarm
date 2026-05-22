# 新增小遊戲指南

## 步驟（只需要這三步，不需要改任何其他檔案）

### 1. 在這個資料夾新增一個 `.py` 檔案
檔名用 snake_case，例如 `bomb_defuse.py`。這個名稱就是伺服器廣播時用的遊戲 ID。

### 2. 繼承 `BaseLogicInterface` 並實作 8 個方法

```python
from games.base_game import BaseLogicInterface

class BombDefuse(BaseLogicInterface):
    def __init__(self, socket_client, player_id_list):
        super().__init__(socket_client, player_id_list)
        self.local_color = socket_client.player_color  # 必須有這個屬性，Renderer 會用到
        # ... 初始化你的遊戲狀態

    def on_enter(self, params=None): ...
    def on_exit(self): ...
    def handle_event(self, event_data): ...   # 接收 move / rescue_start / rescue_stop 等輸入
    def update(self, dt): ...
    def get_render_data(self) -> dict: ...    # 回傳渲染器需要的資料
    def is_cleared(self) -> bool: ...
    def get_sync_data(self) -> dict: ...
    def receive_sync_data(self, data): ...
```

> **注意**：你的類別必須有 `self.local_color` 屬性（`socket_client.player_color`），
> 引擎在呼叫 `renderer.draw_game(render_data, game.local_color)` 時會用到。

### 3. 在 server/main.py 的 start_game 裡把遊戲名稱換成你的

```python
await sio.emit("start_minigame", {"game": "bomb_defuse"}, room=room_id)
```

---

## 引擎自動幫你做的事

- **自動發現**：引擎啟動時掃描這個資料夾，找到所有繼承 `BaseLogicInterface` 的類別並自動註冊，不需要改 `engine.py`。
- **輸入傳遞**：WASD 移動會以 `handle_event({"type": "move", "dx": ..., "dy": ...})` 傳入。E 鍵按下/放開會傳 `rescue_start` / `rescue_stop`。
- **網路同步**：引擎每 50ms 呼叫你的 `get_sync_data()` 並廣播，收到封包時呼叫 `receive_sync_data(data)`。
- **通關偵測**：`is_cleared()` 回傳 `True` 時引擎自動呼叫 `on_exit()`。

## 網路廣播

在遊戲邏輯裡直接呼叫：

```python
self.socket_client.send_game_event({"type": "my_event", "data": ...})
```

其他客戶端的 `receive_sync_data` 就會收到這包資料。

## 渲染

`get_render_data()` 回傳任意字典，然後在 `renderer.py` 的 `draw_game()` 裡根據你的遊戲客製化繪製邏輯（需要改 `renderer.py`，但只是加 `elif` 分支，不影響其他遊戲）。
