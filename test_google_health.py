from datetime import date
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from google_health import HealthMCP, azm_total, load_window, normalized, wake_date


class GoogleDataTests(unittest.TestCase):
    def test_structured_only_and_legacy_text_results(self):
        for payload in ({'structuredContent': {'data': {}}},
                        {'content': [{'type': 'text', 'text': '{"data": {}}'}]}):
            with patch.object(HealthMCP, 'rpc', return_value=payload), self.subTest(payload=payload):
                self.assertEqual(HealthMCP.__new__(HealthMCP).read('get_settings'), {})
        with patch.object(HealthMCP, 'rpc', return_value={'content': [{'text': 'null'}]}):
            with self.assertRaisesRegex(ValueError, 'Invalid Google Health response'):
                HealthMCP.__new__(HealthMCP).read('get_settings')

    def test_pages_allow_empty_page_with_string_token(self):
        with patch.object(HealthMCP, 'read', side_effect=[{'nextPageToken': 'more'}, {'dataPoints': [{}]}]) as read:
            self.assertEqual(list(HealthMCP.__new__(HealthMCP).pages('test', 'dataPoints')), [{}])
            self.assertEqual(read.call_args.kwargs['page_token'], 'more')

    def test_pages_reject_malformed_collections_and_tokens(self):
        for response in ({'dataPoints': {}}, {'dataPoints': [False]}, {'nextPageToken': False}):
            with self.subTest(response=response), patch.object(HealthMCP, 'read', return_value=response):
                with self.assertRaisesRegex(ValueError, 'Unexpected'):
                    list(HealthMCP.__new__(HealthMCP).pages('test', 'dataPoints'))

    def test_measurements_reject_bool_and_invalid_azm_components(self):
        with self.assertRaisesRegex(ValueError, 'Invalid source measurement'):
            normalized([(date(2025, 1, 1), False)], date(2025, 1, 1), date(2025, 2, 1), 0, 100)
        for value in (-1, 2.5, True):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Active Zone Minutes'):
                azm_total({'sumInPeakHeartZone': value, 'sumInFatBurnHeartZone': '15'})
        self.assertEqual(azm_total({'sumInPeakHeartZone': '0'}), 0)
        self.assertIsNone(azm_total({}))

    def test_wake_date_prefers_observation_local_date(self):
        interval = {'endTime': '2025-02-04T23:50:00Z', 'endUtcOffset': '3600s'}
        self.assertEqual(wake_date(interval, ZoneInfo('UTC')), date(2025, 2, 5))
        interval['civilEndTime'] = {'date': {'year': 2025, 'month': 2, 'day': 6}}
        self.assertEqual(wake_date(interval, ZoneInfo('UTC')), date(2025, 2, 6))

    def test_clear_error_for_missing_timezone(self):
        with patch.object(HealthMCP, 'read', return_value={}):
            with self.assertRaisesRegex(ValueError, 'time zone'):
                load_window(HealthMCP.__new__(HealthMCP))
