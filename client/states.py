from enum import Enum

class State(Enum):
    SETUP   = "setup"
    WAITING = "waiting"
    ALARM   = "alarm"
    GAME    = "game"
    RESULT  = "result"

# 合法的狀態轉換表
VALID_TRANSITIONS = {
    State.SETUP:   [State.WAITING],
    State.WAITING: [State.ALARM, State.SETUP],
    State.ALARM:   [State.GAME],
    State.GAME:    [State.RESULT],
    State.RESULT:  [State.SETUP],
}

class StateMachine:
    def __init__(self):
        self.state = State.SETUP
        self.history = []

    def transition(self, new_state: State):
        if new_state in VALID_TRANSITIONS[self.state]:
            print(f"[狀態] {self.state.value} → {new_state.value}")
            self.history.append(self.state)
            self.state = new_state
            return True
        else:
            print(f"[錯誤] 不合法的狀態轉換：{self.state.value} → {new_state.value}")
            return False

    def current(self):
        return self.state
    
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