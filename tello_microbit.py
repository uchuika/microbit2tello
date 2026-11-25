"""Yahboom ゲームハンドル + micro:bit (USB シリアル) の入力を
Tello の SDK コマンド (UDP) に中継する。

操作:
  赤ボタン       離陸 / 着陸
  緑ボタン       押している間 上昇
  青ボタン       押している間 下降
  ジョイスティック 前後左右に水平移動
  黄ボタン+スティック左右  押している間 旋回 (左右移動はしない)
  Ctrl+C         着陸して終了

使い方:
  python tello_microbit.py --dry-run   # Tello に送らず表示だけ
  python tello_microbit.py             # 実機
"""
import argparse
import queue
import socket
import sys
import threading
import time

TELLO_ADDR = ("192.168.10.1", 8889)
LOCAL_PORT = 8889
MICROBIT_VID = 0x0D28

ADC_MAX = 1023
ADC_CENTER = 512
CENTER_TOLERANCE = 150   # 起動時にこれ以上ずれていたらスティックが倒れていたとみなす
DEADZONE = 15            # 中心付近の不感帯 (% )
MOVE_SPEED = 60          # 水平移動の最大速度 (rc の値, -100..100)
YAW_SPEED = 60           # 旋回の最大速度
UD_SPEED = 40            # 上昇・下降の速度
RC_INTERVAL = 0.1        # rc を送る間隔 (秒)
TAKEOFF_HOLD = 4.0       # 離陸直後に rc を送らない時間 (秒)
IDLE_KEEPALIVE = 10.0    # 地上待機中の keepalive 間隔 (秒)


def stick_to_speed(raw, center, max_speed=MOVE_SPEED):
    """スティックの生の値 (0..1023) を rc の速度に変換する。

    中心より小さい値 (前・右に倒した側) を正にする。
    中心からのずれを ±100% にし、不感帯を除いて最大速度に比例させる。
    """
    dev = center - raw
    span = center if dev > 0 else ADC_MAX - center
    percent = max(-100.0, min(100.0, dev * 100.0 / span))
    if abs(percent) <= DEADZONE:
        return 0
    sign = 1 if percent > 0 else -1
    return sign * round((abs(percent) - DEADZONE) / (100 - DEADZONE) * max_speed)


class Controller:
    """ハンドルの入力から Tello のコマンドを決める (通信はしない)。"""

    def __init__(self):
        self.flying = False
        self.prev_red = 0
        self.center_fb = None   # P1 (前後) の中心値
        self.center_lr = None   # P2 (左右) の中心値
        self.fb = self.lr = self.ud = self.yaw = 0

    @staticmethod
    def _calibrate(raw):
        return raw if abs(raw - ADC_CENTER) < CENTER_TOLERANCE else ADC_CENTER

    def update(self, p1, p2, red, green, blue, yellow=0):
        """1 行分の入力を処理し、すぐ送るべきコマンドのリストを返す。"""
        if self.center_fb is None:  # 最初の値を中心として記録
            self.center_fb = self._calibrate(p1)
            self.center_lr = self._calibrate(p2)

        self.fb = stick_to_speed(p1, self.center_fb)
        side = stick_to_speed(p2, self.center_lr, YAW_SPEED if yellow else MOVE_SPEED)
        if yellow:  # 黄を押している間は左右が旋回になる (右に倒すと時計回り)
            self.lr, self.yaw = 0, side
        else:
            self.lr, self.yaw = side, 0
        self.ud = (UD_SPEED if green else 0) - (UD_SPEED if blue else 0)

        cmds = []
        if red and not self.prev_red:  # 押した瞬間だけ反応 (エッジ検出)
            if self.flying:
                cmds += ["rc 0 0 0 0", "land"]
                self.flying = False
            else:
                cmds.append("takeoff")
                self.flying = True
        self.prev_red = red
        return cmds

    def rc(self):
        """現在の状態に対応する rc コマンド (飛行中でなければ None)。"""
        if not self.flying:
            return None
        return "rc {} {} {} {}".format(self.lr, self.fb, self.ud, self.yaw)


def parse_line(line):
    parts = line.strip().split(",")
    if len(parts) not in (5, 6):  # 5: p1,p2,R,G,B / 6: 末尾に黄ボタン Y が付く
        return None
    try:
        return [int(p) for p in parts]
    except ValueError:
        return None


