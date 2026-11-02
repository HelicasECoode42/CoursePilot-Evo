"""请求体大小上限（纯 ASGI 中间件）。

为什么需要：规划、建议对话、学业资料导入都接收 JSON 请求体，不设上限的话一个超大请求
会先被完整读进内存再被校验，等于让任何人都能用一次请求占满内存。

两道检查：
- 有 Content-Length 时，先看声明的长度，超了直接 413，不读请求体。
- 没有或声明不可信时（分块传输），边读边累计字节数，超过就中止读取并返回 413。

超限后不把任何部分请求体交给下游：下游一旦看到前半截合法 JSON 就可能执行副作用
（例如触发一次模型调用），所以用一个内部异常打断读取，由本中间件自己发 413。
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from agent_runtime.api.errors import payload_too_large_response


class _BodyTooLarge(Exception):
    """内部信号：读取请求体时超过上限。不会越过本模块。"""


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                parsed = int(value.decode("latin-1").strip())
            except ValueError:
                return None
            return parsed if parsed >= 0 else None
    return None


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _declared_length(scope)
        if declared is not None and declared > self.max_bytes:
            await self._reject(scope, receive, send)
            return

        seen = 0
        overflowed = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal seen, overflowed
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    overflowed = True
                    raise _BodyTooLarge()
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            # 超限后下游的任何回复都丢弃：FastAPI 会把读取异常包成 400「解析请求体失败」，
            # 那不是我们要的答复。413 由本中间件统一发出。
            if overflowed:
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLarge:
            pass
        # 读取阶段超限时下游还没有开始回复；若已经开始（实际不会发生），就不能再补发。
        if overflowed and not response_started:
            await self._reject(scope, receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = payload_too_large_response(Request(scope, receive))
        await response(scope, receive, send)
