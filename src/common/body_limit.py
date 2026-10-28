"""Request-body guard for the voice upload endpoint (SEC-08).

Starlette spools a multipart upload to disk before the route handler runs, so a
size check inside the handler alone cannot stop an unbounded body. This ASGI
middleware rejects an oversized body up front (Content-Length) or mid-stream
(chunked transfer with no Content-Length).
"""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.config import get_settings

VOICE_PATH_SUFFIX = "/chat/voice"
# Multipart framing and the small form fields (conversationId, clientDate, ...).
MULTIPART_OVERHEAD_BYTES = 64 * 1024


class _BodyTooLargeError(Exception):
    pass


def _too_large_response(limit: int) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={
            "success": False,
            "code": 413,
            "message": f"Audio upload exceeds the {limit // (1024 * 1024) or 1} MB limit",
            "data": None,
            "errors": None,
        },
    )


class VoiceBodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or not scope["path"].endswith(VOICE_PATH_SUFFIX):
            await self.app(scope, receive, send)
            return

        limit = get_settings().voice_max_upload_bytes
        max_body = limit + MULTIPART_OVERHEAD_BYTES
        headers = dict(scope["headers"])
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                too_big = int(declared) > max_body
            except ValueError:
                too_big = True
            if too_big:
                await _too_large_response(limit)(scope, receive, send)
                return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_body:
                    raise _BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLargeError:
            if not response_started:
                await _too_large_response(limit)(scope, receive, send)
