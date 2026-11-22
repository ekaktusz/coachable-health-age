# Local CSV format

Save a comma-separated UTF-8 file with these five column names. Columns can be reordered, but each date must appear at most once.

| Column | What to enter |
| --- | --- |
| `date` | Local calendar day, `YYYY-MM-DD` |
| `resting_heart_rate_bpm` | Resting heart rate in beats per minute, not average heart rate |
| `steps` | Total daily steps |
| `sleep_hours` | Hours actually asleep during the main sleep session, on the day you woke up |
| `active_zone_minutes` | Total earned Active Zone Minutes for the day, already weighted for intensity; not workout duration or generic activity minutes |

Leave unobserved values blank. Keep actual zero steps or zero AZM as `0`. If your device does not report compatible AZM, do not rename another metric to fill the column. The calculator needs all four inputs on enough days to produce a score. The [example CSV](../examples/synthetic.csv) contains synthetic data, not health records.

## How days become a score

- `--end-exclusive` is the first day not counted. Its default is today in the computer's local time. Pass the chronological age as of the last included day (adults 18+).
- The calculator checks coverage in the previous 90 days and scores the most recent 12 whole seven-day blocks. A week qualifies when it has at least two days with all four measurements. At least five weeks must qualify.
- Resting heart rate, steps, and sleep use the averages of those aligned days. Weekly AZM is based on totals, not a daily average. If every qualifying week has all seven AZM days, the tool reports a point estimate. Otherwise, when five weeks still qualify, it reports an AZM-only sensitivity range. The ends reflect recorded AZM and the paper's scoring cap, not a statistical confidence interval.
- If fewer than five weeks qualify, the command returns `"status": "insufficient_data"` and coverage counts without a score. Malformed files produce an error with a row or column hint.

Offline imports and the Google Health adapter use the same window and scoring code. The input handling is this project's implementation, not Google's exact study preprocessing.
