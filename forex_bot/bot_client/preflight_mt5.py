"""Customer-side MT5 preflight check.

This script is intentionally small: it verifies the local MT5 terminal before
the trading bot starts, so customer support can see the exact failure in logs.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import MetaTrader5 as mt5


def build_initialize_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {}

    mt5_path = os.getenv("MT5_PATH", "").strip()
    if mt5_path:
        kwargs["path"] = mt5_path

    login_text = os.getenv("MT5_LOGIN", "").strip()
    if login_text:
        try:
            kwargs["login"] = int(login_text)
        except ValueError:
            print(f"[PREFLIGHT] MT5_LOGIN khong hop le: {login_text}")
            sys.exit(1)

    password = os.getenv("MT5_PASSWORD", "")
    if password:
        kwargs["password"] = password

    server = os.getenv("MT5_SERVER", "").strip()
    if server:
        kwargs["server"] = server

    return kwargs


def main() -> None:
    kwargs = build_initialize_kwargs()
    login_text = str(kwargs.get("login", "") or "terminal-current")
    server_text = str(kwargs.get("server", "") or "terminal-current")
    path_text = str(kwargs.get("path", "") or "auto")
    print(f"[PREFLIGHT] MT5 init | login={login_text} server={server_text} path={path_text}")

    initialized = mt5.initialize(**kwargs)
    if not initialized:
        print(f"[PREFLIGHT] MT5 initialize failed: {mt5.last_error()}")
        sys.exit(1)

    try:
        account = mt5.account_info()
        if account is None:
            print(f"[PREFLIGHT] MT5 account_info failed: {mt5.last_error()}")
            sys.exit(1)

        expected = (os.getenv("MT_ACCOUNT") or os.getenv("MT5_LOGIN") or "").strip()
        actual = str(account.login)
        if expected and actual != expected:
            print(f"[PREFLIGHT] Sai tai khoan MT5: dang login {actual}, can {expected}")
            sys.exit(1)

        print(
            f"[PREFLIGHT] MT5 OK | login={account.login} "
            f"server={account.server} balance={account.balance}"
        )

        symbols = [item.strip() for item in os.getenv("SYMBOLS", "").split(",") if item.strip()]
        for symbol in symbols:
            info = mt5.symbol_info(symbol)
            if info is None:
                print(f"[PREFLIGHT] Symbol khong ton tai trong MT5: {symbol}")
                sys.exit(1)
            if not info.visible and not mt5.symbol_select(symbol, True):
                print(f"[PREFLIGHT] Khong bat duoc symbol trong Market Watch: {symbol}")
                sys.exit(1)
            print(f"[PREFLIGHT] Symbol OK: {symbol}")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
