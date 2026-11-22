"""Read-only use of an already authorized Google Health MCP endpoint."""
import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
from math import isfinite
from urllib.parse import urlsplit
import urllib.request
from zoneinfo import ZoneInfo

from health_window import aggregate, report


def validate_endpoint(url, allow_loopback_http=False):
    endpoint = urlsplit(url)
    if not endpoint.hostname or endpoint.username is not None or endpoint.password is not None:
        raise ValueError('Use a valid MCP URL without embedded credentials')
    if endpoint.scheme == 'https':
        return
    if endpoint.scheme != 'http' or not allow_loopback_http or endpoint.hostname not in ('127.0.0.1', '::1'):
        raise ValueError('Use HTTPS, or explicitly allow HTTP to a loopback IP')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HealthMCP:
    def __init__(self, url, *, allow_loopback_http=False):
        validate_endpoint(url, allow_loopback_http)
        self.url = url
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.headers = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'}
        self.id = 0
        init = self.rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                      'clientInfo': {'name': 'coachable-health-age', 'version': '0.1'}})
        self.headers['MCP-Protocol-Version'] = init['protocolVersion']
        self.rpc('notifications/initialized', {}, notification=True)

    def rpc(self, method, params, notification=False):
        self.id += 1
        payload = {'jsonrpc': '2.0', 'method': method, 'params': params}
        if not notification:
            payload['id'] = self.id
        req = urllib.request.Request(self.url, json.dumps(payload).encode(), self.headers)
        with self.opener.open(req, timeout=45) as response:
            if session := response.headers.get('Mcp-Session-Id'):
                self.headers['Mcp-Session-Id'] = session
            if notification:
                return None
            if response.headers.get_content_type() == 'text/event-stream':
                for line in response:
                    if line.startswith(b'data:'):
                        doc = json.loads(line[5:])
                        if doc.get('id') == self.id:
                            break
                else:
                    raise ValueError('No response for MCP request')
            else:
                doc = json.load(response)
        if 'error' in doc:
            raise ValueError(f'MCP RPC failed: {method}, code {doc["error"].get("code")}')
        return doc['result']

    def read(self, verb, **args):
        result = self.rpc('tools/call', {'name': 'google_health_' + verb, 'arguments': {
            'privacy_mode': 'structured', 'response_format': 'json', **args}})
        try:
            doc = json.loads(result['content'][0]['text'])
        except (KeyError, IndexError, json.JSONDecodeError):
            doc = {}
        if result.get('isError') or 'data' not in doc:
            raise ValueError(f'Google Health read failed: {verb} ({args.get("data_type", "settings")})')
        return doc['data']

    def pages(self, verb, key, **args):
        seen = set()
        page = self.read(verb, **args)
        while True:
            if key not in page and page.keys() - {'nextPageToken'}:
                raise ValueError(f'Unexpected {verb} response')
            yield from page.get(key, [])
            token = page.get('nextPageToken')
            if not token:
                return
            if token in seen or len(seen) >= 200:
                raise ValueError(f'Pagination did not complete: {verb}')
            seen.add(token)
            page = self.read(verb, page_token=token, **args)


def date_field(obj):
    return date(obj['year'], obj['month'], obj['day'])


def normalized(rows, start, end, low, high):
    out = {}
    conflicts = set()
    for day, raw in rows:
        if not start <= day < end:
            continue
        value = float(raw)
        if not isfinite(value) or not low <= value <= high:
            raise ValueError('Invalid source measurement')
        if day in out and out[day] != value:
            conflicts.add(day)
        out[day] = value
    return {d: v for d, v in out.items() if d not in conflicts}, len(conflicts)


def load_window(client, end=None):
    tz = ZoneInfo(client.read('get_settings')['timeZone'])
    today = datetime.now(tz).date()
    end = end or today
    if end > today:
        raise ValueError('Window must not include unfinished or future days')
    start = end - timedelta(days=90)

    def bounds(field, lower, upper):
        return f'{field} >= "{lower}" AND {field} < "{upper}"'

    def reconcile(slug, field, lower, upper):
        return client.pages('reconcile_data_points', 'dataPoints', data_type=slug,
                            filter=bounds(field, lower, upper), page_size=20)

    def rollup(slug):
        return client.pages('daily_rollup', 'rollupDataPoints', data_type=slug,
                            start_date=str(start), end_date=str(end), page_size=30)

    def midnight_utc(d):
        return datetime.combine(d, time(), tz).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')

    rhr = ((date_field(x['date']), x['beatsPerMinute']) for row in reconcile(
        'daily-resting-heart-rate', 'daily_resting_heart_rate.date', start, end)
        for x in [row['dailyRestingHeartRate']])
    steps = ((date_field(row['civilStartTime']['date']), row['steps']['countSum'])
             for row in rollup('steps') if 'countSum' in row.get('steps', {}))
    zone_keys = ('sumInCardioHeartZone', 'sumInPeakHeartZone', 'sumInFatBurnHeartZone')
    azm = ((date_field(row['civilStartTime']['date']), sum(int(x[k]) for k in zone_keys if k in x))
           for row in rollup('active-zone-minutes') for x in [row.get('activeZoneMinutes', {})]
           if x.keys() & set(zone_keys))
    sleep = ((datetime.fromisoformat(x['interval']['endTime']).astimezone(tz).date(),
              float(x['summary']['minutesAsleep']) / 60) for row in reconcile(
        'sleep', 'sleep.interval.end_time', midnight_utc(start), midnight_utc(end))
        for x in [row['sleep']] if x.get('metadata', {}).get('mainSleep') is True
        and 'minutesAsleep' in x.get('summary', {}))
    pairs = [normalized(rows, start, end, lo, hi) for rows, lo, hi in (
        (rhr, 1, 300), (steps, 0, 150000), (sleep, 0.01, 24), (azm, 0, 2880))]
    coverage = aggregate(start, end, *(p[0] for p in pairs))
    coverage['conflicting_days_dropped'] = dict(zip(coverage['observed_days'], (p[1] for p in pairs)))
    return coverage


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcp-url', required=True, help='URL of your authorized Google Health MCP server')
    parser.add_argument('--allow-loopback-http', action='store_true', help='Allow plaintext to 127.0.0.1 or ::1 only')
    parser.add_argument('--birth-date', type=date.fromisoformat, help='Optional; age used only for scoring')
    parser.add_argument('--end-exclusive', type=date.fromisoformat, help='Exclusive local date, default today')
    args = parser.parse_args()
    try:
        result = load_window(HealthMCP(args.mcp_url, allow_loopback_http=args.allow_loopback_http), args.end_exclusive)
        if args.birth_date:
            last_day = date.fromisoformat(result['end_exclusive']) - timedelta(days=1)
            age = (last_day - args.birth_date).days / 365.2425
            result = report(result, age)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, OSError, KeyError, TypeError, OverflowError) as error:
        parser.exit(1, f'Could not finish the Google Health calculation ({type(error).__name__}): '
                       f'{str(error) if isinstance(error, ValueError) else "check connection and schema"}\n')
