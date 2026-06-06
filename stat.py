import requests
import threading
import time
import sys
import random
import os
from queue import Queue

API = "https://discord.com/api/v9/unique-username/username-attempt-unauthed"
WEBHOOK = "https://discord.com/api/webhooks/1508590349713408231/CIljNz9hoywwrkH9ZJ7cjWVwUi5gogPNdGlWXzYucncqQb13qZZpB6D-Vi6wCSaeZ4WT"

# === GitHub Actions Settings ===
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")          # Required
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")  # e.g. "username/repo"
GITHUB_WORKFLOW = os.getenv("GITHUB_WORKFLOW")    # Workflow filename, e.g. "checker.yml"

# Safer settings
THREADS = 1
COOLDOWN_MIN = 7
COOLDOWN_MAX = 16
MAX_RETRIES = 5

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

def random_delay():
    delay = random.uniform(COOLDOWN_MIN, COOLDOWN_MAX)
    log(f"[SLEEP] {delay:.2f}s")
    time.sleep(delay)

def trigger_new_workflow_run():
    """Trigger a new GitHub Actions workflow run"""
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY or not GITHUB_WORKFLOW:
        log("[GITHUB] Missing GITHUB_TOKEN, GITHUB_REPOSITORY or GITHUB_WORKFLOW env vars - cannot retrigger")
        return False

    owner, repo = GITHUB_REPOSITORY.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{GITHUB_WORKFLOW}/dispatches"

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    payload = {
        "ref": "main",           # Change to "master" if your default branch is master
        "inputs": {}             # You can pass inputs if your workflow accepts them
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code in (200, 204):
            log(f"[GITHUB] Successfully triggered new workflow run!")
            return True
        else:
            log(f"[GITHUB] Failed to trigger workflow: {r.status_code} {r.text}")
            return False
    except Exception as e:
        log(f"[GITHUB] Error triggering workflow: {e}")
        return False

log("[INIT] Username checker started")

# Load names
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
    retries = 0
    while retries < MAX_RETRIES:
        random_delay()
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
                try:
                    retry_after = r.json().get("retry_after", 10)
                except:
                    retry_after = 10

                log(f"[RATE LIMITED] Sleeping {retry_after}s then retriggering workflow...")
                time.sleep(float(retry_after) + random.uniform(2, 5))

                # Trigger new GitHub Actions run and exit
                trigger_new_workflow_run()
                log("[EXIT] Rate limit hit → New workflow triggered. Exiting current run.")
                sys.exit(0)   # Important: exit so the current run stops cleanly

            else:
                log(f"[ERROR] {name} -> HTTP {r.status_code}")
                return

        except Exception as e:
            log(f"[REQUEST ERROR] {name} -> {e}")
            retries += 1
            backoff = (2 ** retries) + random.uniform(0.5, 2)
            time.sleep(backoff)

    log(f"[GAVE UP] {name}")

def worker():
    while True:
        if names_queue.empty():
            break
        name = names_queue.get()
        if name in checked:
            names_queue.task_done()
            continue

        with checked_lock:
            checked.add(name)

        check(name)
        names_queue.task_done()
        log(f"[TOTAL CHECKED] {len(checked)}")

# Start threads
threads = []
log(f"[START] Launching {THREADS} thread(s)")
for i in range(THREADS):
    t = threading.Thread(target=worker, name=f"worker-{i}", daemon=True)
    t.start()
    threads.append(t)

for t in threads:
    t.join()

log("[DONE] All names processed")
