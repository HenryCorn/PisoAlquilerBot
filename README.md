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
- `pisorent telegram`: run `/help` and inline Save/Hide handlers by polling
  (local use only; it stops working once the Worker webhook below is set).

No message is sent for an empty check. SQLite tracks cross-portal fingerprints,
price drops, saved homes, and hidden buildings.

## Docker

Set `runtime.database_path: /app/data/pisorent.db` in your mounted config, then:

```powershell
docker compose up -d --build
```

## Serverless deployment (free)

State lives in Cloudflare D1. A Cloudflare Worker answers the Telegram buttons
instantly, and GitHub Actions runs the scraper whenever cron-job.org calls
`workflow_dispatch`, which avoids GitHub's throttled cron.

```text
cron-job.org ──dispatch──▶ GitHub Actions (scrape) ──HTTP API──▶ D1 ◀── Worker ◀── Telegram buttons
                                     └──────────── cards ────────────▶ Telegram
```

1. **D1 and the Worker** (needs a free Cloudflare account):

   ```powershell
   cd worker
   npx wrangler login
   npx wrangler d1 create pisorent          # copy database_id into wrangler.toml
   npx wrangler d1 execute pisorent --remote --file=schema.sql
   npx wrangler secret put TELEGRAM_BOT_TOKEN
   npx wrangler secret put TELEGRAM_CHAT_ID
   npx wrangler secret put TELEGRAM_WEBHOOK_SECRET   # any random string
   npx wrangler deploy                      # prints https://pisorent-telegram.<you>.workers.dev
   ```

2. **Point Telegram at the Worker:**

   ```powershell
   curl.exe "https://api.telegram.org/bot<TOKEN>/setWebhook?url=<WORKER_URL>&secret_token=<WEBHOOK_SECRET>&allowed_updates=%5B%22message%22,%22callback_query%22%5D"
   ```

3. **GitHub secrets:** add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
   `GEOAPIFY_API_KEY`, the optional TfL keys, and `CLOUDFLARE_ACCOUNT_ID`,
   `CLOUDFLARE_D1_DATABASE_ID`, and `CLOUDFLARE_API_TOKEN` (a custom token with
   *Account → D1 → Edit*).

4. **Trigger:** create a fine-grained GitHub token limited to this repository
   with *Actions: Read and write*. In cron-job.org, add a job every 5–10 minutes:

   - `POST https://api.github.com/repos/HenryCorn/PisoAlquilerBot/actions/workflows/scrape.yml/dispatches`
   - Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`,
     `X-GitHub-Api-Version: 2022-11-28`
   - Body: `{"ref":"master"}` (GitHub replies `204 No Content`)

   The hourly GitHub cron in `scrape.yml` is only a backstop.
