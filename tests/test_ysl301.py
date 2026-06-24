import unittest

from inference.python_tensorrt.ysl301 import build_write_coil_frame


class Ysl301ProtocolTest(unittest.TestCase):
    def test_red_on_frame_matches_sdk(self):
        frame = build_write_coil_frame(1, "red", "on")
        self.assertEqual(frame, bytes.fromhex("01 05 00 00 FF 00 8C 3A"))

    def test_yellow_off_frame_matches_sdk(self):
        frame = build_write_coil_frame(1, "yellow", "off")
        self.assertEqual(frame, bytes.fromhex("01 05 00 01 00 00 9C 0A"))

    def test_buzzer_tweet1hz_frame_matches_sdk(self):
        frame = build_write_coil_frame(1, "buzzer", "tweet1hz")
        self.assertEqual(frame, bytes.fromhex("01 05 00 03 F1 00 78 5A"))


if __name__ == "__main__":
    unittest.main()
