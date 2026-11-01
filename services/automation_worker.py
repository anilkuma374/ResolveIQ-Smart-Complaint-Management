"""Standalone 30-second automation worker. Run in a separate terminal from Streamlit."""
import argparse
import time
import traceback
import os
from pathlib import Path
from database.db import initialize
from services.automation import run_automation_cycle


def load_dotenv():
    """Load simple KEY=VALUE entries from the project .env file without extra packages."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="ResolveIQ background automation worker")
    parser.add_argument("--interval", type=int, default=30, help="Polling interval in seconds (default: 30)")
    args = parser.parse_args()
    interval = max(5, args.interval)
    print(f"ResolveIQ automation worker started; polling every {interval} seconds. Press Ctrl+C to stop.", flush=True)
    while True:
        conn = None
        try:
            conn = initialize()
            result = run_automation_cycle(conn)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {result}", flush=True)
        except KeyboardInterrupt:
            break
        except Exception:
            traceback.print_exc()
        finally:
            if conn is not None:
                conn.close()
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            break
    print("ResolveIQ automation worker stopped.", flush=True)


if __name__ == "__main__":
    main()
