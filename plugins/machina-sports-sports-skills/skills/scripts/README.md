# scripts/

Maintenance and operational scripts for the sports-skills repo.

---

## nightly_health_check.py

Tests every upstream data source used by the skills and produces structured health reports.

### What it checks

| Source | Endpoint(s) |
|--------|-------------|
| **ESPN** (12 leagues) | `site.api.espn.com/apis/site/v2/sports/soccer/<id>/scoreboard` |
| **FPL** | `fantasy.premierleague.com/api/bootstrap-static/` |
| **Understat** (5 leagues) | `understat.com/league/<slug>/<year>` |
| **Kalshi** | `api.elections.kalshi.com/trade-api/v2/markets` |
| **Polymarket Gamma** | `gamma-api.polymarket.com/markets` |
| **Polymarket CLOB** | `clob.polymarket.com/sampling-markets` |
| **FastF1** | import check + `fastf1.get_event_schedule(2024)` probe |
| **BBC Sport RSS** | `feeds.bbci.co.uk/sport/rss.xml` |

### Running manually

```bash
# From the repo root
python scripts/nightly_health_check.py
```

No dependencies beyond the standard library (feedparser is **not** required for the health check — it uses raw urllib instead). FastF1 must be installed if you want its check to pass; otherwise it will report `down` with an import error.

### Output files

All reports are written to `reports/health/`:

| File | Contents |
|------|----------|
| `YYYY-MM-DD.json` | Structured JSON with status, latency, errors, and sample data per source |
| `YYYY-MM-DD.md` | Human-readable Markdown summary table |
| `YYYY-MM-DD-issue.md` | GitHub issue body (only created when failures are detected) |

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All sources OK |
| `1` | One or more sources degraded (slow but reachable) |
| `2` | One or more sources down (unreachable or returning errors) |

### Thresholds

- **Timeout:** 10 seconds per request
- **Degraded threshold:** 3000 ms — sources slower than this are marked `degraded` even if they return a valid response

### Scheduling with cron

```cron
# Run every night at 02:00 UTC
0 2 * * * cd /path/to/sports-skills && python scripts/nightly_health_check.py >> logs/health_check.log 2>&1
```

### Scheduling with GitHub Actions

```yaml
# .github/workflows/health_check.yml
name: Nightly Health Check
on:
  schedule:
    - cron: "0 2 * * *"
  workflow_dispatch:

jobs:
  health:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install fastf1
      - run: python scripts/nightly_health_check.py
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: health-reports
          path: reports/health/
```
