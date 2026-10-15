# PisoRentBot

Async London rental scraper for OpenRent, Rightmove, and Zoopla. It enforces the
configured true-cost, property type, floor, move-in, geography, and dual-commute
rules before sending deduplicated Telegram cards.

## Run locally

Requires Python 3.12 and Tesseract. Portal HTML changes regularly; the adapters
first extract embedded JSON and then use a headless Chromium fallback.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
playwright install chromium
Copy-Item .env.example .env
pisorent run
```

Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `GEOAPIFY_API_KEY` in `.env`.
TfL credentials are optional but recommended for rate limits. Adjust portal URLs
and search rules in `config.yaml`.

- `pisorent run`: one check, suitable for cron.
- `pisorent daemon`: repeat at `runtime.poll_interval_seconds`.
- `pisorent telegram`: run `/help` and inline Save/Hide handlers.

No message is sent for an empty check. SQLite tracks cross-portal fingerprints,
price drops, saved homes, and hidden buildings.

## Docker

Set `runtime.database_path: /app/data/pisorent.db` in your mounted config, then:

```powershell
docker compose up -d --build
```

## GitHub Actions

Add the environment variables above as repository secrets. `scrape.yml` runs
every ten minutes and restores the latest SQLite cache. GitHub cron scheduling
can be delayed under load, so use Docker on an always-on host when exact
five-minute checks matter.
