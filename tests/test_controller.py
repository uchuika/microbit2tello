import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tello_microbit import (Controller, parse_line, stick_to_speed,  # noqa: E402
                            MOVE_SPEED, UD_SPEED, YAW_SPEED)

C1, C2 = 514, 527  # 実機で測ったスティックの中心値


class StickTest(unittest.TestCase):
    def test_center_and_deadzone(self):
        self.assertEqual(stick_to_speed(514, 514), 0)
        self.assertEqual(stick_to_speed(514 - 60, 514), 0)   # 約12% -> 不感帯
        self.assertEqual(stick_to_speed(514 + 60, 514), 0)

    def test_full_scale(self):
        self.assertEqual(stick_to_speed(0, 514), MOVE_SPEED)      # 前 / 右
        self.assertEqual(stick_to_speed(1023, 514), -MOVE_SPEED)  # 後 / 左

    def test_proportional(self):
        half = stick_to_speed(514 // 2, 514)
        self.assertTrue(0 < half < MOVE_SPEED)


class ControllerTest(unittest.TestCase):
    def setUp(self):
        self.c = Controller()
        self.c.update(C1, C2, 0, 0, 0)  # 起動時 (中心を記録)

    def test_not_flying_no_rc(self):
        self.assertIsNone(self.c.rc())

    def test_red_edge_toggles_takeoff_land(self):
        self.assertEqual(self.c.update(C1, C2, 1, 0, 0), ["takeoff"])
        self.assertEqual(self.c.update(C1, C2, 1, 0, 0), [])  # 押しっぱなし
        self.assertEqual(self.c.update(C1, C2, 0, 0, 0), [])  # 離した
        self.assertEqual(self.c.update(C1, C2, 1, 0, 0), ["rc 0 0 0 0", "land"])
        self.assertFalse(self.c.flying)

    def test_green_blue_hold(self):
        self.c.update(C1, C2, 1, 0, 0)
        self.c.update(C1, C2, 0, 1, 0)
        self.assertEqual(self.c.rc(), "rc 0 0 {} 0".format(UD_SPEED))
        self.c.update(C1, C2, 0, 0, 0)
        self.assertEqual(self.c.rc(), "rc 0 0 0 0")
        self.c.update(C1, C2, 0, 0, 1)
        self.assertEqual(self.c.rc(), "rc 0 0 {} 0".format(-UD_SPEED))
        self.c.update(C1, C2, 0, 1, 1)
        self.assertEqual(self.c.rc(), "rc 0 0 0 0")

    def test_stick_directions(self):
        self.c.update(C1, C2, 1, 0, 0)
        self.c.update(0, C2, 0, 0, 0)       # 前に倒す (P1 が小さくなる)
        self.assertEqual(self.c.rc(), "rc 0 {} 0 0".format(MOVE_SPEED))
        self.c.update(C1, 0, 0, 0, 0)       # 右に倒す (P2 が小さくなる)
        self.assertEqual(self.c.rc(), "rc {} 0 0 0".format(MOVE_SPEED))
        self.c.update(1023, 1023, 0, 0, 0)  # 後ろ左
        self.assertEqual(self.c.rc(), "rc {0} {0} 0 0".format(-MOVE_SPEED))

    def test_yellow_turns_instead_of_sliding(self):
        self.c.update(C1, C2, 1, 0, 0)
        self.c.update(C1, 0, 0, 0, 0, 1)        # 黄 + 右に倒す
        self.assertEqual(self.c.rc(), "rc 0 0 0 {}".format(YAW_SPEED))
        self.c.update(C1, 1023, 0, 0, 0, 1)     # 黄 + 左に倒す
        self.assertEqual(self.c.rc(), "rc 0 0 0 {}".format(-YAW_SPEED))

    def test_yellow_keeps_forward_and_updown(self):
        self.c.update(C1, C2, 1, 0, 0)
        self.c.update(0, 0, 0, 1, 0, 1)         # 黄 + 前 + 右 + 緑
        self.assertEqual(self.c.rc(), "rc 0 {} {} {}".format(MOVE_SPEED, UD_SPEED, YAW_SPEED))

    def test_release_yellow_returns_to_sliding(self):
        self.c.update(C1, C2, 1, 0, 0)
        self.c.update(C1, 0, 0, 0, 0, 1)
        self.c.update(C1, 0, 0, 0, 0, 0)
        self.assertEqual(self.c.rc(), "rc {} 0 0 0".format(MOVE_SPEED))

    def test_yellow_deadzone(self):
        self.c.update(C1, C2, 1, 0, 0)
        self.c.update(C1, C2, 0, 0, 0, 1)
        self.assertEqual(self.c.rc(), "rc 0 0 0 0")

    def test_calibration_ignores_tilted_start(self):
        c = Controller()
        c.update(0, 1023, 0, 0, 0)  # 倒したまま起動
        self.assertEqual((c.center_fb, c.center_lr), (512, 512))

    def test_parse_line(self):
        self.assertEqual(parse_line("514,527,1,0,0,1\r\n"), [514, 527, 1, 0, 0, 1])
        self.assertEqual(parse_line("514,527,1,0,0\r\n"), [514, 527, 1, 0, 0])  # 旧形式 (5 値) も可
        self.assertIsNone(parse_line("garbage"))
        self.assertIsNone(parse_line("1,2,3"))
        self.assertIsNone(parse_line("1,2,3,4,5,6,7"))


if __name__ == "__main__":
    unittest.main()
