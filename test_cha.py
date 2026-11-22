import math
import unittest

from cha import calculate


class CoreTests(unittest.TestCase):
    def test_reference(self):
        r = calculate(40, 60, 8000, 7, 115)
        self.assertEqual(r['health_age'], 40)
        self.assertEqual(r['delta_years'], 0)

    def test_plateaus_and_paper_weights(self):
        a = calculate(40, 60, 9000, 7, 500)
        b = calculate(40, 55, 12000, 8, 750)
        self.assertEqual(a, b)
        self.assertAlmostEqual(a['delta_years'], 10*(.4773*math.log(.88)+.695*math.log(.68)))

    def test_knots(self):
        r = calculate(40, 90, 8000, 10, 418)
        for key, expected in {'resting_heart_rate': 7.066*math.log(1.33), 'sleep_duration': 8.79*math.log(1.34), 'active_zone_minutes': 6.95*math.log(.71)}.items():
            self.assertAlmostEqual(r['contributions_years'][key], expected)

    def test_piecewise_interpolation(self):
        r = calculate(40, 65, 7000, 5, 180)['contributions_years']
        self.assertAlmostEqual(r['resting_heart_rate'], 7.066*.5*math.log(1.08))
        self.assertAlmostEqual(r['steps'], -4.773*math.log(.88))
        self.assertAlmostEqual(r['sleep_duration'], 8.79*math.log(1.20))
        self.assertAlmostEqual(r['active_zone_minutes'], 6.95*.5*math.log(.76))

    def test_floor_is_separate_from_raw_delta(self):
        self.assertEqual(calculate(19, 60, 9000, 7, 500)['health_age'], 18)

    def test_missing_or_invalid_input_is_not_zero(self):
        for azm in (None, float('nan'), -1, True):
            with self.subTest(azm=azm), self.assertRaises(ValueError):
                calculate(40, 60, 8000, 7, azm)
