import unittest

from inference.python_tensorrt.runtime import (
    AlarmLogic,
    Detection,
    ROIManager,
    ROIRule,
    SystemState,
)


class RoiAlarmStateTest(unittest.TestCase):
    def setUp(self):
        self.roi = ROIRule(
            roi_id="hazard_1",
            name="ROI1",
            roi_type="forbidden_zone",
            polygon=[(0, 0), (10, 0), (10, 10), (0, 10)],
            judge_method="overlap",
            overlap_thres=0.5,
        )
        self.manager = ROIManager([self.roi])

    def evaluate(self, detection):
        detections = self.manager.apply([detection] if detection else [], (20, 20, 3))
        logic = AlarmLogic([self.roi], enter_frames=1, exit_frames=1)
        return logic.evaluate(detections)

    def test_no_overlap_is_safe(self):
        result = self.evaluate(None)

        self.assertEqual(result.system_state, SystemState.SAFE)
        self.assertFalse(result.warning)
        self.assertFalse(result.alarm)
        self.assertEqual(result.zone_summary[0].person_count, 0)
        self.assertEqual(result.zone_summary[0].warning_count, 0)

    def test_overlap_below_threshold_is_warning_not_alarm(self):
        detection = Detection(
            bbox=(8, 0, 18, 10),
            center=(13, 5),
            foot_point=(13, 10),
        )

        result = self.evaluate(detection)

        self.assertEqual(result.system_state, SystemState.WARNING)
        self.assertTrue(result.warning)
        self.assertFalse(result.alarm)
        self.assertEqual(len(result.detections[0].roi_hits), 0)
        self.assertEqual(len(result.detections[0].roi_contacts), 1)
        self.assertEqual(result.zone_summary[0].person_count, 0)
        self.assertEqual(result.zone_summary[0].warning_count, 1)

    def test_overlap_at_threshold_is_alarm(self):
        detection = Detection(
            bbox=(5, 0, 15, 10),
            center=(10, 5),
            foot_point=(10, 10),
        )

        result = self.evaluate(detection)

        self.assertEqual(result.system_state, SystemState.ALARM)
        self.assertFalse(result.warning)
        self.assertTrue(result.alarm)
        self.assertEqual(len(result.detections[0].roi_hits), 1)
        self.assertEqual(len(result.detections[0].roi_contacts), 0)
        self.assertEqual(result.zone_summary[0].person_count, 1)
        self.assertEqual(result.zone_summary[0].warning_count, 0)


if __name__ == "__main__":
    unittest.main()
