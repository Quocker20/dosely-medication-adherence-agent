from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Extract the client IP, honoring the first forwarded address when present."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        first_forwarded = forwarded.split(",")[0].strip()
        if first_forwarded:
            return first_forwarded
    return request.client.host if request.client else "127.0.0.1"
