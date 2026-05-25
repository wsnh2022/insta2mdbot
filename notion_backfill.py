"""
notion_backfill.py

Submits already-processed Instagram posts to the Worker so they get pushed to Notion.
Reads shortcodes from a file (one per line), fires them with a delay between each,
logs all results, and retries any failures at the end.

Usage:
    python notion_backfill.py shortcodes.txt
    python notion_backfill.py shortcodes.txt --delay 90 --retry-delay 120
    python notion_backfill.py shortcodes.txt --start 20
"""

import sys
import time
import argparse
import requests
import getpass
from datetime import datetime
from pathlib import Path

WORKER_URL = "https://instatomdnotes-worker.yogiswagger28.workers.dev"
DEFAULT_DELAY = 90
DEFAULT_RETRY_DELAY = 120
LOG_FILE = Path("backfill_log.txt")


def timestamp():
    return datetime.now().strftime("%H:%M:%S")


def log(line, log_fh):
    print(line, flush=True)
    log_fh.write(line + "\n")
    log_fh.flush()


def submit(shortcode, passphrase):
    url = f"https://www.instagram.com/p/{shortcode}/"
    resp = requests.post(
        WORKER_URL,
        headers={"Content-Type": "application/json", "X-Access-Key": passphrase},
        json={"instagram_url": url, "push_to_notion": True},
        timeout=15,
    )
    return resp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Text file with shortcodes, one per line")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY,
                        help=f"Seconds between submissions (default: {DEFAULT_DELAY})")
    parser.add_argument("--retry-delay", type=int, default=DEFAULT_RETRY_DELAY,
                        help=f"Seconds between retries (default: {DEFAULT_RETRY_DELAY})")
    parser.add_argument("--start", type=int, default=1,
                        help="Resume from this position (default: 1)")
    args = parser.parse_args()

    with open(args.file, encoding="utf-8") as f:
        shortcodes = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    if not shortcodes:
        print("No shortcodes found in file.")
        sys.exit(1)

    passphrase = getpass.getpass("Passphrase: ")

    start_idx = args.start - 1
    total = len(shortcodes)
    remaining = shortcodes[start_idx:]
    eta_min = len(remaining) * args.delay // 60

    failed = []

    with open(LOG_FILE, "a", encoding="utf-8") as log_fh:
        log(f"\n{'='*60}", log_fh)
        log(f"[{timestamp()}] Starting backfill — {len(remaining)} posts, {args.delay}s delay, ETA ~{eta_min}min", log_fh)
        log(f"{'='*60}", log_fh)

        # Main pass
        for i, shortcode in enumerate(remaining):
            position = start_idx + i + 1
            prefix = f"[{timestamp()}] [{position}/{total}] {shortcode}"

            try:
                resp = submit(shortcode, passphrase)
                if resp.status_code == 200:
                    log(f"{prefix} — triggered", log_fh)
                elif resp.status_code == 401:
                    log(f"{prefix} — WRONG PASSPHRASE. Stopping.", log_fh)
                    sys.exit(1)
                elif resp.status_code == 429:
                    log(f"{prefix} — rate limited (Worker). Adding to retry.", log_fh)
                    failed.append(shortcode)
                else:
                    log(f"{prefix} — failed ({resp.status_code}). Adding to retry.", log_fh)
                    failed.append(shortcode)
            except Exception as e:
                log(f"{prefix} — error: {e}. Adding to retry.", log_fh)
                failed.append(shortcode)

            if i < len(remaining) - 1:
                time.sleep(args.delay)

        # Retry pass
        if failed:
            log(f"\n[{timestamp()}] {len(failed)} failed. Waiting 2min before retry pass...", log_fh)
            time.sleep(args.retry_delay)
            log(f"[{timestamp()}] Starting retry pass...", log_fh)

            still_failed = []
            for i, shortcode in enumerate(failed):
                prefix = f"[{timestamp()}] [retry {i+1}/{len(failed)}] {shortcode}"
                try:
                    resp = submit(shortcode, passphrase)
                    if resp.status_code == 200:
                        log(f"{prefix} — triggered", log_fh)
                    elif resp.status_code == 401:
                        log(f"{prefix} — WRONG PASSPHRASE. Stopping.", log_fh)
                        sys.exit(1)
                    else:
                        log(f"{prefix} — still failing ({resp.status_code}). Manual check needed.", log_fh)
                        still_failed.append(shortcode)
                except Exception as e:
                    log(f"{prefix} — error: {e}. Manual check needed.", log_fh)
                    still_failed.append(shortcode)

                if i < len(failed) - 1:
                    time.sleep(args.retry_delay)

            if still_failed:
                log(f"\n[{timestamp()}] {len(still_failed)} permanently failed — check Actions log for these:", log_fh)
                for sc in still_failed:
                    log(f"  https://www.instagram.com/p/{sc}/", log_fh)
            else:
                log(f"\n[{timestamp()}] All retries succeeded.", log_fh)
        else:
            log(f"\n[{timestamp()}] All {total} submitted successfully. No retries needed.", log_fh)

        log(f"[{timestamp()}] Log saved to {LOG_FILE.resolve()}", log_fh)


if __name__ == "__main__":
    main()
