# --- 引入工具箱 ---
from enum import Enum  # 用來建立「列舉」型態，讓狀態名稱更清楚

# 定義所有可能的遊戲狀態
class State(Enum):
    SETUP   = "setup"    # 設定中（例如：輸入名字、房間號）
    WAITING = "waiting"  # 等待中（在大廳等待隊友）
    ALARM   = "alarm"    # 鬧鐘響起（準備進入遊戲）
    GAME    = "game"     # 遊戲進行中
    RESULT  = "result"   # 結算畫面

# 合法的狀態轉換表：定義哪些狀態可以跳到哪些狀態
# 避免程式發生「從設定中直接跳到結算」這種不合理的狀況
VALID_TRANSITIONS = {
    State.SETUP:   [State.WAITING],
    State.WAITING: [State.ALARM, State.SETUP],
    State.ALARM:   [State.GAME],
    State.GAME:    [State.RESULT],
    State.RESULT:  [State.SETUP],
}

# 狀態機管理器：負責控制目前程式在哪個階段
class StateMachine:
    def __init__(self):
        self.state = State.SETUP  # 初始狀態設為 SETUP
        self.history = []         # 紀錄狀態變化的歷史

    def transition(self, new_state: State):
        """嘗試切換到新狀態"""
        if new_state in VALID_TRANSITIONS[self.state]:
            print(f"[狀態] {self.state.value} → {new_state.value}")
            self.history.append(self.state)
            self.state = new_state
            return True
        else:
            # 如果嘗試了不合理的跳轉，會在這裡攔截
            print(f"[錯誤] 不合法的狀態轉換：{self.state.value} → {new_state.value}")
            return False

    def current(self):
        """取得目前的狀態"""
        return self.state
    
# --- 測試區域 ---
if __name__ == "__main__":
    sm = StateMachine()
    print(sm.current())                        # SETUP
    print(sm.transition(State.WAITING))        # True
    print(sm.transition(State.GAME))           # False ← 應該被擋下
    print(sm.transition(State.ALARM))          # True
    print(sm.transition(State.GAME))           # True
    print(sm.transition(State.RESULT))         # True
    print(sm.transition(State.SETUP))          # True
    
    print("✅ 狀態機測試完成")