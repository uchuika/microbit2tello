"""ブロックプログラムの検証と実行ロジック (通信は Tello オブジェクト経由のみ)。

ブラウザの Blockly が作る簡易 JSON:
  {"events": [
     {"kind": "press",       "input": "green",  "script": [<動作>...]},
     {"kind": "hold",        "input": "blue",   "moves":  [<動き続ける>...]},
     {"kind": "stick_drive", "speed": 60}
  ]}
動作:         takeoff / land / move{dir,cm} / turn{dir,deg} / flip{dir} / wait{sec} / repeat{times,body}
動き続ける:   drive{dir,speed} / spin{dir,speed}
赤ボタンは常に 離陸/着陸 に固定 (ここでは変更できない)。
"""
import threading

from tello_microbit import ADC_CENTER, CENTER_TOLERANCE, stick_to_speed

INPUTS = ("green", "blue", "stick_fwd", "stick_back", "stick_left", "stick_right")
DIRS6 = ("forward", "back", "left", "right", "up", "down")
FLIP_DIRS = ("forward", "back", "left", "right")
TURN_DIRS = ("right", "left")
STICK_TRIGGER = 50       # スティックを「倒した」とみなす値 (-100..100 に換算)
MAX_NODES = 300
MAX_DEPTH = 3
RC_MIN, RC_MAX = -100, 100

DEFAULT_PROGRAM = {"events": [
    {"kind": "hold", "input": "green", "moves": [{"op": "drive", "dir": "up", "speed": 40}]},
    {"kind": "hold", "input": "blue", "moves": [{"op": "drive", "dir": "down", "speed": 40}]},
    {"kind": "stick_drive", "speed": 60},
]}


def _num(value, lo, hi, name, integer=True):
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError("{} は数字にしてください".format(name))
    v = max(lo, min(hi, v))
    return int(round(v)) if integer else round(v, 1)


def _choice(value, choices, name):
    if value not in choices:
        raise ValueError("{} が正しくありません: {}".format(name, value))
    return value


class _Counter:
    def __init__(self):
        self.n = 0

    def tick(self):
        self.n += 1
        if self.n > MAX_NODES:
            raise ValueError("ブロックが多すぎます (最大 {} 個)".format(MAX_NODES))


def _node_id(node):
    nid = node.get("id")
    return nid[:64] if isinstance(nid, str) else None


def _validate_script(script, depth, counter):
    if not isinstance(script, list):
        raise ValueError("スクリプトの形が正しくありません")
    out = []
    for node in script:
        if not isinstance(node, dict):
            raise ValueError("ブロックの形が正しくありません")
        counter.tick()
        op = node.get("op")
        item = {"op": op}
        if op in ("takeoff", "land"):
            pass
        elif op == "move":
            item["dir"] = _choice(node.get("dir"), DIRS6, "うごく向き")
            item["cm"] = _num(node.get("cm"), 20, 500, "きょり")
        elif op == "turn":
            item["dir"] = _choice(node.get("dir"), TURN_DIRS, "まわる向き")
            item["deg"] = _num(node.get("deg"), 1, 360, "角度")
        elif op == "flip":
            item["dir"] = _choice(node.get("dir"), FLIP_DIRS, "宙返りの向き")
        elif op == "wait":
            item["sec"] = _num(node.get("sec"), 0.1, 10, "待つ秒数", integer=False)
        elif op == "repeat":
            if depth >= MAX_DEPTH:
                raise ValueError("くり返しの中にくり返しを入れすぎです")
            item["times"] = _num(node.get("times"), 1, 10, "くり返す回数")
            item["body"] = _validate_script(node.get("body", []), depth + 1, counter)
        else:
            raise ValueError("使えないブロックです: {}".format(op))
        nid = _node_id(node)
        if nid:
            item["id"] = nid
        out.append(item)
    return out


