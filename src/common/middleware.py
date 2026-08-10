import logging
import time
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start_time = time.time()

        logger.info(f"[{request_id}] Start request {request.method} {request.url.path}")

        response = await call_next(request)

        process_time = (time.time() - start_time) * 1000
        logger.info(
            f"[{request_id}] Completed {request.method} {request.url.path} "
            f"Status: {response.status_code} in {process_time:.2f}ms"
        )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-MS"] = f"{process_time:.2f}"
        return response
