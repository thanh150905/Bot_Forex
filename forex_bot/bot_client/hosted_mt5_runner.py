"""
Hosted MT5 runner.

Chạy trên Windows VPS của bạn. Runner đọc bảng mt5_accounts trong license server
và spawn một process mt5_ai_bot.py riêng cho từng tài khoản đang bật trên web.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import base64
import hashlib
import hmac
import os
import sqlite3
import subprocess
import sys
import time


BOT_DIR = Path(__file__).resolve().parent
ROOT_DIR = BOT_DIR.parent
SERVER_DIR = ROOT_DIR / "license_server"


DEFAULT_DB_PATH = SERVER_DIR / "forex_license.db"
DB_PATH = Path(os.getenv("HOSTED_RUNNER_DB", str(DEFAULT_DB_PATH))).resolve()
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000").rstrip("/")
POLL_SECONDS = int(os.getenv("HOSTED_RUNNER_POLL_SECONDS", "5"))
BOT_PYTHON = os.getenv("BOT_PYTHON", sys.executable)
LOG_DIR = Path(os.getenv("HOSTED_RUNNER_LOG_DIR", str(BOT_DIR / "logs"))).resolve()
DEFAULT_SECRET_KEY = "CHANGE_THIS_TO_RANDOM_64_CHAR_STRING_BEFORE_DEPLOY"
SINGLE_TERMINAL_MODE = os.getenv("HOSTED_RUNNER_SINGLE_TERMINAL", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
LOCAL_RUNNER_ALLOWED_IPS = {
    item.strip()
    for item in os.getenv("HOSTED_RUNNER_ALLOWED_IPS", "127.0.0.1,::1,localhost").split(",")
    if item.strip()
}


@dataclass
class ManagedProcess:
    account_id: int
    process: subprocess.Popen
    log_file: object


processes: dict[int, ManagedProcess] = {}


def utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")


def credential_source() -> str:
    return os.getenv("MT5_CREDENTIAL_KEY") or os.getenv("SECRET_KEY") or DEFAULT_SECRET_KEY


def credential_key(salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", credential_source().encode("utf-8"), salt, 120_000, dklen=32)


def unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def credential_stream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks = []
    counter = 0
    while sum(len(block) for block in blocks) < length:
        blocks.append(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:length]


def decrypt_secret(encrypted: str) -> str:
    version, salt_text, nonce_text, cipher_text, tag_text = encrypted.split(":", 4)
    if version != "v1":
        raise ValueError("Unsupported secret version")
    salt = unb64(salt_text)
    nonce = unb64(nonce_text)
    cipher = unb64(cipher_text)
    tag = unb64(tag_text)
    key = credential_key(salt)
    expected = hmac.new(key, salt + nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("Secret integrity check failed. MT5_CREDENTIAL_KEY của runner không khớp server.")
    stream = credential_stream(key, nonce, len(cipher))
    return bytes(a ^ b for a, b in zip(cipher, stream)).decode("utf-8")


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def update_account(account_id: int, **values: object) -> None:
    if not values:
        return
    values["updated_at"] = utc_now_text()
    assignments = ", ".join(f"{key}=?" for key in values)
    params = list(values.values()) + [account_id]
    with connect_db() as conn:
        conn.execute(f"UPDATE mt5_accounts SET {assignments} WHERE id=?", params)
        conn.commit()


def load_accounts() -> list[sqlite3.Row]:
    with connect_db() as conn:
        return conn.execute(
            """
            SELECT mt5_accounts.*, licenses.allowed_ip AS license_allowed_ip
            FROM mt5_accounts
            LEFT JOIN licenses ON mt5_accounts.license_key = licenses.license_key
            ORDER BY mt5_accounts.id ASC
            """
        ).fetchall()


def bool_text(value: object) -> str:
    return "true" if bool(value) else "false"


def session_for_mode(symbol_mode: str) -> str:
    return "00:00-23:59"


def build_bot_env(account: sqlite3.Row) -> dict[str, str]:
    if not account["license_key"]:
        raise ValueError("Tài khoản MT5 chưa gắn license")

    password = decrypt_secret(account["mt_password_encrypted"])
    env = os.environ.copy()
    env.update(
        {
            "PYTHONUNBUFFERED": "1",
            "SERVER_URL": SERVER_URL,
            "LICENSE_KEY": account["license_key"],
            "MT_ACCOUNT": str(account["mt_login"]),
            "MT5_LOGIN": str(account["mt_login"]),
            "MT5_PASSWORD": password,
            "MT5_SERVER": account["mt_server"],
            "SYMBOLS": account["symbols"],
            "TIMEFRAME": account["timeframe"] or "M1",
            "ENSEMBLE_TIMEFRAMES": os.getenv("ENSEMBLE_TIMEFRAMES", "M1"),
            "MIN_ENSEMBLE_AGREEMENT": os.getenv("MIN_ENSEMBLE_AGREEMENT", "1"),
            "STRATEGY": os.getenv("STRATEGY", "scalping"),
            "BARS": os.getenv("BARS", "120"),
            "LOT_SIZE": str(account["lot_size"]),
            "LOT_MIN_SIZE": os.getenv("LOT_MIN_SIZE", "0"),
            "LOT_MAX_SIZE": os.getenv("LOT_MAX_SIZE", "0"),
            "LOT_STEP_SIZE": os.getenv("LOT_STEP_SIZE", "0"),
            "MAX_SPREAD_POINTS": str(account["max_spread_points"]),
            "MAX_POSITIONS_PER_SYMBOL": str(account["max_positions"]),
            "MAX_TOTAL_POSITIONS": str(account["max_total_positions"]),
            "DRY_RUN": bool_text(account["dry_run"]),
            "LOOP_SECONDS": os.getenv("LOOP_SECONDS", "1"),
            "COMMAND_POLL_SECONDS": os.getenv("COMMAND_POLL_SECONDS", "2"),
            "TRADE_SESSION_ENABLED": os.getenv("TRADE_SESSION_ENABLED", "true"),
            "TRADE_SESSIONS_UTC": os.getenv("TRADE_SESSIONS_UTC", session_for_mode(account["symbol_mode"])),
            "ONE_TRADE_PER_BAR": os.getenv("ONE_TRADE_PER_BAR", "false"),
            "REENTRY_COOLDOWN_SECONDS": os.getenv("REENTRY_COOLDOWN_SECONDS", "0"),
            "MIN_CONFIDENCE": os.getenv("MIN_CONFIDENCE", "0.55"),
            "MIN_WIN_PROBABILITY": os.getenv("MIN_WIN_PROBABILITY", "0.53"),
            "MAX_SIGNAL_RISK": os.getenv("MAX_SIGNAL_RISK", "0.55"),
            "MAX_SPREAD_ATR_RATIO": os.getenv("MAX_SPREAD_ATR_RATIO", "0.18"),
            "MIN_TP_SPREAD_RATIO": os.getenv("MIN_TP_SPREAD_RATIO", "2.50"),
            "ORDERS_PER_SIGNAL": os.getenv("ORDERS_PER_SIGNAL", "1"),
            "BATCH_MIN_CONFIDENCE": os.getenv("BATCH_MIN_CONFIDENCE", "0.68"),
            "FORCE_BOTH_SIDES": os.getenv("FORCE_BOTH_SIDES", "false"),
            "FORCE_ALTERNATE_SIDES": os.getenv("FORCE_ALTERNATE_SIDES", "true"),
            "FORCE_ENTRY_CONFIDENCE": os.getenv("FORCE_ENTRY_CONFIDENCE", "0.70"),
            "TREND_FILTER_ENABLED": os.getenv("TREND_FILTER_ENABLED", "true"),
            "ALLOW_HEDGING": os.getenv("ALLOW_HEDGING", "true"),
            "HEDGE_REBALANCE_ENABLED": os.getenv("HEDGE_REBALANCE_ENABLED", "true"),
            "HEDGE_REBALANCE_BYPASS_RISK": os.getenv("HEDGE_REBALANCE_BYPASS_RISK", "true"),
            "MIN_ORDER_SPACING_SECONDS": os.getenv("MIN_ORDER_SPACING_SECONDS", "0"),
            "BATCH_FIXED_LOT": os.getenv("BATCH_FIXED_LOT", "true"),
            "PYRAMID_LOT_MULTIPLIER": os.getenv("PYRAMID_LOT_MULTIPLIER", "1.00"),
            "TREND_LOT_MULTIPLIER": os.getenv("TREND_LOT_MULTIPLIER", "1.00"),
            "SIDEWAY_LOT_MULTIPLIER": os.getenv("SIDEWAY_LOT_MULTIPLIER", "1.00"),
            "COUNTER_TREND_LOT_MULTIPLIER": os.getenv("COUNTER_TREND_LOT_MULTIPLIER", "0.50"),
            "MAX_EQUITY_DRAWDOWN_PERCENT": os.getenv("MAX_EQUITY_DRAWDOWN_PERCENT", "4"),
            "MAX_DAILY_LOSS_PERCENT": os.getenv("MAX_DAILY_LOSS_PERCENT", "3"),
            "MAX_SYMBOL_FLOATING_LOSS": os.getenv("MAX_SYMBOL_FLOATING_LOSS", "40"),
            "CLOSE_ON_REVERSE": os.getenv("CLOSE_ON_REVERSE", "false"),
            "MAX_HOLD_SECONDS": os.getenv("MAX_HOLD_SECONDS", "600"),
            "CLOSE_WINNERS_ENABLED": os.getenv("CLOSE_WINNERS_ENABLED", "true"),
            "WINNER_MIN_PROFIT_MONEY": os.getenv("WINNER_MIN_PROFIT_MONEY", "3.00"),
            "WINNER_MAX_PROFIT_MONEY": os.getenv("WINNER_MAX_PROFIT_MONEY", "8.00"),
            "WINNER_MIN_PROFIT_POINTS": os.getenv("WINNER_MIN_PROFIT_POINTS", "0"),
            "CLOSE_LOSERS_ENABLED": os.getenv("CLOSE_LOSERS_ENABLED", "true"),
            "LOSER_MAX_LOSS_MONEY": os.getenv("LOSER_MAX_LOSS_MONEY", "40.00"),
            "LOSER_MAX_LOSS_POINTS": os.getenv("LOSER_MAX_LOSS_POINTS", "0"),
            "BASKET_CLOSE_ENABLED": os.getenv("BASKET_CLOSE_ENABLED", "true"),
            "BASKET_MIN_NET_PROFIT_MONEY": os.getenv("BASKET_MIN_NET_PROFIT_MONEY", "50.00"),
            "BASKET_MAX_NET_LOSS_MONEY": os.getenv("BASKET_MAX_NET_LOSS_MONEY", "40.00"),
            "BASKET_PROFIT_LOSS_RATIO": os.getenv("BASKET_PROFIT_LOSS_RATIO", "0"),
            "NEWS_FILTER_ENABLED": os.getenv("NEWS_FILTER_ENABLED", "false"),
            "NEWS_FAIL_CLOSED": os.getenv("NEWS_FAIL_CLOSED", "false"),
            "MAGIC": str(260501 + int(account["id"])),
        }
    )
    if os.getenv("MT5_PATH"):
        env["MT5_PATH"] = os.getenv("MT5_PATH", "")
    return env


def running_account_ids(except_account_id: int | None = None) -> list[int]:
    return [
        account_id
        for account_id, managed in processes.items()
        if account_id != except_account_id and managed.process.poll() is None
    ]


def block_shared_terminal_start(account_id: int, running_ids: list[int]) -> None:
    running_text = ", ".join(f"#{item}" for item in running_ids)
    message = (
        "Không thể chạy nhiều tài khoản MT5 trên cùng một terminal. "
        f"Account đang chạy: {running_text}. Cài terminal MT5 riêng cho account này "
        "hoặc dừng account đang chạy trước khi bật account khác."
    )
    update_account(account_id, is_active=0, run_status="error", last_error=message)
    print(f"[RUNNER] Blocked account #{account_id}: {message}")


def block_remote_license_start(account: sqlite3.Row) -> bool:
    allowed_ip = str(account["license_allowed_ip"] or "").strip()
    if not is_remote_license_account(account):
        return False

    account_id = int(account["id"])
    message = (
        f"License lock IP {allowed_ip}; tài khoản này phải chạy trên máy khách IP đó, "
        "không chạy bằng hosted runner localhost."
    )
    update_account(account_id, is_active=1, run_status="waiting_client", last_error=message)
    print(f"[RUNNER] Skipped remote account #{account_id}: {message}")
    return True


def is_remote_license_account(account: sqlite3.Row) -> bool:
    allowed_ip = str(account["license_allowed_ip"] or "").strip()
    return bool(allowed_ip and allowed_ip not in LOCAL_RUNNER_ALLOWED_IPS)


def start_bot(account: sqlite3.Row) -> None:
    account_id = int(account["id"])
    if account_id in processes and processes[account_id].process.poll() is None:
        return

    try:
        if block_remote_license_start(account):
            return

        if SINGLE_TERMINAL_MODE:
            running_ids = running_account_ids(except_account_id=account_id)
            if running_ids:
                block_shared_terminal_start(account_id, running_ids)
                return

        env = build_bot_env(account)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / f"hosted_mt5_account_{account_id}.log"
        log_file = open(log_path, "a", encoding="utf-8")
        log_file.write(f"\n[{utc_now_text()}] START account={account_id} login={account['mt_login']} symbols={account['symbols']}\n")
        log_file.flush()
        process = subprocess.Popen(
            [BOT_PYTHON, "mt5_ai_bot.py"],
            cwd=str(BOT_DIR),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        processes[account_id] = ManagedProcess(account_id=account_id, process=process, log_file=log_file)
        update_account(account_id, run_status="running", is_active=1, last_error=None, last_started_at=utc_now_text())
        print(f"[RUNNER] Started account #{account_id} pid={process.pid} log={log_path}")
    except Exception as exc:
        update_account(account_id, run_status="error", last_error=str(exc))
        print(f"[RUNNER] Start failed account #{account_id}: {exc}")


def stop_bot(account_id: int, reason: str = "stop") -> None:
    managed = processes.pop(account_id, None)
    if not managed:
        update_account(account_id, run_status="stopped", last_stopped_at=utc_now_text())
        return

    print(f"[RUNNER] Stopping account #{account_id} | {reason}")
    managed.process.terminate()
    try:
        managed.process.wait(timeout=12)
    except subprocess.TimeoutExpired:
        managed.process.kill()
        managed.process.wait(timeout=5)
    managed.log_file.write(f"[{utc_now_text()}] STOP account={account_id} reason={reason}\n")
    managed.log_file.close()
    update_account(account_id, run_status="stopped", last_stopped_at=utc_now_text())


def reconcile() -> None:
    accounts = load_accounts()
    known_ids = {int(account["id"]) for account in accounts}
    exited_ids: set[int] = set()

    for account_id, managed in list(processes.items()):
        return_code = managed.process.poll()
        if return_code is None:
            continue
        exited_ids.add(account_id)
        managed.log_file.write(f"[{utc_now_text()}] EXIT account={account_id} code={return_code}\n")
        managed.log_file.close()
        processes.pop(account_id, None)
        update_account(
            account_id,
            is_active=0,
            run_status="error" if return_code else "stopped",
            last_error=None if return_code == 0 else f"Bot exited with code {return_code}",
            last_stopped_at=utc_now_text(),
        )

    for account_id in list(processes):
        if account_id not in known_ids:
            stop_bot(account_id, "account deleted")

    for account in accounts:
        account_id = int(account["id"])
        if account_id in exited_ids:
            continue
        if is_remote_license_account(account):
            running = account_id in processes and processes[account_id].process.poll() is None
            if running:
                stop_bot(account_id, "remote license must run on customer machine")
            continue
        status = account["run_status"] or "stopped"
        active = bool(account["is_active"])
        running = account_id in processes and processes[account_id].process.poll() is None

        if not active or status in {"pending_stop", "stopped"}:
            if running:
                stop_bot(account_id, "disabled from web")
            elif status == "pending_stop":
                update_account(account_id, run_status="stopped", last_stopped_at=utc_now_text())
            continue

        if status == "pending_restart":
            if running:
                stop_bot(account_id, "restart from web")
            start_bot(account)
            continue

        if active and status in {"pending_start", "running"} and not running:
            start_bot(account)


def main() -> None:
    print(f"[RUNNER] Hosted MT5 runner started | db={DB_PATH} server={SERVER_URL} poll={POLL_SECONDS}s")
    try:
        while True:
            try:
                reconcile()
            except Exception as exc:
                print(f"[RUNNER] reconcile error: {exc}")
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("[RUNNER] Stopping all managed bots...")
    finally:
        for account_id in list(processes):
            stop_bot(account_id, "runner shutdown")


if __name__ == "__main__":
    main()
