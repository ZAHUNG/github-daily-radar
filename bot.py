import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

UTC = timezone.utc
VN = timezone(timedelta(hours=7))
API = "https://api.github.com"
STATE_PATH = Path("data/state.json")
TOP_N = 10
TIMEOUT = 25


def now_vn():
    return datetime.now(UTC).astimezone(VN)


def iso_z(dt):
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def load_state():
    if not STATE_PATH.exists():
        return {"last_sent_date": None, "snapshot_at": None, "repos": {}}
    with STATE_PATH.open("r", encoding="utf-8") as f:
        state = json.load(f)
    state.setdefault("last_sent_date", None)
    state.setdefault("snapshot_at", None)
    state.setdefault("repos", {})
    return state


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(STATE_PATH)


def github_search(query, headers):
    response = requests.get(
        f"{API}/search/repositories",
        params={"q": query, "sort": "stars", "order": "desc", "per_page": 100},
        headers=headers,
        timeout=TIMEOUT,
    )
    if response.status_code in (403, 429):
        raise RuntimeError(
            f"GitHub API rate limit/error: HTTP {response.status_code}; "
            f"remaining={response.headers.get('X-RateLimit-Remaining')}, "
            f"reset={response.headers.get('X-RateLimit-Reset')}"
        )
    response.raise_for_status()
    data = response.json()
    if data.get("incomplete_results"):
        print(f"Warning: incomplete search results for: {query}", file=sys.stderr)
    return data.get("items", [])


def discover_repositories(now):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "GitHub-Daily-Radar",
    }
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    d7 = (now - timedelta(days=7)).date().isoformat()
    d30 = (now - timedelta(days=30)).date().isoformat()
    d90 = (now - timedelta(days=90)).date().isoformat()
    queries = [
        f"stars:>20 created:>={d90}",
        f"stars:>20 pushed:>={d7}",
        f"stars:>10 created:>={d30} topic:ai",
        f"stars:>10 created:>={d30} topic:developer-tools",
        f"stars:>10 created:>={d30} topic:machine-learning",
    ]
    found = {}
    for query in queries:
        for item in github_search(query, headers):
            if item.get("fork") or item.get("archived"):
                continue
            name = item.get("full_name")
            if not name:
                continue
            found[name] = {
                "full_name": name,
                "html_url": item.get("html_url", ""),
                "description": (item.get("description") or "").strip(),
                "language": item.get("language") or "Not specified",
                "stargazers_count": int(item.get("stargazers_count") or 0),
            }
    return list(found.values())


def esc(value):
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt(n):
    return f"{n:,}"


def make_message(ranked, now, baseline, elapsed_hours):
    lines = [
        "🔥 <b>GITHUB DAILY RADAR — TOP 10</b>",
        f"📅 {now.strftime('%Y-%m-%d')} · 12:35 Vietnam time",
        "",
    ]
    if baseline:
        lines += [
            "ℹ️ <b>Baseline run:</b> 24-hour star growth is not available yet.",
            "Ranked by total stars while the first snapshot is saved.",
            "",
        ]
    else:
        lines += [
            f"📈 Ranked by observed star growth since the previous snapshot (~{elapsed_hours:.1f} hours).",
            "",
        ]

    for i, repo in enumerate(ranked[:TOP_N], 1):
        delta = repo.get("delta")
        if baseline:
            growth = "baseline"
        elif delta is None:
            growth = "new candidate · baseline unavailable"
        elif delta >= 0:
            growth = f"+{fmt(delta)} stars"
        else:
            growth = f"{fmt(delta)} stars"
        desc = esc(repo["description"] or "No description provided.")
        if len(desc) > 180:
            desc = desc[:177].rstrip() + "..."
        lines += [
            f'<b>{i}. <a href="{esc(repo["html_url"])}">{esc(repo["full_name"])}</a></b>',
            f'⭐ {fmt(repo["stargazers_count"])} total · 📈 {esc(growth)} · 💻 {esc(repo["language"])}',
            desc,
            "",
        ]
    lines += [
        "Source: GitHub public repository data",
        "<i>Growth is calculated from snapshots collected by this bot; it may not equal an exact rolling 24-hour figure.</i>",
    ]
    return "\n".join(lines)


def send_telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {result}")
    return result


def main():
    now = now_vn()
    today = now.date().isoformat()
    state = load_state()
    if state.get("last_sent_date") == today and os.getenv("FORCE_SEND", "false").lower() != "true":
        print(f"Already sent today's digest ({today}); skipping duplicate.")
        return

    repos = discover_repositories(now)
    if not repos:
        raise RuntimeError("GitHub search returned no repositories; refusing to send an empty digest.")

    previous = state.get("repos", {})
    baseline = not bool(previous)
    elapsed_hours = 24.0
    if state.get("snapshot_at"):
        try:
            prior = datetime.fromisoformat(state["snapshot_at"].replace("Z", "+00:00"))
            elapsed_hours = max(0.0, (now.astimezone(UTC) - prior.astimezone(UTC)).total_seconds() / 3600)
        except (ValueError, TypeError):
            pass

    for repo in repos:
        old = previous.get(repo["full_name"])
        repo["delta"] = (
            repo["stargazers_count"] - int(old.get("stars", 0))
            if old is not None else None
        )

    if baseline:
        ranked = sorted(repos, key=lambda r: (r["stargazers_count"], r["full_name"]), reverse=True)
    else:
        ranked = sorted(
            repos,
            key=lambda r: (
                r["delta"] is not None,
                r["delta"] if r["delta"] is not None else -1,
                r["stargazers_count"],
                r["full_name"],
            ),
            reverse=True,
        )

    # Send first, then persist the state. A rare crash after Telegram accepts the
    # message but before the git commit can still lead to a duplicate on retry.
    send_telegram(make_message(ranked, now, baseline, elapsed_hours))
    state["repos"] = {
        r["full_name"]: {"stars": r["stargazers_count"], "seen_at": iso_z(now)}
        for r in repos
    }
    state["snapshot_at"] = iso_z(now)
    state["last_sent_date"] = today
    state["last_message_repo_names"] = [r["full_name"] for r in ranked[:TOP_N]]
    save_state(state)
    print(f"Sent Top {min(TOP_N, len(ranked))}; saved {len(repos)} repository snapshots.")


if __name__ == "__main__":
    main()
