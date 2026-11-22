"""Calculate a core Coachable Health Age from a local daily CSV."""
import argparse
import csv
from datetime import date, timedelta
import json
from math import isfinite
from pathlib import Path

from health_window import DAILY_AZM_MAX, aggregate, report

FIELDS = ('date', 'resting_heart_rate_bpm', 'steps', 'sleep_hours', 'active_zone_minutes')
LIMITS = ((1, 300), (0, 150_000), (0.01, 24), (0, DAILY_AZM_MAX))


def load_csv(source, end):
    """Parse locally, preserving a missing cell separately from a measured zero."""
    start = end - timedelta(days=90)
    reader = csv.reader(source, strict=True)
    streams = ({}, {}, {}, {})
    seen = set()
    try:
        header = next(reader, [])
        if len(header) != len(FIELDS) or set(header) != set(FIELDS):
            raise ValueError('Expected CSV columns: ' + ','.join(FIELDS))
        indices = [header.index(field) for field in FIELDS]
        for row in reader:
            if not row or (len(row) == 1 and not row[0].strip()):
                continue
            prefix = f'Row {reader.line_num}:'
            if len(row) != len(FIELDS):
                raise ValueError(f'{prefix} expected {len(FIELDS)} columns')
            raw_date = row[indices[0]].strip()
            try:
                day = date.fromisoformat(raw_date)
                if day.isoformat() != raw_date:
                    raise ValueError
            except ValueError:
                raise ValueError(f'{prefix} date must be YYYY-MM-DD') from None
            if day in seen:
                raise ValueError(f'{prefix} duplicate date; use one row per day')
            seen.add(day)
            for field, idx, stream, (lo, hi) in zip(FIELDS[1:], indices[1:], streams, LIMITS):
                raw = row[idx].strip()
                if not raw:
                    continue
                try:
                    value = float(raw)
                    if not isfinite(value) or not lo <= value <= hi:
                        raise ValueError
                except ValueError:
                    raise ValueError(f'{prefix} invalid {field}; expected a number from {lo} to {hi}') from None
                if start <= day < end:
                    stream[day] = value
    except csv.Error:
        raise ValueError(f'Invalid CSV near line {reader.line_num}') from None
    return aggregate(start, end, *streams)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_file', type=Path, help='Path to a UTF-8 CSV in the project format')
    parser.add_argument('--age', type=float, required=True, help='Chronological age on the last included day (18+)')
    parser.add_argument('--end-exclusive', type=date.fromisoformat, default=date.today(),
                        help='First local date to exclude (default: today); use for historical files')
    args = parser.parse_args()
    if not isfinite(args.age) or args.age < 18:
        parser.error('--age must be a finite number of at least 18')
    if args.end_exclusive > date.today():
        parser.error('--end-exclusive cannot include unfinished or future days')
    try:
        with args.csv_file.open(encoding='utf-8-sig', newline='') as source:
            result = report(load_csv(source, args.end_exclusive), args.age)
    except (OSError, UnicodeError):
        parser.error('Could not read CSV; check the file path and UTF-8 encoding')
    except (ValueError, OverflowError) as error:
        parser.error(str(error))
    if 'coachable_health_age' in result:
        result['status'] = 'point_estimate'
    elif 'coachable_health_age_bounds' in result:
        result['status'] = 'azm_sensitivity_range'
    else:
        result['status'] = 'insufficient_data'
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
