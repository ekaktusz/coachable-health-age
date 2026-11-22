from datetime import date, timedelta
import unittest
from health_window import aggregate, report


class WindowTests(unittest.TestCase):
    def test_mixed_azm_weeks_do_not_produce_a_point_estimate(self):
        end = date(2026, 4, 1)
        start = end - timedelta(days=90)
        days = [end - timedelta(days=n) for n in range(1, 85)]
        series = [{d: x for d in days} for x in (70, 8000, 7, 20)]
        del series[3][days[0]]
        result = report(aggregate(start, end, *series), 40)
        self.assertEqual(result['complete_azm_weeks'], 11)
        self.assertNotIn('coachable_health_age', result)
        self.assertIn('coachable_health_age_bounds', result)

    def test_missing_azm_days_are_not_zero(self):
        start = date(2026, 1, 1)
        end = start + timedelta(days=90)
        days = [end - timedelta(days=n) for n in range(1, 85)]
        series = [{d: x for d in days} for x in (70, 8000, 7, 20)]
        for d in days[::7]:
            del series[3][d]
        result = aggregate(start, end, *series)
        self.assertIsNone(result['features'])
        self.assertEqual(result['complete_azm_weeks'], 0)
        score = report(result, 40)['coachable_health_age_bounds']
        self.assertLess(score['lower'], score['upper'])
        self.assertLess(score['upper'], 41)

    def test_full_weeks_and_observed_zero(self):
        end = date(2026, 4, 1)
        start = end - timedelta(days=90)
        days = [end - timedelta(days=n) for n in range(1, 85)]
        series = [{d: x for d in days} for x in (70, 8000, 7, 0)]
        result = aggregate(start, end, *series)
        self.assertEqual(result['complete_azm_weeks'], 12)
        self.assertEqual(result['features']['weekly_azm'], 0)
        self.assertEqual(result['features']['steps'], 8000)