def _validate_moves(moves, counter):
    if not isinstance(moves, list):
        raise ValueError("「押している間」の形が正しくありません")
    out = []
    for node in moves:
        if not isinstance(node, dict):
            raise ValueError("ブロックの形が正しくありません")
        counter.tick()
        op = node.get("op")
        if op == "drive":
            item = {"op": op, "dir": _choice(node.get("dir"), DIRS6, "うごく向き")}
        elif op == "spin":
            item = {"op": op, "dir": _choice(node.get("dir"), TURN_DIRS, "まわる向き")}
        else:
            raise ValueError("「押している間」には「動き続ける」ブロックだけ入れられます")
        item["speed"] = _num(node.get("speed"), 10, 100, "速さ")
        out.append(item)
    return out


def validate_program(data):
    """ブラウザから来た JSON を検証・正規化する。不正なら ValueError (日本語)。"""
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        raise ValueError("プログラムの形が正しくありません")
    counter = _Counter()
    events = []
    for ev in data["events"]:
        if not isinstance(ev, dict):
            raise ValueError("イベントの形が正しくありません")
        counter.tick()
        kind = ev.get("kind")
        if kind == "press":
            events.append({"kind": kind,
                           "input": _choice(ev.get("input"), INPUTS, "ボタン"),
                           "script": _validate_script(ev.get("script", []), 0, counter)})
        elif kind == "hold":
            events.append({"kind": kind,
                           "input": _choice(ev.get("input"), INPUTS, "ボタン"),
                           "moves": _validate_moves(ev.get("moves", []), counter)})
        elif kind == "stick_drive":
            events.append({"kind": kind, "speed": _num(ev.get("speed"), 10, 100, "速さ")})
        else:
            raise ValueError("使えないイベントです: {}".format(kind))
    return {"events": events}


def _clamp(v):
    return max(RC_MIN, min(RC_MAX, int(v)))


class BlockController:
    """ハンドルの入力とブロックプログラムから Tello の動きを決める (通信はしない)。

    赤ボタンは固定で 離陸/着陸。Controller (tello_microbit.py) と同じ形で使える。
    """

    def __init__(self, program=None):
        self.program = program or validate_program(DEFAULT_PROGRAM)
        self.flying = False
        self.prev_red = 0
        self.prev_active = frozenset()
        self.center_fb = None
        self.center_lr = None
        self.fb = self.lr = self.ud = self.yaw = 0
        self.active = frozenset()
        self._pending = []
        self._lock = threading.Lock()

    def set_program(self, program):
        self.program = program

    @staticmethod
    def _calibrate(raw):
        return raw if abs(raw - ADC_CENTER) < CENTER_TOLERANCE else ADC_CENTER

    def update(self, p1, p2, red, green, blue, yellow=0):  # yellow は未使用 (6 値の行を受けるため)
        """1 行分の入力を処理し、すぐ送るべきコマンド (離陸/着陸) のリストを返す。"""
        program = self.program
        if self.center_fb is None:
            self.center_fb = self._calibrate(p1)
            self.center_lr = self._calibrate(p2)

        fb100 = stick_to_speed(p1, self.center_fb, 100)
        lr100 = stick_to_speed(p2, self.center_lr, 100)
        active = set()
        if green:
            active.add("green")
        if blue:
            active.add("blue")
        if fb100 >= STICK_TRIGGER:
            active.add("stick_fwd")
        if fb100 <= -STICK_TRIGGER:
            active.add("stick_back")
        if lr100 >= STICK_TRIGGER:
            active.add("stick_right")
        if lr100 <= -STICK_TRIGGER:
            active.add("stick_left")
        active = frozenset(active)

        fb = lr = ud = yaw = 0
        for ev in program["events"]:
            if ev["kind"] == "stick_drive":
                fb += stick_to_speed(p1, self.center_fb, ev["speed"])
                lr += stick_to_speed(p2, self.center_lr, ev["speed"])
            elif ev["kind"] == "hold" and ev["input"] in active:
                for m in ev["moves"]:
                    s = m["speed"]
                    d = m["dir"]
                    if m["op"] == "drive":
                        if d == "forward":
                            fb += s
                        elif d == "back":
                            fb -= s
                        elif d == "right":
                            lr += s
                        elif d == "left":
                            lr -= s
                        elif d == "up":
                            ud += s
                        elif d == "down":
                            ud -= s
                    else:
                        yaw += s if d == "right" else -s
        self.fb, self.lr, self.ud, self.yaw = _clamp(fb), _clamp(lr), _clamp(ud), _clamp(yaw)

        with self._lock:
            for ev in program["events"]:
                if ev["kind"] == "press" and ev["input"] in active - self.prev_active:
                    self._pending.append(ev["script"])
        self.prev_active = active
        self.active = active

        cmds = []
        if red and not self.prev_red:  # 赤ボタンは固定: 離陸 / 着陸
            if self.flying:
                cmds += ["rc 0 0 0 0", "land"]
                self.flying = False
            else:
                cmds.append("takeoff")
                self.flying = True
        self.prev_red = red
        return cmds

    def take_pending(self):
        """「押したとき」で起動されたスクリプトを取り出す。"""
        with self._lock:
            out, self._pending = self._pending, []
        return out

    def rc(self):
        if not self.flying:
            return None
        return "rc {} {} {} {}".format(self.lr, self.fb, self.ud, self.yaw)


