import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

DATA = Path("docs/data/history.json")
MAX_ENTRIES = 336  # 7 days at 30-minute intervals
REPO = os.getenv("GITHUB_REPOSITORY")
TOKEN = os.getenv("GITHUB_TOKEN")
API = f"https://api.github.com/repos/{REPO}/issues"


def check(url):
    start = time.time()
    try:
        r = requests.get(url, timeout=10)
        ms = round((time.time() - start) * 1000)
        return {"up": r.status_code < 400, "code": r.status_code, "ms": ms}
    except requests.RequestException:
        return {"up": False, "code": None, "ms": None}


def sync_issue(name, up, now):
    if not (REPO and TOKEN):
        return
    headers = {"Authorization": f"Bearer {TOKEN}",
               "Accept": "application/vnd.github+json"}
    title = f"{name} is down"
    open_issues = requests.get(
        API, headers=headers,
        params={"state": "open", "labels": "outage"}, timeout=10).json()
    existing = [i for i in open_issues if i["title"] == title]
    if not up and not existing:
        requests.post(API, headers=headers, timeout=10, json={
            "title": title, "labels": ["outage"],
            "body": f"Outage detected at {now} by the uptime monitor."})
    elif up and existing:
        for issue in existing:
            url = f"{API}/{issue['number']}"
            requests.post(f"{url}/comments", headers=headers, timeout=10,
                          json={"body": f"Recovered at {now}."})
            requests.patch(url, headers=headers, timeout=10,
                           json={"state": "closed"})


def main():
    config = yaml.safe_load(Path("sites.yml").read_text())["sites"]
    old = json.loads(DATA.read_text()) if DATA.exists() else {"sites": []}
    old_checks = {s["name"]: s["checks"] for s in old["sites"]}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sites = []
    for site in config:
        result = check(site["url"])
        result["t"] = now
        checks = (old_checks.get(site["name"], []) + [result])[-MAX_ENTRIES:]
        sites.append({"name": site["name"], "url": site["url"], "checks": checks})
        sync_issue(site["name"], result["up"], now)
        print(f'{site["name"]}: {"UP" if result["up"] else "DOWN"} {result["ms"]} ms')

    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps({"updated": now, "sites": sites}))


if __name__ == "__main__":
    main()