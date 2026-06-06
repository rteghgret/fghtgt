import requests
import sys
import os
import random
import string
from queue import Queue

API = "https://discord.com/api/v9/unique-username/username-attempt-unauthed"
WEBHOOK = "https://discord.com/api/webhooks/1508590349713408231/CIljNz9hoywwrkH9ZJ7cjWVwUi5gogPNdGlWXzYucncqQb13qZZpB6D-Vi6wCSaeZ4WT"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")
GITHUB_WORKFLOW = "checker.yml"   # Hardcoded - do not change unless filename changes

# Random username settings
USERNAME_LENGTH = 4
NUM_USERNAMES = 10000   # How many to generate per run (adjust as needed)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json"
})

def log(msg):
    print(msg, flush=True)

def trigger_new_workflow_run():
    if not all([GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_WORKFLOW]):
        log("[GITHUB] Missing environment variables")
        return False

    owner, repo = GITHUB_REPOSITORY.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{GITHUB_WORKFLOW}/dispatches"

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    log(f"[GITHUB] Triggering workflow file: {GITHUB_WORKFLOW}")

    try:
        r = requests.post(url, json={"ref": "main"}, headers=headers, timeout=10)
        if r.status_code in (200, 204):
            log("[GITHUB] ✅ Successfully triggered new workflow run!")
            return True
        else:
            log(f"[GITHUB] Failed: {r.status_code} {r.text}")
            return False
    except Exception as e:
        log(f"[GITHUB] Error: {e}")
        return False

log("[INIT] Random 4-char username checker started")

# Character set: letters + digits + underscore + period
chars = string.ascii_lowercase + string.digits + "_."

# Generate random usernames
names_queue = Queue()
for _ in range(NUM_USERNAMES):
    username = ''.join(random.choice(chars) for _ in range(USERNAME_LENGTH))
    names_queue.put(username)

log(f"[GENERATED] {NUM_USERNAMES} random 4-character usernames")

def check(name):
    try:
        log(f"[CHECKING] {name}")
        r = session.post(API, json={"username": name}, timeout=15)
        log(f"[RESPONSE] {name} -> {r.status_code}")

        if r.status_code == 200:
            data = r.json()
            if not data.get("taken", True):
                log(f"[OPEN] {name}")
                with open("hits.txt", "a", encoding="utf-8") as f:
                    f.write(name + "\n")
                log(f"[SAVED] {name}")
        elif r.status_code == 429:
            log("[RATE LIMITED] → Triggering new workflow run immediately...")
            trigger_new_workflow_run()
            log("[EXIT] Exiting current run.")
            sys.exit(0)
        else:
            log(f"[ERROR] HTTP {r.status_code}")

    except Exception as e:
        log(f"[ERROR] {e}")

# Run the checker
while not names_queue.empty():
    name = names_queue.get()
    check(name)

log("[DONE]")
