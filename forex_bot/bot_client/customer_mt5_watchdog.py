"""Customer-side watchdog for MT5 bot.

Keep this process running on the customer's machine. It polls the license server
for the desired account state and starts/stops mt5_ai_bot.py locally.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import subprocess
import sys
import time
from typing import Any

import httpx


BOT_DIR = Path(__file__).resolve().parent
LOG_DIR = BOT_DIR / "logs"


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Watchdog:
    def __init__(self) -> None:
        self.server_url = os.getenv("SERVER_URL", "http://localhost:8000").rstrip("/")
        self.license_key = os.getenv("LICENSE_KEY", "").strip()
        self.mt_account = (os.getenv("MT_ACCOUNT") or os.getenv("MT5_LOGIN") or "").strip()
        self.poll_seconds = env_int("CUSTOMER_WATCHDOG_POLL_SECONDS", 5)
        self.restart_seconds = env_int("CUSTOMER_BOT_RESTART_SECONDS", 10)
        self.process: subprocess.Popen | None = None
        self.log_file: Any = None
        self.last_start_attempt = 0.0
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.watchdog_log_path = LOG_DIR / f"customer_{self.mt_account or 'unknown'}_watchdog.log"
        self.bot_log_path = LOG_DIR / f"customer_{self.mt_account or 'unknown'}_bot.log"

    def log(self, message: str) -> None:
        line = f"[{now_text()}] {message}"
        print(line, flush=True)
        with open(self.watchdog_log_path, "a", encoding="utf-8") as file:
            file.write(line + "\n")

    def validate_config(self) -> None:
        if not self.license_key:
            raise RuntimeError("LICENSE_KEY chưa được cấu hình")
        if not self.mt_account:
            raise RuntimeError("MT_ACCOUNT/MT5_LOGIN chưa được cấu hình")

    def fetch_state(self) -> dict[str, Any]:
        response = httpx.post(
            f"{self.server_url}/bot/run-state",
            json={"license_key": self.license_key, "mt_account": self.mt_account},
            timeout=10,
        )
        if response.status_code != 200:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except Exception:
                pass
            raise RuntimeError(f"run-state rejected: {detail}")
        data = response.json()
        self.poll_seconds = env_int("CUSTOMER_WATCHDOG_POLL_SECONDS", int(data.get("poll_seconds") or self.poll_seconds))
        return data

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start_bot(self) -> None:
        now = time.time()
        if now - self.last_start_attempt < self.restart_seconds:
            return
        self.last_start_attempt = now

        if self.log_file is not None:
            try:
                self.log_file.close()
            except Exception:
                pass
        self.log_file = open(self.bot_log_path, "a", encoding="utf-8")
        self.log_file.write(f"\n[{now_text()}] START customer bot account={self.mt_account}\n")
        self.log_file.flush()
        self.process = subprocess.Popen(
            [sys.executable, "mt5_ai_bot.py"],
            cwd=str(BOT_DIR),
            env=os.environ.copy(),
            stdout=self.log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        self.log(f"Started bot pid={self.process.pid} log={self.bot_log_path}")

    def stop_bot(self, reason: str) -> None:
        if not self.process:
            return
        if self.process.poll() is not None:
            self.close_bot_log(f"EXIT code={self.process.returncode}")
            self.process = None
            return
        self.log(f"Stopping bot | {reason}")
        self.process.terminate()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.close_bot_log(f"STOP reason={reason}")
        self.process = None

    def close_bot_log(self, message: str) -> None:
        if self.log_file is None:
            return
        self.log_file.write(f"[{now_text()}] {message}\n")
        self.log_file.flush()
        self.log_file.close()
        self.log_file = None

    def reconcile(self, state: dict[str, Any]) -> None:
        should_run = bool(state.get("should_run"))
        run_status = state.get("run_status")
        if should_run and run_status == "pending_restart" and self.is_running():
            self.stop_bot("server requested restart")
            self.start_bot()
            return
        if should_run and not self.is_running():
            self.start_bot()
            return
        if not should_run and self.is_running():
            self.stop_bot(f"server state={run_status}")
            return
        if self.process and self.process.poll() is not None:
            code = self.process.returncode
            self.close_bot_log(f"EXIT code={code}")
            self.log(f"Bot exited code={code}; desired_run={should_run}")
            self.process = None

    def run(self) -> None:
        self.validate_config()
        self.log(f"Watchdog started | server={self.server_url} account={self.mt_account}")
        try:
            while True:
                try:
                    state = self.fetch_state()
                    self.reconcile(state)
                except Exception as exc:
                    self.log(f"Warning: {exc}")
                time.sleep(max(1, self.poll_seconds))
        except KeyboardInterrupt:
            self.log("Watchdog stopping by keyboard")
        finally:
            self.stop_bot("watchdog shutdown")


if __name__ == "__main__":
    Watchdog().run()
