import os
import json
import subprocess
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

ACCOUNT_ID = "a0d2686f0804c32456ef0f58975e9853"
NAMESPACE_ID = "897dcd24fa784dbc90f32d4d6cb0db21"
PROJECT_DIR = Path(__file__).resolve().parent.parent
TOKEN_FILE = PROJECT_DIR / ".cloudflare-token"
ENV_FILE = PROJECT_DIR / ".env.local"
LOG_FILE = PROJECT_DIR / "queue-runner.log"
CF_KV = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/storage/kv/namespaces/{NAMESPACE_ID}"

_log_fh = None


def log(msg=""):
    print(msg)
    if _log_fh:
        _log_fh.write(msg + "\n")
        _log_fh.flush()


def load_env():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def get_token():
    if not TOKEN_FILE.exists():
        raise RuntimeError(f".cloudflare-token not found at {TOKEN_FILE}")
    return TOKEN_FILE.read_text(encoding="utf-8").strip()


def cf_get(token, path):
    import requests
    resp = requests.get(f"{CF_KV}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=15)
    resp.raise_for_status()
    return resp


def cf_put(token, path, value):
    import requests
    requests.put(f"{CF_KV}{path}", headers={"Authorization": f"Bearer {token}"}, data=value, timeout=15).raise_for_status()


def cf_delete(token, path):
    import requests
    requests.delete(f"{CF_KV}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=15).raise_for_status()


def list_queue_keys(token):
    resp = cf_get(token, "/keys?prefix=queue%3A&limit=100")
    return [k["name"] for k in resp.json().get("result", [])]


def get_job(token, key):
    resp = cf_get(token, f"/values/{urllib.parse.quote(key, safe='')}")
    return json.loads(resp.text)


def delete_job(token, key):
    cf_delete(token, f"/values/{urllib.parse.quote(key, safe='')}")


def mark_processed(token, shortcode):
    cf_put(token, f"/values/processed%3A{shortcode}", "1")


def run_script(name, env):
    """Run a script, streaming its output live to both stdout and the log file."""
    proc = subprocess.Popen(
        [sys.executable, str(PROJECT_DIR / "scripts" / name)],
        env=env,
        cwd=str(PROJECT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in proc.stdout:
        line = line.rstrip("\n")
        log(line)
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"{name} exited with code {proc.returncode}")


def process_job(token, job):
    mode = job.get("mode", "instagram")
    env = os.environ.copy()
    env["MODE"] = mode

    if mode == "instagram":
        env["INSTAGRAM_URL"] = job.get("url", "")
        env["EXTRACT_TEXT"] = "false" if not job.get("extract_text", True) else "true"
    elif mode in ("urls", "text"):
        env["CONTENT"] = job.get("content", "")

    if job.get("notion_title_override"):
        env["NOTION_TITLE_OVERRIDE"] = job["notion_title_override"]

    run_script("process.py", env)

    if job.get("push_to_notion", True):
        run_script("notion_push.py", env)

    if mode == "instagram":
        shortcode = job.get("shortcode") or job.get("url", "").rstrip("/").split("/")[-1]
        if shortcode:
            try:
                mark_processed(token, shortcode)
            except Exception as e:
                log(f"  [warn] Could not mark processed in KV: {e}")


def main():
    global _log_fh
    _log_fh = open(LOG_FILE, "a", encoding="utf-8")

    try:
        load_env()

        try:
            import requests  # noqa: F401
        except ImportError:
            log("[error] 'requests' is not installed. Run: pip install requests")
            sys.exit(1)

        run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log(f"\n{'='*60}")
        log(f"  Queue run: {run_ts}")
        log(f"{'='*60}")

        token = get_token()

        log("[queue] Checking for pending jobs...")
        keys = list_queue_keys(token)

        if not keys:
            log("[queue] No pending jobs.")
            return

        log(f"[queue] Found {len(keys)} job(s).")

        for key in sorted(keys):
            log(f"\n[job] {key}")
            try:
                job = get_job(token, key)
                log(f"  mode={job.get('mode')}  url={job.get('url', job.get('content', ''))[:60]}")
                process_job(token, job)
                delete_job(token, key)
                log(f"  [done] Removed from queue.")
            except Exception as e:
                log(f"  [error] {e}")
                log(f"  [retry] Left in queue for next run.")

        log(f"\n[queue] Run complete.")

    finally:
        _log_fh.close()
        _log_fh = None


if __name__ == "__main__":
    main()
