"""ブロックプログラミング版: ブラウザで組んだブロックの通りにハンドルで Tello を操縦する。

使い方:
  python block_server.py --dry-run --no-microbit   # Tello もハンドルも無しで画面だけ試す
  python block_server.py --dry-run                 # ハンドルあり、Tello には送らない
  python block_server.py                           # 実機

ブラウザで http://127.0.0.1:8000/ が開く。赤ボタンは常に 離陸/着陸。
画面の「とまる」ボタン (スペースキー) でいつでも着陸できる。
"""
import argparse
import json
import os
import sys
import threading
import time
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from block_runtime import BlockController, ScriptRunner, DEFAULT_PROGRAM, validate_program
from tello_microbit import (IDLE_KEEPALIVE, RC_INTERVAL, TAKEOFF_HOLD, Tello,
                            find_microbit_port, parse_line)

if getattr(sys, "frozen", False):  # PyInstaller で固めた exe
    ROOT = sys._MEIPASS
    _DATA = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "TelloBlocks")
else:
    ROOT = os.path.dirname(os.path.abspath(__file__))
    _DATA = ROOT
WEB_DIR = os.path.join(ROOT, "web")
DEFAULT_FILE = os.path.join(ROOT, "programs", "default.json")
CURRENT_FILE = os.path.join(_DATA, "programs", "current.json")
MAX_BODY = 1_000_000
BATTERY_INTERVAL = 10.0


class App:
    """サーバー全体で共有する状態。"""

    def __init__(self, tello):
        self.tello = tello
        self.ctrl = BlockController()
        self.runner = ScriptRunner(tello, self.ctrl)
        self.input = [512, 512, 0, 0, 0]       # 直近の入力 p1,p2,R,G,B
        self.virtual = [512, 512, 0, 0, 0]     # 画面から送る仮想入力 (--no-microbit 用)
        self.microbit = False
        self.error = ""
        self.hold_until = 0.0
        self.load_program()

    # ---- プログラムの読み書き ----
    def _read_saved(self):
        for path in (CURRENT_FILE, DEFAULT_FILE):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("workspace"), validate_program(data.get("program"))
            except (OSError, ValueError):
                continue
        return None, validate_program(DEFAULT_PROGRAM)

    def load_program(self):
        workspace, program = self._read_saved()
        self.runner.stop()
        self.ctrl.set_program(program)
        return {"workspace": workspace, "program": program}

    def save_program(self, workspace, raw_program):
        program = validate_program(raw_program)
        self.runner.stop()
        self.ctrl.set_program(program)
        os.makedirs(os.path.dirname(CURRENT_FILE), exist_ok=True)
        with open(CURRENT_FILE, "w", encoding="utf-8") as f:
            json.dump({"workspace": workspace, "program": program}, f, ensure_ascii=False)
        return program

    def reset_program(self):
        try:
            os.remove(CURRENT_FILE)
        except OSError:
            pass
        return self.load_program()

    # ---- 操作 ----
    def emergency_stop(self):
        """どのプログラムよりも優先して止めて着陸する。"""
        self.runner.stop(join=False)
        self.tello.send("rc 0 0 0 0")
        self.tello.send("land")
        self.ctrl.flying = False
        self.runner.stop()

    def status(self):
        t = self.tello
        return {
            "connected": t.dry_run or t.got_ok.is_set(),
            "dry_run": t.dry_run,
            "microbit": self.microbit,
            "flying": self.ctrl.flying,
            "battery": t.battery,
            "busy": self.runner.busy,
            "current_id": self.runner.current_id,
            "message": self.error or self.runner.message,
            "input": self.input,
            "active": sorted(self.ctrl.active),
        }

    # ---- 制御ループ ----
    def handle_values(self, vals):
        self.input = vals
        for cmd in self.ctrl.update(*vals):
            if cmd == "land" or cmd == "takeoff":
                self.runner.stop()
            self.tello.send(cmd)
            if cmd == "takeoff":
                self.hold_until = time.monotonic() + TAKEOFF_HOLD
        for script in self.ctrl.take_pending():
            self.runner.start(script)

    def run_loop(self, ser):
        last_rc = None
        next_rc = 0.0
        next_battery = time.monotonic() + 1.0
        buf = b""
        while True:
            if ser:
                buf += ser.read(256)
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    vals = parse_line(raw.decode("ascii", errors="ignore"))
                    if vals is not None:
                        self.handle_values(vals)
            else:
                time.sleep(0.05)
                self.handle_values(list(self.virtual))

            now = time.monotonic()
            if (self.ctrl.flying and not self.runner.busy
                    and now >= self.hold_until and now >= next_rc):
                rc = self.ctrl.rc()
                self.tello.send(rc, quiet=(rc == last_rc))
                last_rc = rc
                next_rc = now + RC_INTERVAL
            if now >= next_battery and not self.runner.busy:
                self.tello.send("battery?", quiet=True)
                next_battery = now + BATTERY_INTERVAL


