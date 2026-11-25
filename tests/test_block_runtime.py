import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from block_runtime import (BlockController, DEFAULT_PROGRAM, ScriptRunner,  # noqa: E402
                           validate_program)

C1, C2 = 514, 527


class FakeTello:
    def __init__(self, responses=None, delay=0.0):
        self.sent = []
        self.responses = responses or {}
        self.delay = delay

    def send(self, cmd, quiet=False):
        self.sent.append(cmd)

    def send_and_wait(self, cmd, timeout=10.0):
        self.sent.append(cmd)
        if self.delay:
            time.sleep(self.delay)
        return self.responses.get(cmd.split()[0], "ok")


def prog(*events):
    return validate_program({"events": list(events)})


class ValidateTest(unittest.TestCase):
    def test_default_program_valid(self):
        validate_program(DEFAULT_PROGRAM)

    def test_values_are_clamped(self):
        p = prog({"kind": "press", "input": "green", "script": [
            {"op": "move", "dir": "forward", "cm": 9999},
            {"op": "move", "dir": "up", "cm": 1},
            {"op": "turn", "dir": "right", "deg": 720},
            {"op": "wait", "sec": 99},
        ]})
        s = p["events"][0]["script"]
        self.assertEqual([s[0]["cm"], s[1]["cm"], s[2]["deg"], s[3]["sec"]], [500, 20, 360, 10.0])

    def test_rejects_unknown(self):
        for bad in [
            {"events": [{"kind": "press", "input": "red", "script": []}]},   # 赤は使えない
            {"events": [{"kind": "press", "input": "green", "script": [{"op": "rm -rf"}]}]},
            {"events": [{"kind": "press", "input": "green", "script": [{"op": "move", "dir": "x", "cm": 50}]}]},
            {"events": [{"kind": "hold", "input": "blue", "moves": [{"op": "move", "dir": "up", "cm": 50}]}]},
            {"events": "x"},
        ]:
            with self.assertRaises(ValueError):
                validate_program(bad)

    def test_nesting_and_size_limits(self):
        body = [{"op": "takeoff"}]
        for _ in range(5):
            body = [{"op": "repeat", "times": 2, "body": body}]
        with self.assertRaises(ValueError):
            prog({"kind": "press", "input": "green", "script": body})
        with self.assertRaises(ValueError):
            prog({"kind": "press", "input": "green", "script": [{"op": "takeoff"}] * 400})


