"""Core-only Coachable Health Age, arXiv:2611.08568v1, Eqs. 1–6 and 8."""
import argparse
import json
from math import fsum, isfinite, log


def calculate(age, rhr, steps, sleep_hours, weekly_azm):
    """Score already aggregated inputs; no optional domains or imputation."""
    for name, value, low, high in (
        ('age', age, 18, float('inf')), ('rhr', rhr, 0.01, float('inf')),
        ('steps', steps, 0, float('inf')), ('sleep_hours', sleep_hours, 0.01, 24),
        ('weekly_azm', weekly_azm, 0, float('inf')),
    ):
        if type(value) not in (float, int) or not isfinite(value) or not low <= value <= high:
            raise ValueError(f'Missing or invalid {name}')
    if rhr <= 60:
        heart = 0.0
    elif rhr <= 70:
        heart = (rhr - 60) / 10 * log(1.08)
    else:
        heart = log(1.08) + (rhr - 70) / 20 * (log(1.33) - log(1.08))
    sleep = (6 - sleep_hours) * log(1.20) if sleep_hours < 6 else max(0, sleep_hours - 9) * log(1.34)
    azm = 0.0 if weekly_azm < 115 else log(.68)
    knots = ((115, 1), (245, .76), (418, .71), (500, .68))
    for (start, start_hr), (end, end_hr) in zip(knots, knots[1:]):
        if start <= weekly_azm < end:
            azm = log(start_hr) + (weekly_azm - start) / (end - start) * (log(end_hr) - log(start_hr))
            break
    contributions = {
        'resting_heart_rate': .7066 * heart / .1,
        'steps': .4773 * (min(steps, 9000) - 8000) / 1000 * log(.88) / .1,
        'sleep_duration': .8790 * sleep / .1,
        'active_zone_minutes': .6950 * azm / .1,
    }
    delta = fsum(contributions.values())
    return {'model': 'arxiv:2611.08568v1/core-only', 'chronological_age': age,
            'health_age': max(18, age + delta), 'delta_years': delta,
            'contributions_years': contributions}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for field, help_text in [('age', 'chronological age (years)'), ('rhr', 'resting heart rate (bpm)'),
                             ('steps', 'mean daily steps'), ('sleep-hours', 'mean hours asleep per night'),
                             ('weekly-azm', 'mean weekly Active Zone Minutes')]:
        parser.add_argument('--' + field, type=float, required=True, help=help_text)
    try:
        print(json.dumps(calculate(**vars(parser.parse_args())), indent=2, allow_nan=False))
    except ValueError as error:
        parser.error(str(error))
