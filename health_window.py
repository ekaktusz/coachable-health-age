"""Shared daily-window aggregation for local and Google Health inputs."""
from datetime import timedelta
from statistics import mean

from cha import calculate


def aggregate(start, end, rhr, steps, sleep_hours, azm):
    """Find adequately observed days and weekly AZM without filling gaps."""
    keys = ('rhr', 'steps', 'sleep_hours', 'azm')
    bounded = [{d: v for d, v in stream.items() if start <= d < end}
               for stream in (rhr, steps, sleep_hours, azm)]
    common = set.intersection(*(set(stream) for stream in bounded))
    weekly_azm, recorded_weekly_azm, valid_days, valid_weeks = [], [], set(), 0
    for n in range((end - start).days // 7):
        week = {end - timedelta(days=n * 7 + k) for k in range(1, 8)}
        shared = week & common
        if len(shared) >= 2:
            valid_weeks += 1
            valid_days.update(shared)
            total = sum(bounded[3][d] for d in week if d in bounded[3])
            recorded_weekly_azm.append(total)
            if week <= bounded[3].keys():
                weekly_azm.append(total)
    features = base = None
    if valid_weeks >= 5:
        base = {k: mean(stream[d] for d in sorted(valid_days)) for k, stream in zip(keys[:3], bounded)}
        if len(weekly_azm) == valid_weeks:
            features = dict(base, weekly_azm=mean(weekly_azm))
    azm_min = mean(recorded_weekly_azm) if base is not None else None
    return {'start': str(start), 'end_exclusive': str(end),
            'observed_days': dict(zip(keys, map(len, bounded))), 'aligned_days_used': len(valid_days),
            'valid_weeks': valid_weeks, 'complete_azm_weeks': len(weekly_azm), 'features': features,
            'base_features': base, 'recorded_mean_weekly_azm': azm_min}


def report(coverage, age):
    result = dict(coverage)
    if result['features'] is not None:
        result['coachable_health_age'] = calculate(age, **result['features'])
    if result['base_features'] is not None:
        azm_min = result['recorded_mean_weekly_azm']
        # Unobserved AZM cannot reduce recorded totals. 500 is the scoring
        # plateau, not an estimate of the user's missing activity.
        plateau = 500 if result['complete_azm_weeks'] < result['valid_weeks'] else azm_min
        lower = calculate(age, **result['base_features'], weekly_azm=plateau)
        upper = calculate(age, **result['base_features'], weekly_azm=azm_min)
        result['coachable_health_age_bounds'] = {
            'lower': lower['health_age'], 'upper': upper['health_age'],
            'chronological_age': age, 'delta_lower': lower['delta_years'], 'delta_upper': upper['delta_years'],
            'upper_age_contributions': upper['contributions_years']}
    return result
