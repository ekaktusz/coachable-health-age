"""Read-only use of an already authorized Google Health MCP endpoint."""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from math import isfinite
from urllib.parse import urlsplit
import urllib.request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from health_window import DAILY_AZM_MAX, aggregate, report

MCP_VERSIONS = {'2025-03-26', '2025-06-18', '2025-11-25'}


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


def sse_messages(response):
    data = []
    for raw_line in response:
        line = raw_line.rstrip(b'\r\n')
        if not line:
            if data:
                yield json.loads(b'\n'.join(data))
                data.clear()
        else:
            field, separator, value = line.partition(b':')
            if field == b'data':
                data.append(value.removeprefix(b' ') if separator else b'')


class HealthMCP:
    def __init__(self, url, *, allow_loopback_http=False):
        validate_endpoint(url, allow_loopback_http)
        self.url = url
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.headers = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'}
        self.id = 0
        init = self.rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                      'clientInfo': {'name': 'coachable-health-age', 'version': '0.1'}})
        version = init.get('protocolVersion')
        if not isinstance(version, str) or version not in MCP_VERSIONS:
            raise ValueError('Unsupported MCP protocol version')
        self.headers['MCP-Protocol-Version'] = version
        self.rpc('notifications/initialized', {}, notification=True)

    def rpc(self, method, params, notification=False):
        self.id += 1
        payload = {'jsonrpc': '2.0', 'method': method, 'params': params}
        if not notification:
            payload['id'] = self.id
        req = urllib.request.Request(self.url, json.dumps(payload).encode(), self.headers)
        with self.opener.open(req, timeout=45) as response:
            if notification:
                return None
            content_type = response.headers.get_content_type()
            if content_type == 'text/event-stream':
                messages = sse_messages(response)
            elif content_type == 'application/json':
                messages = (json.load(response),)
            else:
                raise ValueError('Expected JSON or an event stream from the MCP endpoint')
            for doc in messages:
                if not isinstance(doc, dict) or doc.get('id') != payload['id'] or doc.get('jsonrpc') != '2.0':
                    continue
                if 'error' in doc:
                    raise ValueError(f'MCP RPC failed: {method}')
                if not isinstance(doc.get('result'), dict):
                    raise ValueError(f'Invalid MCP result: {method}')
                if method == 'initialize' and (session := response.headers.get('Mcp-Session-Id')):
                    self.headers['Mcp-Session-Id'] = session
                return doc['result']
            raise ValueError(f'No matching MCP response: {method}')

    def read(self, verb, **args):
        result = self.rpc('tools/call', {'name': 'google_health_' + verb, 'arguments': {
            'privacy_mode': 'structured', 'response_format': 'json', **args}})
        target = f'{verb} ({args.get("data_type", "settings")})'
        if result.get('isError'):
            raise ValueError(f'Google Health read failed: {target}; check connector authorization and read scopes')
        if 'structuredContent' in result:
            doc = result['structuredContent']
        else:
            try:
                doc = json.loads(result['content'][0]['text'])
            except (KeyError, IndexError, TypeError, json.JSONDecodeError):
                doc = None
        if not isinstance(doc, dict) or not isinstance(doc.get('data'), dict):
            raise ValueError(f'Invalid Google Health response: {target}')
        return doc['data']

    def pages(self, verb, key, **args):
        seen = set()
        page = self.read(verb, **args)
        while True:
            if key not in page and page.keys() - {'nextPageToken'}:
                raise ValueError(f'Unexpected {verb} response')
            rows = page.get(key, [])
            token = page.get('nextPageToken', '')
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows) or not isinstance(token, str):
                raise ValueError(f'Unexpected {verb} response')
            yield from rows
            if not token:
                return
            if token in seen or len(seen) >= 200:
                raise ValueError(f'Pagination did not complete: {verb}')
            seen.add(token)
            page = self.read(verb, page_token=token, **args)


def date_field(obj):
    return date(obj['year'], obj['month'], obj['day'])


def number(raw, label, *, integer=False):
    try:
        if type(raw) not in (int, float, str):
            raise ValueError
        value = float(raw)
        if not isfinite(value) or (integer and not value.is_integer()):
            raise ValueError
    except (ValueError, OverflowError):
        raise ValueError(f'Invalid {label}') from None
    return value


def azm_total(zones):
    if not isinstance(zones, dict):
        raise ValueError('Invalid Active Zone Minutes')
    keys = ('sumInCardioHeartZone', 'sumInPeakHeartZone', 'sumInFatBurnHeartZone')
    values = [number(zones[k], 'Active Zone Minutes', integer=True) for k in keys if k in zones]
    if not values:
        return None
    if any(v < 0 for v in values):
        raise ValueError('Invalid Active Zone Minutes')
    return sum(values)


def wake_date(interval, account_tz):
    if 'civilEndTime' in interval:
        return date_field(interval['civilEndTime']['date'])
    end = datetime.fromisoformat(interval['endTime'])
    if end.tzinfo is None:
        raise ValueError('Sleep end time has no UTC offset')
    if 'endUtcOffset' in interval:
        offset = interval['endUtcOffset']
        if not isinstance(offset, str) or not offset.endswith('s'):
            raise ValueError('Invalid sleep wake UTC offset')
        local = timezone(timedelta(seconds=number(offset[:-1], 'sleep wake UTC offset')))
    else:
        local = account_tz
    return end.astimezone(local).date()


def normalized(rows, start, end, low, high):
    out = {}
    conflicts = set()
    for day, raw in rows:
        if not start <= day < end:
            continue
        value = number(raw, 'source measurement')
        if not low <= value <= high:
            raise ValueError('Invalid source measurement')
        if day in out and out[day] != value:
            conflicts.add(day)
        out[day] = value
    return {d: v for d, v in out.items() if d not in conflicts}, len(conflicts)


def load_window(client, end=None):
    name = client.read('get_settings').get('timeZone')
    if not isinstance(name, str) or not name:
        raise ValueError('Google Health settings did not provide a time zone')
    try:
        tz = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('Google Health time zone unavailable; check settings or install Python tzdata') from None
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


    rhr = ((date_field(x['date']), x['beatsPerMinute']) for row in reconcile(
        'daily-resting-heart-rate', 'daily_resting_heart_rate.date', start, end)
        for x in [row['dailyRestingHeartRate']])
    steps = ((date_field(row['civilStartTime']['date']), row['steps']['countSum'])
             for row in rollup('steps') if 'countSum' in row.get('steps', {}))
    azm = ((date_field(row['civilStartTime']['date']), total)
           for row in rollup('active-zone-minutes') if (total := azm_total(row.get('activeZoneMinutes', {}))) is not None)
    sleep = ((wake_date(x['interval'], tz), number(x['summary']['minutesAsleep'], 'sleep minutes') / 60)
             for row in reconcile('sleep', 'sleep.interval.civil_end_time', start, end)
        for x in [row['sleep']] if x.get('metadata', {}).get('mainSleep') is True
        and 'minutesAsleep' in x.get('summary', {}))
    pairs = [normalized(rows, start, end, lo, hi) for rows, lo, hi in (
        (rhr, 1, 300), (steps, 0, 150000), (sleep, 0.01, 24), (azm, 0, DAILY_AZM_MAX))]
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
