import requests
import threading
import time
import sys
import random
import os
from queue import Queue

API = "https://discord.com/api/v9/unique-username/username-attempt-unauthed"
WEBHOOK = "https://discord.com/api/webhooks/1508590349713408231/CIljNz9hoywwrkH9ZJ7cjWVwUi5gogPNdGlWXzYucncqQb13qZZpB6D-Vi6wCSaeZ4WT"

# GitHub Actions Settings
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")
GITHUB_WORKFLOW = os.getenv("GITHUB_WORKFLOW")

THREADS = 1
COOLDOWN_MIN = 7
COOLDOWN_MAX = 16

request_lock = threading.Lock()
checked_lock = threading.Lock()
checked = set()
names_queue = Queue()

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Content-Type": "application/json"
})

def log(msg):
    print(msg, flush=True)
    sys.stdout.flush()

def trigger_new_workflow_run():
    """Immediately trigger a new workflow run and exit"""
    if not all([GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_WORKFLOW]):
        log("[GITHUB] Missing env vars - cannot trigger new run")
        return False

    owner, repo = GITHUB_REPOSITORY.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{GITHUB_WORKFLOW}/dispatches"

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    payload = {
        "ref": "main",        # Change to "master" if your default branch is master
        "inputs": {}
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code in (200, 204):
            log("[GITHUB] ✅ New workflow run triggered successfully!")
            return True
        else:
            log(f"[GITHUB] Trigger failed: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        log(f"[GITHUB] Error triggering new run: {e}")
        return False

log("[INIT] Username checker started")

# Load names.txt
with open("names.txt", "r", encoding="utf-8") as f:
    for line in f:
        name = line.strip()
        if name:
            names_queue.put(name)

def send_webhook(name):
    if not WEBHOOK:
        return
    try:
        session.post(
            WEBHOOK,
            json={"content": f"available: `{name}` @everyone", "allowed_mentions": {"parse": ["everyone"]}},
            timeout=10
        )
        log(f"[WEBHOOK] Sent hit for {name}")
    except Exception as e:
        log(f"[WEBHOOK ERROR] {e}")

def check(name):
    try:
        log(f"[CHECKING] {name}")
        r = session.post(API, json={"username": name}, timeout=15)
        log(f"[RESPONSE] {name} -> {r.status_code}")

        if r.status_code == 200:
            data = r.json()
            if data.get("taken", True):
                log(f"[TAKEN] {name}")
            else:
                log(f"[OPEN] {name}")
                with open("hits.txt", "a", encoding="utf-8") as f:
                    f.write(name + "\n")
                log(f"[SAVED] {name} -> hits.txt")
                send_webhook(name)
            return

        elif r.status_code == 429:
            log("[RATE LIMITED] → Triggering new GitHub workflow run immediately...")
            trigger_new_workflow_run()
            log("[EXIT] Rate limit detected → Exiting current run.")
            sys.exit(0)   # Stop this run right away

        else:
            log(f"[ERROR] {name} -> HTTP {r.status_code}")

    except Exception as e:
        log(f"[REQUEST ERROR] {name} -> {e}")

def worker():
    while not names_queue.empty():
        name = names_queue.get()
        if name in checked:
            names_queue.task_done()
            continue

        with checked_lock:
            checked.add(name)

        check(name)
        names_queue.task_done()
        log(f"[TOTAL CHECKED] {len(checked)}")

    log("[WORKER] Queue empty, exiting.")

# Start workers
log(f"[START] Launching {THREADS} thread(s)")
threads = []
for i in range(THREADS):
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    threads.append(t)

for t in threads:
    t.join()

log("[DONE] All names processed")
