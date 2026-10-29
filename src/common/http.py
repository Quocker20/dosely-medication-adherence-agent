from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Return the TCP peer address of the request (SEC-04).

    Deliberately ignores the X-Forwarded-For header: any client can send it, so
    trusting it lets an attacker pick their own rate-limit key. Behind a reverse
    proxy, uvicorn (``--proxy-headers --forwarded-allow-ips=<proxy network>``)
    rewrites ``request.client`` from X-Forwarded-For *only* when the connection
    comes from a trusted proxy address, so ``request.client.host`` is already the
    real client there.
    """
    return request.client.host if request.client else "127.0.0.1"