def make_handler(app, http_port):
    allowed_hosts = {"127.0.0.1:%d" % http_port, "localhost:%d" % http_port}

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self):
            # DNS リバインディング対策: 自分宛ての Host だけ受け付ける
            if self.headers.get("Host") not in allowed_hosts:
                self._json({"error": "bad host"}, 403)
                return False
            return True

        def do_GET(self):
            if not self._host_ok():
                return
            if self.path == "/api/status":
                return self._json(app.status())
            if self.path == "/api/program":
                workspace, program = app._read_saved()
                return self._json({"workspace": workspace, "program": program})
            if self.path.startswith("/api/"):
                return self._json({"error": "not found"}, 404)
            super().do_GET()

        def do_POST(self):
            if not self._host_ok():
                return
            # 他サイトからの勝手な POST を防ぐ (JSON は事前確認が要るので横断リクエストは通らない)
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._json({"error": "json only"}, 415)
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    return self._json({"error": "too large"}, 413)
                data = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, OSError):
                return self._json({"error": "bad json"}, 400)

            if self.path == "/api/program":
                try:
                    program = app.save_program(data.get("workspace"), data.get("program"))
                except ValueError as e:
                    return self._json({"error": str(e)}, 400)
                app.error = ""
                return self._json({"ok": True, "program": program})
            if self.path == "/api/default":
                app.error = ""
                return self._json(app.reset_program())
            if self.path == "/api/stop":
                app.emergency_stop()
                return self._json({"ok": True})
            if self.path == "/api/input":
                try:
                    vals = [int(data[k]) for k in ("p1", "p2", "red", "green", "blue")]
                except (KeyError, TypeError, ValueError):
                    return self._json({"error": "bad input"}, 400)
                if not app.microbit:
                    app.virtual = [max(0, min(1023, vals[0])), max(0, min(1023, vals[1])),
                                   int(bool(vals[2])), int(bool(vals[3])), int(bool(vals[4]))]
                return self._json({"ok": True})
            self._json({"error": "not found"}, 404)

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="micro:bit の COM ポート (省略時は自動検出)")
    ap.add_argument("--dry-run", action="store_true", help="Tello に送らず表示だけ")
    ap.add_argument("--no-microbit", action="store_true", help="ハンドル無し (画面の仮想ボタンで操作)")
    ap.add_argument("--http-port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")
    args = ap.parse_args(argv)

    ser = None
    if not args.no_microbit:
        import serial
        port = args.port or find_microbit_port()
        if not port:
            sys.exit("micro:bit が見つかりません。USB でつなぐか、--no-microbit で画面だけ使ってください。")
        print("micro:bit:", port)
        ser = serial.Serial(port, 115200, timeout=0.02)

    tello = Tello(args.dry_run)
    app = App(tello)
    app.microbit = ser is not None
    handler = partial(make_handler(app, args.http_port), directory=WEB_DIR)
    server = ThreadingHTTPServer(("127.0.0.1", args.http_port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/" % args.http_port
    print("ブロック画面:", url)
    if not args.no_browser:
        webbrowser.open(url)

    try:
        tello.wait_connected()
        tello.send("command")
        tello.send("battery?")
        if ser:
            ser.reset_input_buffer()
        app.run_loop(ser)
    except KeyboardInterrupt:
        print("\n終了します")
    finally:
        app.runner.stop()
        if app.ctrl.flying:
            tello.send("rc 0 0 0 0")
            tello.send("land")
            time.sleep(0.5)
        server.shutdown()
        if ser:
            ser.close()
        tello.close()


if __name__ == "__main__":
    main()
