import math
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from baselines import Point, Sample, _constant_turn_step, constant_turn_rate, constant_velocity, hold_last_position, to_local
from evaluate import periodic_mask, summarize


class BaselineTests(unittest.TestCase):
    def samples(self):
        return [
            Sample(float(i), 0.0, i / 111_195.0, 1.0, 90.0)
            for i in range(6)
        ]

    def test_hold_uses_last_visible_position(self):
        samples = self.samples()
        prediction = hold_last_position(samples, [False, False, True, True, False, False])
        truth = to_local(samples)
        self.assertEqual(prediction[2], truth[1])
        self.assertEqual(prediction[3], truth[1])

    def test_constant_velocity_tracks_straight_motion(self):
        samples = self.samples()
        prediction = constant_velocity(samples, [False, False, True, True, True, False])
        truth = to_local(samples)
        self.assertLess(abs(prediction[4].east_m - truth[4].east_m), 0.02)

    def test_constant_turn_rate_is_deterministic(self):
        samples = self.samples()
        mask = [False, False, True, True, True, False]
        self.assertEqual(constant_turn_rate(samples, mask), constant_turn_rate(samples, mask))

    def test_constant_turn_rate_integrates_left_arc(self):
        point, heading = _constant_turn_step(Point(0.0, 0.0), 1.0, 90.0, 90.0, 1.0)
        expected = 2.0 / math.pi
        self.assertAlmostEqual(point.east_m, expected)
        self.assertAlmostEqual(point.north_m, -expected)
        self.assertAlmostEqual(heading, 180.0)

    def test_constant_turn_rate_integrates_right_arc(self):
        point, heading = _constant_turn_step(Point(0.0, 0.0), 1.0, 90.0, -90.0, 1.0)
        expected = 2.0 / math.pi
        self.assertAlmostEqual(point.east_m, expected)
        self.assertAlmostEqual(point.north_m, expected)
        self.assertAlmostEqual(heading, 0.0)

    def test_constant_turn_rate_wraps_heading(self):
        point, heading = _constant_turn_step(Point(0.0, 0.0), 1.0, 350.0, 20.0, 1.0)
        radius = 9.0 / math.pi
        self.assertAlmostEqual(point.east_m, 0.0, places=12)
        self.assertAlmostEqual(point.north_m, 2.0 * radius * math.sin(math.radians(10.0)))
        self.assertAlmostEqual(heading, 10.0)

    def test_initial_blackout_requires_visible_anchor(self):
        mask = [True, True, True, False, False, False]
        for baseline in (hold_last_position, constant_velocity, constant_turn_rate):
            with self.subTest(baseline=baseline.__name__):
                with self.assertRaisesRegex(ValueError, "visible initialization"):
                    baseline(self.samples(), mask)

    def test_masked_truth_cannot_initialize_predictions(self):
        mask = [True, True, True, False, False, False]
        perturbed = self.samples()
        perturbed[1] = Sample(1.0, 0.0, 100.0 / 111_195.0, 1.0, 90.0)
        for baseline in (hold_last_position, constant_velocity, constant_turn_rate):
            with self.subTest(baseline=baseline.__name__):
                for samples in (self.samples(), perturbed):
                    with self.assertRaisesRegex(ValueError, "visible initialization"):
                        baseline(samples, mask)

    def test_periodic_mask(self):
        self.assertEqual(periodic_mask(8, 1.0, 2.0, 2.0, 5.0), [False, False, True, True, False, False, False, True])

    def test_summary(self):
        result = summarize([3.0, 4.0])
        self.assertAlmostEqual(result["rmse_m"], math.sqrt(12.5))
        self.assertEqual(result["max_m"], 4.0)


if __name__ == "__main__":
    unittest.main()
