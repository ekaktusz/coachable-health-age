# Coachable Health Age (core only)

Independent implementation of [arXiv:2611.08568v1](https://arxiv.org/html/2611.08568v1#S4.SS1), equations 1–6 and 8, with the paper’s adult output floor. This is a wearable risk-equivalent coaching score, not a clinical or epigenetic biological age, and not a reproduction of any app result. No SensorWM or optional domains are used.

```sh
python3 -m unittest -v
python3 cha.py --age 40 --rhr 60 --steps 9000 --sleep-hours 7 --weekly-azm 500
python3 google_health.py --mcp-url "$GOOGLE_HEALTH_MCP_URL"
```

The last command checks coverage through yesterday; give `--birth-date YYYY-MM-DD` to calculate as of the last completed local day, or apply `report(coverage, age)` in-process. It targets an already authenticated Google Health MCP server. Use the trusted endpoint’s HTTPS URL directly; redirects are not followed. For a local server or tunnel at `127.0.0.1` or `::1`, add `--allow-loopback-http` to permit plaintext on that connection only. It does not save individual measurements or send data to any additional service. Console output contains sensitive summary values.

The Google Health adapter is not the authors’ preprocessing. It queries 90 completed days, looks at the latest 12 whole seven-day blocks, requires at least five blocks with at least two dates having all four core measurements, and uses those aligned days for the three daily features. It uses Google’s daily RHR and AZM rather than reconstructing the All of Us study’s daily-minimum HR and legacy activity proxies. Main sleep is assigned to the local wake date. Google’s AZM rollup sums earned minutes, already intensity-weighted. A point estimate requires at least five valid weeks and explicit AZM on all seven days of every valid week; if incomplete, a sensitivity interval uses the recorded total as the lower bound on AZM and the paper’s 500 AZM scoring plateau as the most favorable scoring case. This is sensitivity to AZM only, not a statistical confidence interval. It does not account for missingness in other features, measurement error, or differences between devices. Do not use a sensitivity edge as a training target.
