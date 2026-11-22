# Coachable Health Age

A Python tool for estimating **wearable-based biological age** using the [Coachable Health Age method published by Google Research](https://arxiv.org/html/2611.08568v1#S4.SS1).

The idea: start with your actual age, then use published links between everyday wearable measurements and health risk to adjust it up or down. The calculator shows what each input contributed, so you can see why you got that number.

## What goes in

- Resting heart rate (bpm)
- Average daily steps
- Average hours of sleep per night
- Average weekly Active Zone Minutes (AZM)

## Try it

No account or extra Python packages needed for the example:

```sh
python3 cha.py --age 40 --rhr 65 --steps 8500 \
  --sleep-hours 7 --weekly-azm 180
```

**Result: 39.0 years**, about one year below the example’s actual age.

## Use your Google Health data

- Pass `--mcp-url "$GOOGLE_HEALTH_MCP_URL"` to `python3 google_health.py` to check your last 90 completed days through an existing, authorized connection.
- Add `--birth-date YYYY-MM-DD` to calculate your score.
- If AZM records are incomplete, the tool reports a range when it has enough data. Missing days aren’t treated as zero.

## What the number means

A score of 39 at age 40 means your inputs moved the paper’s risk score down by about one year. It doesn’t mean your body is literally a year younger. This is an independent implementation of the paper’s four core inputs, not a medical test or an official Google score.
