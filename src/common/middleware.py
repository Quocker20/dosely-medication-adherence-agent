import logging
import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.core.logging_config import request_id_var

logger = logging.getLogger(__name__)

# UUIDs fit this too. Anything else (control characters, spaces, long strings)
# could forge log lines or bloat logs, so it is replaced rather than echoed.
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9-]{1,64}")


def resolve_request_id(candidate: str | None) -> str:
    if candidate is not None and _REQUEST_ID_RE.fullmatch(candidate):
        return candidate
    return str(uuid.uuid4())


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = resolve_request_id(request.headers.get("X-Request-ID"))
        start_time = time.time()

        # The id rides on every log record through the contextvar + record factory.
        token = request_id_var.set(request_id)
        try:
            logger.info("Start request %s %s", request.method, request.url.path)

            response = await call_next(request)

            process_time = (time.time() - start_time) * 1000
            logger.info(
                "Completed %s %s Status: %s in %.2fms",
                request.method,
                request.url.path,
                response.status_code,
                process_time,
            )
        finally:
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-MS"] = f"{process_time:.2f}"
        return response
