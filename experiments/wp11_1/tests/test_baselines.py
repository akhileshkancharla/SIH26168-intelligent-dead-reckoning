import math
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from baselines import Sample, constant_turn_rate, constant_velocity, hold_last_position, to_local
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

    def test_periodic_mask(self):
        self.assertEqual(periodic_mask(8, 1.0, 2.0, 2.0, 5.0), [False, False, True, True, False, False, False, True])

    def test_summary(self):
        result = summarize([3.0, 4.0])
        self.assertAlmostEqual(result["rmse_m"], math.sqrt(12.5))
        self.assertEqual(result["max_m"], 4.0)


if __name__ == "__main__":
    unittest.main()

