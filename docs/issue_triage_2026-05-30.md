# Tethered Alarm — 前十大 Issue 分類報告

> 產出日期：2026-05-30
> 方法：Haiku 4.5 廣度掃描 5 個模組群（共撈出 32 個 raw issue）→ Opus 4.8 去重、排名、歸納三大類
> 分支：`game/reverse_pacman`

## 整體總評

核心玩法可運作，但有多個會直接破壞**可玩性**或**同步正確性**的缺陷。最嚴重的問題集中在三個面向：

1. 多執行緒共享狀態幾乎全面缺乏同步保護（CPython GIL 暫時掩蓋風險，但脆弱且不可移植）。
2. 網路同步與狀態正確性問題（重連無效、封包未驗證 NaN/inf、方向向量覆蓋造成預測漂移、例外被靜默吞掉）。
3. 直接破壞玩法的邏輯／資源缺陷，其中 `dodge_knives` 的 `BUTTON_GATE_MAP` 為空字典是**阻斷級** bug。

> 查證註記：`sound_manager.py:33` 的 `master_volume=0.0` 雖忽略傳入參數，但第 42 行 `set_master_volume()` 會立即覆蓋修正，**並非**「預設靜音」的 critical 問題，已下修為可維護性層級的 dead assignment。

健康度：**中等偏弱**。建議優先修復阻斷級玩法 bug，並引入統一的執行緒安全佇列機制。

---

## 🥇 第一類：穩定性與多執行緒同步

**分類理由**：涵蓋所有在背景執行緒與主迴圈／伺服器事件處理器之間共享可變狀態卻缺乏鎖或佇列保護的問題。共通根因是「跨執行緒共享狀態無同步機制」，在 CPython GIL 下表面可運作，但在迭代中修改列表、房長重指派、斷線任務追蹤等情境下會產生競態，屬最難重現也最難除錯的一類。修復方向一致：改用 `threading.Queue` / `threading.Lock` 或集中化狀態變更並加鎖。

| 排名 | 標題 | 檔案 | 行號 | 嚴重度 |
|---|---|---|---|---|
| #2 | engine 三個 `_pending_*` 共享列表跨執行緒存取無同步 | `game_client/engine.py` | 83/133/293-305、94/137-145/250-270、99/153/287-290 | high |
| #5 | 伺服器斷線處理的房長重指派與計時任務存在競態 | `server/main.py` | 110-119、116-118、129-131 | high |
| #9 | 測試共享 `results` 列表多執行緒寫入無鎖 | `tests/test_connection.py` | 6, 17, 22 | high |

**#2** — `_pending_remote_updates`、`_pending_teammate_events`、`_pending_game_events` 三個列表皆由網路背景執行緒寫入、主迴圈 `_flush_pending()` 讀取，全程無鎖。teammate_events 在主迴圈迭代期間若被背景執行緒修改可能拋例外。修復：統一改用 `threading.Queue` 取代 list，將生產/消費解耦並保證執行緒安全。

**#5** — disconnect 處理器中房長斷線時以 `next(iter(room.players))` 重指派房長（117），與其他玩家的 ready 檢查並行時可能造成新舊房長 SID 不一致；同時 `asyncio.create_task()` 建立的逾時任務未被追蹤，任務內例外會被吞掉。應對房間狀態變更加鎖，並以 `ensure_future` + done callback 追蹤任務完成。

**#9** — 全域 `results` 列表由多執行緒於 17、22 行並行 `append`，雖 CPython 下 append 為原子操作，但屬不可移植寫法。應加 `threading.Lock()` 保護，與 engine 的同步修復方向一致，可作為團隊執行緒安全規範的示範。

---

## 🥈 第二類：網路同步與資料正確性

**分類理由**：聚焦於連線生命週期、封包資料驗證、遠端狀態預測（Dead Reckoning）與網路例外可見性。共通影響是：在實際多人連線且網路抖動時導致畫面失步、位置跳躍或封包/伺服器狀態被汙染，且多處 `try/except: pass` 讓這些故障難以診斷。與第一類差別在於根因不是執行緒競態，而是網路協定處理與數值正確性。

| 排名 | 標題 | 檔案 | 行號 | 嚴重度 |
|---|---|---|---|---|
| #3 | Socket.IO 重連邏輯無效，`wait()` 後 `break` 不可達 | `game_client/network.py` | 56-66 | high |
| #4 | 位置廣播未驗證 NaN/inf，且遠端方向向量覆蓋造成預測偏移 | `game_client/network.py`、`game_client/games/reverse_pacman.py` | network.py:143-148、reverse_pacman.py:601-602 | high |
| #7 | 關鍵網路操作 `try/except: pass` 靜默吞例外 | `game_client/games/reverse_pacman.py`、`game_client/engine.py` | reverse_pacman.py:347-353/361-367/445-452/495-504/831、engine.py:358-361 | medium |
| #8 | Dead Reckoning 假設方向為單位向量但未驗證 | `game_client/sync_helpers.py` | 75-77 | medium |