def find_microbit_port():
    from serial.tools import list_ports
    for p in list_ports.comports():
        if p.vid == MICROBIT_VID:
            return p.device
    return None


class Tello:
    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.sock = None
        self.got_ok = threading.Event()
        self.responses = queue.Queue()
        self.battery = None
        if not dry_run:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind(("", LOCAL_PORT))
            self.sock.settimeout(0.5)
            self._running = True
            threading.Thread(target=self._recv_loop, daemon=True).start()

    def send(self, cmd, quiet=False):
        if self.dry_run:
            if not quiet:
                print("[dry-run] ->", cmd)
            return
        if not quiet:
            print("->", cmd)
        try:
            self.sock.sendto(cmd.encode("utf-8"), TELLO_ADDR)
        except OSError as e:  # Wi-Fi 切り替え中など
            if not quiet:
                print("   送信失敗:", e)

    def send_and_wait(self, cmd, timeout=10.0):
        """コマンドを送り、Tello の応答 ('ok' / 'error' ...) を待つ。
        タイムアウトしたら None を返す。dry-run では短く待って 'ok' を返す。"""
        if self.dry_run:
            self.send(cmd)
            time.sleep(0.2)
            return "ok"
        while not self.responses.empty():  # 古い応答を捨てる
            try:
                self.responses.get_nowait()
            except queue.Empty:
                break
        self.send(cmd)
        try:
            return self.responses.get(timeout=timeout)
        except queue.Empty:
            return None

    def wait_connected(self):
        """Tello が 'command' に ok を返すまで 1 秒ごとに送り続ける。"""
        if self.dry_run:
            return
        print("Tello の Wi-Fi (TELLO-xxxxxx) への接続を待っています...")
        while not self.got_ok.is_set():
            self.send("command", quiet=True)
            self.got_ok.wait(1.0)
        print("Tello に接続しました")

    def _recv_loop(self):
        while self._running:
            try:
                data, _ = self.sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break
            text = data.decode("utf-8", errors="replace").strip()
            if text == "ok":
                self.got_ok.set()
            if text.isdigit():  # battery? の応答 (send_and_wait の応答と混ざらないよう別扱い)
                self.battery = int(text)
            else:
                self.responses.put(text)
            print(time.strftime("%H:%M:%S"), "<-", text)

    def close(self):
        if self.sock:
            self._running = False
            self.sock.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="micro:bit の COM ポート (省略時は自動検出)")
    ap.add_argument("--dry-run", action="store_true", help="Tello に送らず表示だけ")
    ap.add_argument("--show-input", action="store_true", help="micro:bit の入力を表示")
    args = ap.parse_args(argv)

    import serial

    port = args.port or find_microbit_port()
    if not port:
        sys.exit("micro:bit が見つかりません。USB でつないでください (--port COMx で指定も可)。")
    print("micro:bit:", port)
    ser = serial.Serial(port, 115200, timeout=0.02)

    tello = Tello(args.dry_run)
    ctrl = Controller()
    try:
        tello.wait_connected()
    except KeyboardInterrupt:
        ser.close()
        tello.close()
        return
    tello.send("command")
    tello.send("battery?")
    ser.reset_input_buffer()

    last_rc = None
    next_rc = 0.0
    hold_until = 0.0
    next_keepalive = time.monotonic() + IDLE_KEEPALIVE
    buf = b""
    try:
        while True:
            buf += ser.read(256)
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                vals = parse_line(raw.decode("ascii", errors="ignore"))
                if vals is None:
                    continue
                if args.show_input:
                    print("input", vals)
                for cmd in ctrl.update(*vals):
                    tello.send(cmd)
                    if cmd == "takeoff":
                        hold_until = time.monotonic() + TAKEOFF_HOLD
                    last_rc = None

            now = time.monotonic()
            if ctrl.flying and now >= hold_until and now >= next_rc:
                rc = ctrl.rc()
                tello.send(rc, quiet=(rc == last_rc))  # 変化したときだけ表示
                last_rc = rc
                next_rc = now + RC_INTERVAL
            if not ctrl.flying and now >= next_keepalive:
                tello.send("battery?", quiet=args.dry_run)
                next_keepalive = now + IDLE_KEEPALIVE
    except KeyboardInterrupt:
        print("\n終了します")
    finally:
        if ctrl.flying:
            tello.send("rc 0 0 0 0")
            tello.send("land")
            time.sleep(0.5)
        ser.close()
        tello.close()


if __name__ == "__main__":
    main()