class ControllerTest(unittest.TestCase):
    def make(self, *events):
        c = BlockController(prog(*events) if events else None)
        c.update(C1, C2, 0, 0, 0)
        return c

    def test_red_is_fixed_takeoff_land(self):
        c = self.make({"kind": "press", "input": "green", "script": []})
        self.assertEqual(c.update(C1, C2, 1, 0, 0), ["takeoff"])
        self.assertEqual(c.update(C1, C2, 1, 0, 0), [])
        c.update(C1, C2, 0, 0, 0)
        self.assertEqual(c.update(C1, C2, 1, 0, 0), ["rc 0 0 0 0", "land"])

    def test_default_program_matches_old_controller(self):
        c = self.make()
        self.assertIsNone(c.rc())
        c.update(C1, C2, 1, 0, 0)
        c.update(C1, C2, 0, 1, 0)
        self.assertEqual(c.rc(), "rc 0 0 40 0")
        c.update(C1, C2, 0, 0, 1)
        self.assertEqual(c.rc(), "rc 0 0 -40 0")
        c.update(C1, C2, 0, 1, 1)
        self.assertEqual(c.rc(), "rc 0 0 0 0")
        c.update(0, C2, 0, 0, 0)
        self.assertEqual(c.rc(), "rc 0 60 0 0")

    def test_hold_custom_and_clamp(self):
        c = self.make(
            {"kind": "hold", "input": "green", "moves": [
                {"op": "drive", "dir": "forward", "speed": 80},
                {"op": "spin", "dir": "left", "speed": 50}]},
            {"kind": "hold", "input": "green", "moves": [{"op": "drive", "dir": "forward", "speed": 80}]},
        )
        c.update(C1, C2, 1, 0, 0)
        c.update(C1, C2, 0, 1, 0)
        self.assertEqual(c.rc(), "rc 0 100 0 -50")

    def test_press_fires_once_per_edge(self):
        script = [{"op": "takeoff"}]
        c = self.make({"kind": "press", "input": "green", "script": script})
        c.update(C1, C2, 0, 1, 0)
        c.update(C1, C2, 0, 1, 0)
        self.assertEqual(len(c.take_pending()), 1)
        c.update(C1, C2, 0, 0, 0)
        c.update(C1, C2, 0, 1, 0)
        self.assertEqual(len(c.take_pending()), 1)

    def test_stick_press(self):
        c = self.make({"kind": "press", "input": "stick_fwd", "script": [{"op": "land"}]})
        c.update(C1 // 2 + 30, C2, 0, 0, 0)  # 少し倒す程度では反応しない
        self.assertEqual(c.take_pending(), [])
        c.update(0, C2, 0, 0, 0)
        self.assertEqual(len(c.take_pending()), 1)


class RunnerTest(unittest.TestCase):
    def run_script(self, script, flying, tello=None):
        tello = tello or FakeTello()
        c = BlockController()
        c.flying = flying
        r = ScriptRunner(tello, c)
        r.start(validate_program({"events": [{"kind": "press", "input": "green", "script": script}]})
                ["events"][0]["script"])
        r._thread.join(5)
        return tello, c, r

    def test_sequence_and_repeat(self):
        tello, c, r = self.run_script([
            {"op": "takeoff"},
            {"op": "repeat", "times": 2, "body": [
                {"op": "move", "dir": "forward", "cm": 50},
                {"op": "turn", "dir": "right", "deg": 90}]},
            {"op": "flip", "dir": "back"},
            {"op": "land"},
        ], flying=False)
        self.assertEqual(tello.sent, [
            "takeoff", "forward 50", "cw 90", "forward 50", "cw 90", "flip b", "rc 0 0 0 0", "land"])
        self.assertFalse(c.flying)

    def test_move_on_ground_is_skipped(self):
        tello, c, r = self.run_script([{"op": "move", "dir": "up", "cm": 50}], flying=False)
        self.assertEqual(tello.sent, [])
        self.assertIn("離陸", r.message)

    def test_error_aborts(self):
        tello, c, r = self.run_script(
            [{"op": "move", "dir": "up", "cm": 50}, {"op": "move", "dir": "down", "cm": 50}],
            flying=True, tello=FakeTello({"up": "error"}))
        self.assertEqual(tello.sent, ["up 50"])
        self.assertIn("error", r.message)

    def test_timeout_aborts(self):
        tello, c, r = self.run_script(
            [{"op": "move", "dir": "up", "cm": 50}, {"op": "move", "dir": "down", "cm": 50}],
            flying=True, tello=FakeTello({"up": None}))
        self.assertEqual(tello.sent, ["up 50"])
        self.assertTrue(r.message)

    def test_stop_interrupts_wait(self):
        tello = FakeTello()
        c = BlockController()
        c.flying = True
        r = ScriptRunner(tello, c)
        r.start([{"op": "wait", "sec": 10}, {"op": "move", "dir": "up", "cm": 50}])
        time.sleep(0.2)
        self.assertTrue(r.busy)
        t0 = time.monotonic()
        r.stop()
        self.assertLess(time.monotonic() - t0, 1.5)
        self.assertFalse(r.busy)
        self.assertNotIn("up 50", tello.sent)

    def test_busy_ignores_second_start(self):
        tello = FakeTello(delay=0.3)
        r = ScriptRunner(tello, BlockController())
        self.assertTrue(r.start([{"op": "takeoff"}]))
        self.assertFalse(r.start([{"op": "land"}]))
        r.stop()


if __name__ == "__main__":
    unittest.main()
