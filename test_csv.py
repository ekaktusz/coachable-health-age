from datetime import date, timedelta
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import unittest

from csv_import import load_csv
from health_window import report


END = date(2025, 2, 5)
HEADER = 'date,resting_heart_rate_bpm,steps,sleep_hours,active_zone_minutes\n'


def daily_rows(missing_azm=False):
    return HEADER + ''.join(
        f'{END - timedelta(days=n)},65,8500,7,{"" if missing_azm and n == 1 else 0}\n'
        for n in range(1, 36)
    )


class CSVTests(unittest.TestCase):
    def test_complete_window_preserves_observed_zero(self):
        result = report(load_csv(StringIO(daily_rows()), END), 40)
        self.assertEqual(result['valid_weeks'], 5)
        self.assertEqual(result['features']['weekly_azm'], 0)
        self.assertIn('coachable_health_age', result)

    def test_blank_azm_produces_only_bounds(self):
        result = report(load_csv(StringIO(daily_rows(True)), END), 40)
        self.assertEqual(result['observed_days']['azm'], 34)
        self.assertEqual(result['complete_azm_weeks'], 4)
        self.assertNotIn('coachable_health_age', result)
        bounds = result['coachable_health_age_bounds']
        self.assertLess(bounds['lower'], bounds['upper'])

    def test_sparse_window_reports_coverage_without_score(self):
        result = report(load_csv(StringIO(HEADER + '2025-02-04,65,8500,,0\n'), END), 40)
        self.assertEqual(result['observed_days']['sleep_hours'], 0)
        self.assertNotIn('coachable_health_age', result)
        self.assertNotIn('coachable_health_age_bounds', result)

    def test_outside_window_rows_are_not_aggregated(self):
        text = HEADER + '2024-01-01,65,8500,7,1\n2025-02-05,65,8500,7,1\n'
        self.assertEqual(load_csv(StringIO(text), END)['observed_days']['steps'], 0)

    def test_rejects_generic_active_minutes_header(self):
        with self.assertRaisesRegex(ValueError, 'active_zone_minutes'):
            load_csv(StringIO(HEADER.replace('active_zone_minutes', 'active_minutes')), END)

    def test_rejects_duplicate_date(self):
        with self.assertRaisesRegex(ValueError, 'Row 3: duplicate date'):
            load_csv(StringIO(HEADER + '2025-02-04,65,8500,7,0\n2025-02-04,65,8500,7,0\n'), END)

    def test_rejects_invalid_rows_without_echoing_values(self):
        for row, field in [('20250204,65,8500,7,0', 'date'),
                           ('2025-02-04,65,8500,7', 'columns'),
                           ('2025-02-04,65,8500,7,0,extra', 'columns'),
                           ('2025-02-04,nan,8500,7,0', 'resting_heart_rate_bpm'),
                           ('2025-02-04,65,8500,25,0', 'sleep_hours'),
                           ('2025-02-04,65,8500,7,-1', 'active_zone_minutes')]:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'Row 2:.*' + field):
                load_csv(StringIO(HEADER + row + '\n'), END)

    def test_readme_example_runs_from_checkout(self):
        root = Path(__file__).resolve().parent
        output = subprocess.check_output(
            [sys.executable, 'csv_import.py', 'examples/synthetic.csv', '--age', '40',
             '--end-exclusive', str(END)], cwd=root, text=True,
        )
        result = json.loads(output)
        self.assertAlmostEqual(result['coachable_health_age']['health_age'], 39.0131609784)
        self.assertEqual(result['features']['weekly_azm'], 180)
