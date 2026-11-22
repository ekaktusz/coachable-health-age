# Coachable Health Age

A Python tool for estimating **wearable-based biological age** using the [Coachable Health Age method published by Google Research](https://arxiv.org/html/2611.08568v1#S4.SS1).

The idea: start with your actual age, then use published links between everyday wearable measurements and health risk to adjust it up or down. The calculator shows what each input contributed, so you can see why you got that number.

## What goes in

- Resting heart rate (bpm)
- Average daily steps
- Average hours of sleep per night
- Average weekly Active Zone Minutes (AZM)

## Try it without an account

No account or extra Python packages needed for the example:

```sh
python3 cha.py --age 40 --rhr 65 --steps 8500 \
  --sleep-hours 7 --weekly-azm 180
```

**Result: 39.0 years**, about one year below the example’s actual age.

## Use your own data

**Option 1: Local CSV (no login, API key, or MCP).** Try the included synthetic file:

```sh
python3 csv_import.py examples/synthetic.csv --age 40 --end-exclusive 2025-02-05
```

- Copy the [sample CSV](examples/synthetic.csv) as a template. Use one row per local day: `date,resting_heart_rate_bpm,steps,sleep_hours,active_zone_minutes`. Record sleep on the day you woke up.
- Leave missing measurements blank. Enter `0` only for a measured zero. Use earned **Active Zone Minutes**, not generic active minutes or workout duration. Files from wearable apps need to be mapped to these columns first.
- Use your age at the end of the window. The tool looks back up to 90 days, ending yesterday by default. For older data, set `--end-exclusive` to the day after the last day you want included.

**Option 2: Google Health MCP (automatic, read-only).**

- Pass `--mcp-url "$GOOGLE_HEALTH_MCP_URL"` to `python3 google_health.py` to check your last 90 completed days through an existing, authorized connection.
- Add `--birth-date YYYY-MM-DD` to calculate your score.

Both imports use the same scoring rules. If enough weeks qualify but some AZM days are missing, you get an AZM sensitivity range rather than one number. If too little data qualifies, you get coverage counts without a score. See [CSV format and coverage rules](docs/csv-import.md).

Keep personal CSV files and output private. The CSV importer reads locally and does not upload your data.

## What the number means

A score of 39 at age 40 means your inputs moved the paper’s risk score down by about one year. It doesn’t mean your body is literally a year younger. This is an independent implementation of the paper’s four core inputs, not a medical test or an official Google score.
