"""
Bot License Client (Python)
Dùng trong bot Python hoặc làm bridge cho bot C++ gọi qua subprocess

C++ bot có thể:
  1. Gọi file này qua Python subprocess
  2. Hoặc bạn tự viết HTTP client tương tự trong C++ (libcurl)
"""

import httpx
import time
import threading
import sys
import os
from datetime import datetime


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class LicenseClient:
    """
    Client kết nối với License Server.
    Bot phải khởi tạo client này đầu tiên trước khi giao dịch.
    """

    def __init__(self, server_url: str, license_key: str, mt_account: str = None):
        self.server_url  = server_url.rstrip("/")
        self.license_key = license_key
        self.mt_account  = mt_account
        self.bot_token   = None
        self.hosted_runner_internal = env_bool("HOSTED_RUNNER_INTERNAL")
        self._ping_thread = None
        self._running    = False

    def verify(self) -> bool:
        """
        Xác thực license lần đầu.
        Trả về True nếu hợp lệ, thoát chương trình nếu không.
        """
        try:
            response = httpx.post(
                f"{self.server_url}/bot/verify",
                json={
                    "license_key": self.license_key,
                    "mt_account": self.mt_account,
                    "hosted_runner": self.hosted_runner_internal,
                },
                timeout=10,
            )
            data = response.json()

            if response.status_code == 200 and data.get("status") == "ok":
                self.bot_token = data["bot_token"]
                print(f"[LICENSE] ✅ Xác thực thành công | User: {data['user']} | IP: {data['ip_locked']}")
                print(f"[LICENSE] Token hết hạn sau {data['token_expires_hours']} giờ")
                return True
            else:
                print(f"[LICENSE] ❌ Từ chối: {data.get('detail', 'Unknown error')}")
                sys.exit(1)

        except httpx.ConnectError:
            print("[LICENSE] ❌ Không kết nối được License Server. Kiểm tra mạng/server.")
            sys.exit(1)
        except Exception as e:
            print(f"[LICENSE] ❌ Lỗi xác thực: {e}")
            sys.exit(1)

    def start_ping(self, interval_seconds: int = 300):
        """Bắt đầu ping định kỳ trong background thread"""
        self._running = True
        self._ping_thread = threading.Thread(
            target=self._ping_loop,
            args=(interval_seconds,),
            daemon=True,
            name="LicensePing",
        )
        self._ping_thread.start()
        print(f"[LICENSE] Ping định kỳ mỗi {interval_seconds}s đã bắt đầu")

    def stop_ping(self):
        self._running = False

    def _ping_loop(self, interval: int):
        """Ping server định kỳ, cập nhật token"""
        fail_count = 0
        while self._running:
            time.sleep(interval)
            try:
                response = httpx.post(
                    f"{self.server_url}/bot/ping",
                    json={
                        "bot_token": self.bot_token,
                        "license_key": self.license_key,
                        "hosted_runner": self.hosted_runner_internal,
                    },
                    timeout=10,
                )
                if response.status_code == 200:
                    self.bot_token = response.json()["bot_token"]
                    fail_count = 0
                    print(f"[LICENSE] Ping OK {datetime.now().strftime('%H:%M:%S')}")
                else:
                    fail_count += 1
                    print(f"[LICENSE] ⚠️ Ping thất bại lần {fail_count}: {response.json().get('detail')}")
                    if fail_count >= 3:
                        print("[LICENSE] ❌ Ping thất bại 3 lần liên tiếp. Dừng bot.")
                        os._exit(1)
            except Exception as e:
                fail_count += 1
                print(f"[LICENSE] ⚠️ Lỗi ping: {e}")
                if fail_count >= 3:
                    print("[LICENSE] ❌ Mất kết nối server. Dừng bot.")
                    os._exit(1)

    def report_trade(self, ticket: str, symbol: str, direction: str,
                     entry_price: float, lot_size: float,
                     sl_price: float = None, tp_price: float = None,
                     status: str = "open", close_price: float = None,
                     profit: float = None, pips: float = None, note: str = None):
        """Báo cáo lệnh lên server (entry/close)"""
        if not self.bot_token:
            return
        try:
            httpx.post(
                f"{self.server_url}/bot/report-trade",
                json={
                    "bot_token": self.bot_token,
                    "license_key": self.license_key,
                    "ticket": ticket,
                    "symbol": symbol,
                    "direction": direction,
                    "entry_price": entry_price,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "lot_size": lot_size,
                    "status": status,
                    "close_price": close_price,
                    "profit": profit,
                    "pips": pips,
                    "note": note,
                },
                timeout=5,
            )
        except Exception as e:
            print(f"[LICENSE] Lỗi report trade: {e}")

    def sync_positions(self, positions: list[dict], mark_missing_closed: bool = True):
        """Đồng bộ snapshot position MT5 thật để server dọn trade log bị treo."""
        if not self.bot_token:
            return
        try:
            response = httpx.post(
                f"{self.server_url}/bot/sync-positions",
                json={
                    "bot_token": self.bot_token,
                    "license_key": self.license_key,
                    "mt_account": self.mt_account,
                    "positions": positions,
                    "mark_missing_closed": mark_missing_closed,
                },
                timeout=5,
            )
            if response.status_code != 200:
                print(f"[LICENSE] Sync positions failed: {response.json().get('detail', response.status_code)}")
        except Exception as e:
            print(f"[LICENSE] Lỗi sync positions: {e}")

    def report_status(self, **payload):
        """Gửi trạng thái tín hiệu/runtime mới nhất lên dashboard."""
        if not self.bot_token:
            return
        try:
            payload.setdefault("license_key", self.license_key)
            payload.setdefault("bot_token", self.bot_token)
            payload.setdefault("mt_account", self.mt_account)
            response = httpx.post(
                f"{self.server_url}/bot/status",
                json=payload,
                timeout=5,
            )
            if response.status_code != 200:
                print(f"[LICENSE] Runtime status failed: {response.json().get('detail', response.status_code)}")
        except Exception as e:
            print(f"[LICENSE] Lỗi report runtime status: {e}")

    def fetch_commands(self) -> list[dict]:
        """Lấy lệnh vận hành đang chờ từ admin dashboard."""
        if not self.bot_token:
            return []
        try:
            response = httpx.post(
                f"{self.server_url}/bot/commands",
                json={"bot_token": self.bot_token, "license_key": self.license_key},
                timeout=5,
            )
            if response.status_code != 200:
                print(f"[COMMAND] Poll failed: {response.json().get('detail', response.status_code)}")
                return []
            return response.json().get("commands", [])
        except Exception as e:
            print(f"[COMMAND] Poll error: {e}")
            return []

    def ack_command(self, command_id: int, status: str, result: str = None) -> None:
        """Báo kết quả xử lý command về server."""
        if not self.bot_token:
            return
        try:
            response = httpx.post(
                f"{self.server_url}/bot/commands/{command_id}/ack",
                json={
                    "bot_token": self.bot_token,
                    "license_key": self.license_key,
                    "status": status,
                    "result": result,
                },
                timeout=5,
            )
            if response.status_code != 200:
                print(f"[COMMAND] Ack failed #{command_id}: {response.json().get('detail', response.status_code)}")
        except Exception as e:
            print(f"[COMMAND] Ack error #{command_id}: {e}")


# ─── Ví dụ sử dụng ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 1. Khởi tạo client
    client = LicenseClient(
        server_url="http://your-server.com:8000",
        license_key="YOUR_LICENSE_KEY_HERE",
        mt_account="12345678",
    )

    # 2. Xác thực (sẽ tự exit nếu thất bại)
    client.verify()

    # 3. Bắt đầu ping định kỳ
    client.start_ping(interval_seconds=300)

    # 4. Bot hoạt động bình thường
    print("[BOT] Bot đang chạy...")

    # 5. Khi vào lệnh, báo cáo lên server
    client.report_trade(
        ticket="10001",
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.0852,
        sl_price=1.0820,
        tp_price=1.0920,
        lot_size=0.1,
        status="open",
    )

    # 6. Khi đóng lệnh
    client.report_trade(
        ticket="10001",
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.0852,
        lot_size=0.1,
        status="closed",
        close_price=1.0920,
        profit=68.0,
        pips=6.8,
    )

    # Giữ bot chạy
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        client.stop_ping()
        print("[BOT] Dừng bot.")
