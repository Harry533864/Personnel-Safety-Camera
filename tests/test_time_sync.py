import unittest
import importlib.util
from pathlib import Path


TIME_SYNC_PATH = Path(__file__).resolve().parents[1] / "app" / "time_sync.py"
spec = importlib.util.spec_from_file_location("time_sync_under_test", TIME_SYNC_PATH)
time_sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(time_sync)


class TimeSyncTests(unittest.TestCase):
    def test_client_timezone_formats_filename(self):
        state = time_sync.sync_from_client({
            "client_epoch_ms": 1782288000000,
            "timezone_offset_min": -480,
            "timezone": "Asia/Shanghai",
        })

        self.assertTrue(state["synced"])
        self.assertEqual(time_sync.filename_timestamp(1782288000), "20260624_160000")
        self.assertEqual(time_sync.format_local(1782288000), "2026-06-24T16:00:00")

    def test_rejects_missing_time(self):
        with self.assertRaises(ValueError):
            time_sync.sync_from_client({})


if __name__ == "__main__":
    unittest.main()