class ScriptRunner:
    """「押したとき」のスクリプトを 1 本ずつ別スレッドで実行する。"""

    TIMEOUTS = {"takeoff": 20, "land": 20, "move": 25, "turn": 15, "flip": 15}

    def __init__(self, tello, ctrl):
        self.tello = tello
        self.ctrl = ctrl
        self._stop = threading.Event()
        self._thread = None
        self.current_id = None
        self.message = ""

    @property
    def busy(self):
        t = self._thread
        return t is not None and t.is_alive()

    def start(self, script):
        """実行中でなければ開始して True。実行中なら無視して False。"""
        if self.busy:
            return False
        self._stop.clear()
        self.message = ""
        self._thread = threading.Thread(target=self._run, args=(script,), daemon=True)
        self._thread.start()
        return True

    def stop(self, join=True):
        self._stop.set()
        t = self._thread
        if join and t is not None and t is not threading.current_thread():
            t.join(timeout=2.0)

    def _run(self, script):
        try:
            self._exec(script)
        finally:
            self.current_id = None

    def _fail(self, msg):
        self.message = msg
        self._stop.set()

    def _exec(self, script):
        for node in script:
            if self._stop.is_set():
                return
            self.current_id = node.get("id")
            op = node["op"]
            if op == "repeat":
                for _ in range(node["times"]):
                    self._exec(node["body"])
                    if self._stop.is_set():
                        return
            elif op == "wait":
                self._wait(node["sec"])
            else:
                self._command(node)

    def _wait(self, sec):
        remaining = sec
        while remaining > 0 and not self._stop.is_set():
            step = min(1.0, remaining)
            self._stop.wait(step)
            remaining -= step
            if self.ctrl.flying and not self._stop.is_set():
                self.tello.send("rc 0 0 0 0", quiet=True)  # 15 秒自動着陸の防止

    def _command(self, node):
        op = node["op"]
        if op == "takeoff":
            if self.ctrl.flying:
                return
            cmd = "takeoff"
        elif op == "land":
            if not self.ctrl.flying:
                return
            cmd = "land"
        else:
            if not self.ctrl.flying:
                self.message = "先に離陸してね"
                return
            if op == "move":
                cmd = "{} {}".format(node["dir"], node["cm"])
            elif op == "turn":
                cmd = "{} {}".format("cw" if node["dir"] == "right" else "ccw", node["deg"])
            else:  # flip
                cmd = "flip " + node["dir"][0]
        if op == "land":
            self.tello.send("rc 0 0 0 0")
        resp = self.tello.send_and_wait(cmd, self.TIMEOUTS[op])
        if self._stop.is_set():
            return
        if resp is None:
            self._fail("Tello から返事がありません: " + cmd)
        elif resp != "ok":
            self._fail("Tello が実行できませんでした ({}): {}".format(resp, cmd))
        elif op == "takeoff":
            self.ctrl.flying = True
        elif op == "land":
            self.ctrl.flying = False
