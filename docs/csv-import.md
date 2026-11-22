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

The importer validates every row, even outside the scoring window. Its input limits are 1–300 bpm, 0–150,000 daily steps, 0.01–24 sleep hours and 0–2,880 daily AZM. These catch invalid data; they are not target ranges.

## How days become a score

- `--end-exclusive` is the first day not counted. Its default is today in the computer's local time. Pass the chronological age as of the last included day (adults 18+).
- The calculator checks coverage in the previous 90 days and scores the most recent 12 whole seven-day blocks. A week qualifies when it has at least two days with all four measurements. At least five weeks must qualify.
- Resting heart rate, steps, and sleep use the averages of those aligned days. Weekly AZM is based on totals, not a daily average. If every qualifying week has all seven AZM days, the tool reports a point estimate. Otherwise it varies the missing AZM in those weeks from zero to the input limit, with the other inputs held fixed. This is a sensitivity range, not a statistical confidence interval or a bound on a complete re-import, which may include different days or weeks.
- `start` is the coverage start; `scoring_start` is the start of the whole weeks used for scoring. `delta_years` is reported health age minus chronological age. `raw_delta_years` shows the sum of input contributions before the model's 18-year floor.
- If fewer than five weeks qualify, the command returns `"status": "insufficient_data"` and coverage counts without a score. Malformed files produce an error with a row or column hint.

Offline imports and the Google Health adapter use the same window and scoring code. The adapter uses Google's daily resting heart rate and earned AZM; for sleep, it uses the recorded local wake date or end offset when available, falling back to the account time zone. This is not the paper's exact study preprocessing.
