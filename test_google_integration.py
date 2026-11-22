import csv
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
import unittest

from google_health import HealthMCP, load_window
from health_window import report


class GoogleIntegrationTests(unittest.TestCase):
    def test_paginated_http_import_matches_example_csv(self):
        endpoints = {'steps': [], 'active-zone-minutes': [], 'daily-resting-heart-rate': [], 'sleep': []}
        with Path(__file__).with_name('examples').joinpath('synthetic.csv').open() as source:
            for row in csv.DictReader(source):
                day = date.fromisoformat(row['date'])
                civil = {'date': dict(year=day.year, month=day.month, day=day.day)}
                endpoints['steps'].append({'civilStartTime': civil, 'steps': {'countSum': row['steps']}})
                endpoints['active-zone-minutes'].append({'civilStartTime': civil, 'activeZoneMinutes': {
                    'sumInCardioHeartZone': '10', 'sumInFatBurnHeartZone': str(int(row['active_zone_minutes']) - 10)}})
                endpoints['daily-resting-heart-rate'].append({'dailyRestingHeartRate': {
                    'date': civil['date'], 'beatsPerMinute': row['resting_heart_rate_bpm']}})
                endpoints['sleep'].append({'sleep': {'metadata': {'mainSleep': True},
                    'interval': {'endTime': f'{day}T09:00:00Z', 'endUtcOffset': '0s'},
                    'summary': {'minutesAsleep': str(int(row['sleep_hours']) * 60)}}})
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                method = req['method']
                if method != 'initialize' and self.headers.get('Mcp-Session-Id') != 'synthetic-session':
                    self.send_error(400)
                    return
                if method == 'notifications/initialized':
                    self.send_response(202)
                    self.end_headers()
                    return
                if method == 'initialize':
                    result = {'protocolVersion': '2025-06-18'}
                else:
                    name, args = req['params']['name'], req['params']['arguments']
                    calls.append((name, args))
                    slug = args.get('data_type')
                    if name == 'google_health_get_settings':
                        data = {'timeZone': 'UTC'}
                    else:
                        collection = 'rollupDataPoints' if name.endswith('rollup') else 'dataPoints'
                        rows = endpoints[slug]
                        data = {collection: rows[:17], 'nextPageToken': 'next'} if 'page_token' not in args else {collection: rows[17:]}
                    result = {'structuredContent': {'data': data}}
                body = json.dumps({'jsonrpc': '2.0', 'id': req['id'], 'result': result}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                if method == 'initialize':
                    self.send_header('Mcp-Session-Id', 'synthetic-session')
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                client = HealthMCP(f'http://127.0.0.1:{server.server_port}/mcp', allow_loopback_http=True)
                result = report(load_window(client, date(2025, 2, 5)), 40)
            finally:
                server.shutdown()
                thread.join()
        self.assertEqual(result['features'], {'rhr': 65, 'steps': 8500, 'sleep_hours': 7, 'weekly_azm': 180})
        self.assertAlmostEqual(result['coachable_health_age']['health_age'], 39.0131609784)
        self.assertEqual(calls[0][0], 'google_health_get_settings')
        self.assertCountEqual([(name, args['data_type']) for name, args in calls[1:]], [
            ('google_health_reconcile_data_points', 'daily-resting-heart-rate'),
            ('google_health_reconcile_data_points', 'sleep'),
            ('google_health_daily_rollup', 'steps'),
            ('google_health_daily_rollup', 'active-zone-minutes'),
        ] * 2)
        self.assertTrue(all(args['privacy_mode'] == 'structured' for _, args in calls))
        self.assertEqual(sum(args.get('page_token') == 'next' for _, args in calls), 4)
        self.assertEqual(next(args['filter'] for _, args in calls if args.get('data_type') == 'sleep'),
                         'sleep.interval.civil_end_time >= "2024-11-07" AND sleep.interval.civil_end_time < "2025-02-05"')
