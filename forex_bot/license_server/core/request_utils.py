from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Lấy IP thực của client khi chạy trực tiếp hoặc sau tunnel/proxy."""
    for header in ("CF-Connecting-IP", "X-Real-IP", "X-Forwarded-For"):
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
