# GitHub Daily Radar

A free scheduled Telegram digest that discovers public GitHub repositories and sends a Top 10 list daily at 12:20 in `Asia/Ho_Chi_Minh`.

## Features

- Searches across broad public GitHub repository queries and popular topics.
- Saves star-count snapshots in `data/state.json`.
- After the baseline run, ranks candidates by observed star increase since the previous successful run.
- Sends an English Telegram message with links, descriptions, languages, total stars, and growth.
- Prevents ordinary duplicate sends on the same Vietnam calendar day.

## Important accuracy note

GitHub repository search does not provide exact rolling 24-hour star history. This bot calculates growth from its own snapshots. The first run is a baseline and ranks by total stars. Later runs compare current counts with the previous snapshot; newly discovered repositories without an earlier snapshot are placed after candidates with known deltas. This is observed growth between runs, not guaranteed exact rolling 24-hour growth.

## Setup

1. In Telegram, open `@BotFather`, send `/newbot`, follow the prompts, and copy the bot token.
2. Open your new bot's private chat and press **Start**, then send it a message.
3. Get your chat ID. For example, after temporarily setting your token locally, open:
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   Find `message.chat.id` in the JSON. If `result` is empty, message the bot again and retry. Keep the token private.
4. Create a GitHub repository and upload all files in this project to its default branch.
5. In **Settings → Secrets and variables → Actions → New repository secret**, add:
   - `TELEGRAM_BOT_TOKEN` = token from BotFather
   - `TELEGRAM_CHAT_ID` = your private chat ID
6. In **Settings → Actions → General → Workflow permissions**, allow read and write permissions for repository contents.
7. Ensure `.github/workflows/daily-radar.yml` is committed on the default branch.
8. Open **Actions → GitHub Daily Radar → Run workflow** and run a test. The first successful run sends a baseline digest and saves the first snapshot.
9. After success, check `data/state.json` in the repository. It should contain `snapshot_at`, `last_sent_date`, and repo star counts.

## Schedule

The workflow uses `cron: "20 5 * * *"` in UTC. This targets 12:20 Vietnam time (UTC+7). GitHub may delay scheduled workflows during high load, so delivery is not guaranteed at the exact minute.

## Duplicate prevention

- `last_sent_date` prevents normal reruns on the same Vietnam calendar day from sending a second digest.
- Workflow concurrency prevents two runs from overlapping.
- Set `force_send` to `true` only when manually requesting a second message that day.

A rare failure window remains if Telegram accepts a message but the subsequent Git commit fails. A retry could send a duplicate. Telegram `sendMessage` does not offer a general idempotency key, so exactly-once delivery cannot be guaranteed by this simple design.

## Run locally (optional)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GITHUB_TOKEN = "YOUR_GITHUB_PERSONAL_ACCESS_TOKEN"
$env:TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
$env:TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"
python bot.py
```

A GitHub token is recommended for authenticated API limits. In GitHub Actions, `GITHUB_TOKEN` is supplied automatically.

## Troubleshooting

- **No Telegram message:** verify both Telegram secrets and press Start in the bot's private chat.
- **Telegram 401:** token invalid; rotate it in BotFather if exposed.
- **GitHub 403/429:** rate limit or access restriction; wait and retry.
- **Schedule not running:** ensure Actions is enabled and the workflow exists on the default branch; test using manual dispatch.
- **Day one has no growth values:** expected; the first run builds the baseline.

## Security

Never commit Telegram tokens or personal access tokens. Store them only in GitHub Actions Secrets. Revoke or rotate a token immediately if exposed.