**#3** — `_start()` 為 `while True` 迴圈，`connect(wait=True)` 成功後呼叫 `sio.wait()` 會阻塞直到斷線，斷線後因例外才會 retry；而正常結束路徑的 `break`（66）在 `wait()` 正常返回時才到達，重連語意混亂。雖 Client 已設 `reconnection=True` 可部分緩解，但自寫迴圈與內建重連疊加易造成重複連線或無法乾淨退出。應釐清由內建重連負責、移除衝突的手動迴圈邏輯。

**#4** — 合併兩個同質的同步正確性問題：`send_position()` 未驗證 x/y/dx/dy 是否為 NaN/inf，異常值會汙染伺服器狀態與其他客戶端；`reverse_pacman` 第 601-602 行以未規範化的網路原始 dx/dy 無條件覆蓋 `current_dx/dy`，使速度向量與 visual_key 方向及 Dead Reckoning 預測不一致，導致位置漂移。修復：emit 前以 `math.isnan/isinf` 驗證並丟棄異常值，遠端方向向量套用前先正規化。

**#7** — 合併多處同質問題：`pacman_pos`、`gate_state`、`player_rescued`、`rescue_progress`、engine 位置廣播等網路送出皆包在 `try/except Exception: pass`。其中 `pacman_pos` 與 `gate_state` 失敗會直接造成各客戶端遊戲狀態分歧卻無從察覺。應至少 log 例外，必要時設定重試旗標，以恢復同步故障的可見性。

**#8** — `apply_server_update` 預測 `target_x += dr_dx * speed * dt` 假設 `dr_dx/dr_dy` 為單位向量，但無正規化或驗證。配合 #4 的方向覆蓋問題，一旦收到非單位向量會造成預測過衝或不足。應在套用前正規化方向向量，集中於 sync_helpers 處理可一併解決多個來源。

---

## 🥉 第三類：玩法阻斷邏輯與資源管理

**分類理由**：直接破壞可玩性或會隨遊玩累積的資源/邏輯缺陷，包含一個阻斷級 bug、測試會直接拋 NameError 的缺陷，以及記憶體/資源洩漏。不屬於同步或網路協定範疇，而是單機可重現的明確邏輯與生命週期錯誤，影響面從「遊戲不能玩」到「長時間遊玩劣化」。

| 排名 | 標題 | 檔案 | 行號 | 嚴重度 |
|---|---|---|---|---|
| #1 | `dodge_knives` 的 `BUTTON_GATE_MAP` 為空字典，所有閘門永不開啟 | `game_client/games/dodge_knives.py` | 54 | **critical** |
| #6 | `test_alarm_flow` 使用未定義變數導致測試直接拋 NameError | `tests/test_alarm_flow.py` | 143（並含 80-86 play 參數錯誤） | high |
| #10 | 資源洩漏：visual_registry 快取與測試/伺服器連線、Sound 物件未釋放 | `game_client/visual_registry.py`、`server/main.py`、`tests/test_connection.py` | visual_registry.py:65-69、server/main.py:54-68、test_connection.py:11-19 | medium |

**#1（critical）** — 已實地查證第 54 行 `BUTTON_GATE_MAP = {}` 始終為空，`_evaluate_gates()` 依此判斷踩鈕開門，導致閘門機制完全失效、逃生路徑無法開啟，屬阻斷遊戲核心玩法的 critical bug。應比照 `reverse_pacman.py` 第 84-89 行補上 4 組按鈕-閘門映射。

**#6** — 合併兩個測試缺陷：第 143 行使用的 `busy/busy_after` 僅在 111-115 的 else 區塊定義，使用 `StubSoundManager` 時不進入 else 而拋 NameError；80-86 行 play 失敗回退路徑參數組合錯誤使 `play_called` 永不為真，測試無法驗證真實音效播放。應在 else 之前初始化變數並修正 play 呼叫參數，否則測試套件無法可靠把關。

**#10** — 合併多個資源生命週期問題：`clear_cache()` 只清 `_cache` 未清 `_tags`，跨關卡累積洩漏（應加 `_tags.clear()`）；server `play_test_alarm` 的 Sound 物件重複建立未釋放，宜改用 `pygame.mixer.Channel` 管理；`test_connection` 的 sio 連線未以 try-finally 確保 disconnect。皆為隨使用次數累積的資源洩漏，修復方向一致：補齊清理路徑與 finally 區塊。

---

## 建議修復優先順序

1. **立刻修 #1**（`BUTTON_GATE_MAP` 空字典）— 阻斷級，比照 `reverse_pacman.py:84-89` 補 4 組映射即可，改動最小、效益最大。
2. **修 #6** 讓測試套件能可靠把關。
3. **系統性處理第一類**：引入統一的 `threading.Queue` 機制取代裸 list，並建立團隊執行緒安全規範。
