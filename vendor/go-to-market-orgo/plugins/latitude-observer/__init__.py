"""Fail-open Hermes observer that exports bounded OTLP/HTTP traces to Latitude.

The default capture mode is metadata-only. ``sanitized`` includes conversation
and tool content only after Hermes secret-pattern redaction and truncation.
There is deliberately no raw/full mode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import logging
import os
import queue
import secrets
import socket
import threading
import time
from typing import Any
from urllib import error, parse, request


logger = logging.getLogger(__name__)
DEFAULT_ENDPOINT = "https://ingest.latitude.so/v1/traces"
MAX_FIELD_CHARS = 16_000
MAX_LIVE_TURNS = 256
MAX_QUEUE = 512
_LOCK = threading.Lock()
_TURNS: dict[str, "TurnState"] = {}
_REQUESTS: dict[str, "Span"] = {}
_TOOLS: dict[str, "Span"] = {}
_SUBAGENTS: dict[str, "Span"] = {}
_EXPORTER: "Exporter | None | bool" = None


def _now_ns() -> int:
    return time.time_ns()


def _capture_mode() -> str:
    mode = os.environ.get("LATITUDE_CAPTURE_MODE", "metadata").strip().lower()
    return mode if mode in {"metadata", "sanitized"} else "metadata"


def _redact(value: str) -> str:
    try:
        from agent.redact import redact_sensitive_text

        return redact_sensitive_text(value, force=True)
    except Exception:
        return "[content omitted: redaction unavailable]"


def _bounded(value: Any) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        text = repr(value)
    text = _redact(text)
    if len(text) > MAX_FIELD_CHARS:
        text = text[:MAX_FIELD_CHARS] + "…[truncated]"
    return text


def _content(value: Any) -> str | None:
    if _capture_mode() != "sanitized" or value is None:
        return None
    return _bounded(value)


def _safe_id(value: Any) -> str:
    if not value:
        return ""
    return hashlib.sha256(str(value).encode()).hexdigest()[:24]


def _profile(kwargs: dict[str, Any]) -> str:
    value = kwargs.get("profile") or kwargs.get("profile_name") or os.environ.get("HERMES_PROFILE")
    return str(value or "default")[:80]


def _attrs(values: dict[str, Any]) -> list[dict[str, Any]]:
    encoded: list[dict[str, Any]] = []
    for key, value in values.items():
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            item = {"boolValue": value}
        elif isinstance(value, int):
            item = {"intValue": str(value)}
        elif isinstance(value, float):
            item = {"doubleValue": value}
        else:
            item = {"stringValue": str(value)[:MAX_FIELD_CHARS]}
        encoded.append({"key": key, "value": item})
    return encoded


@dataclass
class Span:
    trace_id: str
    span_id: str
    name: str
    start_ns: int
    parent_span_id: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    def finish(self, *, status: str = "ok", extra: dict[str, Any] | None = None) -> dict[str, Any]:
        values = dict(self.attributes)
        if extra:
            values.update(extra)
        result: dict[str, Any] = {
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "name": self.name[:160],
            "kind": 1,
            "startTimeUnixNano": str(self.start_ns),
            "endTimeUnixNano": str(max(_now_ns(), self.start_ns + 1)),
            "attributes": _attrs(values),
            "status": {"code": 2 if status == "error" else 1},
        }
        if self.parent_span_id:
            result["parentSpanId"] = self.parent_span_id
        return result


@dataclass
class TurnState:
    key: str
    session_id: str
    root: Span
    touched_at: float = field(default_factory=time.monotonic)


class Exporter:
    def __init__(self, endpoint: str, api_key: str, project: str) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.project = project
        self.items: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=MAX_QUEUE)
        self.stopping = threading.Event()
        self.worker = threading.Thread(target=self._run, name="latitude-observer", daemon=True)
        self.worker.start()

    def submit(self, span: dict[str, Any]) -> None:
        try:
            self.items.put_nowait(span)
        except queue.Full:
            logger.warning("Latitude observer queue full; dropping one span")

    def _run(self) -> None:
        while not self.stopping.is_set():
            try:
                first = self.items.get(timeout=0.5)
            except queue.Empty:
                continue
            if first is None:
                break
            batch = [first]
            while len(batch) < 25:
                try:
                    item = self.items.get_nowait()
                except queue.Empty:
                    break
                if item is None:
                    self.stopping.set()
                    break
                batch.append(item)
            self._send(batch)

    def _send(self, spans: list[dict[str, Any]]) -> None:
        resource = {
            "service.name": os.environ.get("LATITUDE_SERVICE_NAME", "ai-guy-hermes"),
            "service.version": os.environ.get("AI_GUY_STACK_VERSION", "2026.09.13.1"),
            "service.instance.id": _safe_id(socket.gethostname()),
            "deployment.environment": os.environ.get("AI_GUY_ENVIRONMENT", "production"),
        }
        payload = {
            "resourceSpans": [{
                "resource": {"attributes": _attrs(resource)},
                "scopeSpans": [{
                    "scope": {"name": "ai-guy.latitude-observer", "version": "1.0.0"},
                    "spans": spans,
                }],
            }]
        }
        body = json.dumps(payload, separators=(",", ":")).encode()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Latitude-Project": self.project,
            "Content-Type": "application/json",
            "User-Agent": "ai-guy-latitude-observer/1.0",
        }
        for attempt in range(3):
            try:
                req = request.Request(self.endpoint, data=body, headers=headers, method="POST")
                with request.urlopen(req, timeout=8) as response:
                    if response.status == 202:
                        return
                    if response.status < 500 and response.status != 429:
                        return
            except error.HTTPError as exc:
                if exc.code < 500 and exc.code != 429:
                    return
            except Exception:
                pass
            time.sleep(0.5 * (2**attempt))

    def close(self) -> None:
        self.stopping.set()
        try:
            self.items.put_nowait(None)
        except queue.Full:
            pass
        self.worker.join(timeout=4)


def _endpoint() -> str | None:
    value = os.environ.get("LATITUDE_OTLP_ENDPOINT", DEFAULT_ENDPOINT).strip()
    parsed = parse.urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        logger.warning("Latitude observer rejected a non-HTTPS endpoint")
        return None
    return value


def _exporter() -> Exporter | None:
    global _EXPORTER
    if _EXPORTER is False:
        return None
    if isinstance(_EXPORTER, Exporter):
        return _EXPORTER
    with _LOCK:
        if isinstance(_EXPORTER, Exporter):
            return _EXPORTER
        api_key = os.environ.get("LATITUDE_API_KEY", "").strip()
        project = os.environ.get("LATITUDE_PROJECT_SLUG", "").strip()
        endpoint = _endpoint()
        if not api_key or not project or not endpoint:
            _EXPORTER = False
            return None
        _EXPORTER = Exporter(endpoint, api_key, project)
        return _EXPORTER


def _submit(span: dict[str, Any]) -> None:
    exporter = _exporter()
    if exporter:
        exporter.submit(span)


def _turn_key(kwargs: dict[str, Any]) -> str:
    return str(kwargs.get("turn_id") or kwargs.get("task_id") or kwargs.get("session_id") or "")


def _get_or_create_turn(kwargs: dict[str, Any]) -> TurnState | None:
    key = _turn_key(kwargs)
    if not key or _exporter() is None:
        return None
    evicted: dict[str, Any] | None = None
    with _LOCK:
        state = _TURNS.get(key)
        if state:
            state.touched_at = time.monotonic()
            return state
        if len(_TURNS) >= MAX_LIVE_TURNS:
            oldest = min(_TURNS.values(), key=lambda item: item.touched_at)
            evicted = oldest.root.finish(status="error", extra={"ai.guy.stop_reason": "state_evicted"})
            _TURNS.pop(oldest.key, None)
        trace_id = secrets.token_hex(16)
        session_id = str(kwargs.get("session_id") or "")
        root = Span(
            trace_id=trace_id,
            span_id=secrets.token_hex(8),
            name="hermes.agent.turn",
            start_ns=_now_ns(),
            attributes={
                "latitude.capture.name": "hermes-agent-turn",
                "latitude.tags": json.dumps(["ai-guy", "hermes", _profile(kwargs)]),
                "latitude.metadata": json.dumps({"platform": kwargs.get("platform", "unknown"), "profile": _profile(kwargs)}),
                "session.id": _safe_id(session_id),
                "user.id": _safe_id(kwargs.get("sender_id")),
                "agent.profile": _profile(kwargs),
                "agent.platform": kwargs.get("platform", "unknown"),
                "ai.guy.capture_mode": _capture_mode(),
            },
        )
        state = TurnState(key=key, session_id=session_id, root=root)
        _TURNS[key] = state
    if evicted:
        _submit(evicted)
    return state


def _finish_turn(kwargs: dict[str, Any], status: str = "ok") -> None:
    key = _turn_key(kwargs)
    with _LOCK:
        state = _TURNS.pop(key, None)
    if not state:
        return
    response = _content(kwargs.get("assistant_response"))
    extra = {"ai.guy.completed": status == "ok"}
    if response:
        extra["gen_ai.output.messages"] = response
    _submit(state.root.finish(status=status, extra=extra))


def on_pre_llm_call(**kwargs: Any) -> None:
    state = _get_or_create_turn(kwargs)
    if state:
        content = _content(kwargs.get("user_message"))
        if content:
            state.root.attributes["gen_ai.input.messages"] = content


def on_post_llm_call(**kwargs: Any) -> None:
    _finish_turn(kwargs)


def on_pre_api_request(**kwargs: Any) -> None:
    state = _get_or_create_turn(kwargs)
    request_id = str(kwargs.get("api_request_id") or "")
    if not state or not request_id:
        return
    attributes: dict[str, Any] = {
        "gen_ai.operation.name": "chat",
        "gen_ai.system": kwargs.get("provider", "unknown"),
        "gen_ai.request.model": kwargs.get("model", "unknown"),
        "gen_ai.usage.input_tokens": kwargs.get("approx_input_tokens"),
        "agent.profile": _profile(kwargs),
    }
    content = _content(kwargs.get("request"))
    if content:
        attributes["gen_ai.input.messages"] = content
    with _LOCK:
        _REQUESTS[request_id] = Span(
            trace_id=state.root.trace_id,
            span_id=secrets.token_hex(8),
            parent_span_id=state.root.span_id,
            name=f"chat {str(kwargs.get('model') or 'model')}",
            start_ns=_now_ns(),
            attributes=attributes,
        )


def _usage_attrs(usage: Any) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {}
    return {
        "gen_ai.usage.input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
        "gen_ai.usage.output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
    }


def on_post_api_request(**kwargs: Any) -> None:
    request_id = str(kwargs.get("api_request_id") or "")
    with _LOCK:
        span = _REQUESTS.pop(request_id, None)
    if not span:
        return
    extra = _usage_attrs(kwargs.get("usage"))
    extra.update({
        "gen_ai.response.model": kwargs.get("response_model"),
        "gen_ai.response.finish_reasons": kwargs.get("finish_reason"),
        "ai.guy.duration_seconds": kwargs.get("api_duration"),
    })
    content = _content(kwargs.get("response") or kwargs.get("assistant_message"))
    if content:
        extra["gen_ai.output.messages"] = content
    _submit(span.finish(extra=extra))


def on_api_request_error(**kwargs: Any) -> None:
    request_id = str(kwargs.get("api_request_id") or "")
    with _LOCK:
        span = _REQUESTS.pop(request_id, None)
    if not span:
        return
    _submit(span.finish(status="error", extra={
        "error.type": (kwargs.get("error") or {}).get("type") if isinstance(kwargs.get("error"), dict) else "provider_error",
        "http.response.status_code": kwargs.get("status_code"),
        "ai.guy.retryable": kwargs.get("retryable"),
    }))


def on_pre_tool_call(**kwargs: Any) -> None:
    state = _get_or_create_turn(kwargs)
    call_id = str(kwargs.get("tool_call_id") or "")
    if not state or not call_id:
        return
    attributes: dict[str, Any] = {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": kwargs.get("tool_name", "unknown"),
        "agent.profile": _profile(kwargs),
    }
    content = _content(kwargs.get("args"))
    if content:
        attributes["gen_ai.tool.call.arguments"] = content
    with _LOCK:
        _TOOLS[call_id] = Span(
            trace_id=state.root.trace_id,
            span_id=secrets.token_hex(8),
            parent_span_id=state.root.span_id,
            name=f"tool {str(kwargs.get('tool_name') or 'unknown')}",
            start_ns=_now_ns(),
            attributes=attributes,
        )


def on_post_tool_call(**kwargs: Any) -> None:
    call_id = str(kwargs.get("tool_call_id") or "")
    with _LOCK:
        span = _TOOLS.pop(call_id, None)
    if not span:
        return
    status = str(kwargs.get("status") or "ok")
    extra: dict[str, Any] = {
        "tool.status": status,
        "tool.duration_ms": kwargs.get("duration_ms"),
        "error.type": kwargs.get("error_type"),
    }
    content = _content(kwargs.get("result"))
    if content:
        extra["gen_ai.tool.call.result"] = content
    _submit(span.finish(status="error" if status in {"error", "blocked", "cancelled"} else "ok", extra=extra))


def on_pre_approval_request(**kwargs: Any) -> None:
    state = _get_or_create_turn(kwargs)
    if not state:
        return
    span = Span(
        trace_id=state.root.trace_id,
        span_id=secrets.token_hex(8),
        parent_span_id=state.root.span_id,
        name="approval.requested",
        start_ns=_now_ns(),
        attributes={"approval.surface": kwargs.get("surface"), "approval.pattern": kwargs.get("pattern_key")},
    )
    _submit(span.finish())


def on_post_approval_response(**kwargs: Any) -> None:
    state = _get_or_create_turn(kwargs)
    if not state:
        return
    choice = str(kwargs.get("choice") or "unknown")
    span = Span(
        trace_id=state.root.trace_id,
        span_id=secrets.token_hex(8),
        parent_span_id=state.root.span_id,
        name="approval.response",
        start_ns=_now_ns(),
        attributes={"approval.choice": choice, "approval.surface": kwargs.get("surface")},
    )
    _submit(span.finish(status="error" if choice in {"deny", "timeout"} else "ok"))


def on_subagent_start(**kwargs: Any) -> None:
    state = _get_or_create_turn(kwargs)
    child = str(kwargs.get("child_session_id") or "")
    if not state or not child:
        return
    with _LOCK:
        _SUBAGENTS[child] = Span(
            trace_id=state.root.trace_id,
            span_id=secrets.token_hex(8),
            parent_span_id=state.root.span_id,
            name=f"subagent {str(kwargs.get('child_role') or 'worker')}",
            start_ns=_now_ns(),
            attributes={"agent.role": kwargs.get("child_role"), "agent.child_session": _safe_id(child)},
        )


def on_subagent_stop(**kwargs: Any) -> None:
    child = str(kwargs.get("child_session_id") or "")
    with _LOCK:
        span = _SUBAGENTS.pop(child, None)
    if not span:
        return
    status = str(kwargs.get("child_status") or "ok")
    extra: dict[str, Any] = {"agent.status": status, "agent.duration_ms": kwargs.get("duration_ms")}
    content = _content(kwargs.get("child_summary"))
    if content:
        extra["agent.summary"] = content
    _submit(span.finish(status="error" if status in {"error", "failed"} else "ok", extra=extra))


def on_session_end(**kwargs: Any) -> None:
    if kwargs.get("completed") is False or kwargs.get("interrupted"):
        _finish_turn(kwargs, status="error")
    else:
        _finish_turn(kwargs)


def on_session_finalize(**kwargs: Any) -> None:
    session_id = str(kwargs.get("session_id") or "")
    with _LOCK:
        keys = [key for key, state in _TURNS.items() if not session_id or state.session_id == session_id]
    for key in keys:
        _finish_turn({"turn_id": key}, status="error" if kwargs.get("reason") == "shutdown" else "ok")
    if kwargs.get("reason") == "shutdown":
        global _EXPORTER
        exporter = _EXPORTER
        if isinstance(exporter, Exporter):
            exporter.close()
        _EXPORTER = False


def register(ctx: Any) -> None:
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("post_llm_call", on_post_llm_call)
    ctx.register_hook("pre_api_request", on_pre_api_request)
    ctx.register_hook("post_api_request", on_post_api_request)
    ctx.register_hook("api_request_error", on_api_request_error)
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    ctx.register_hook("post_tool_call", on_post_tool_call)
    ctx.register_hook("pre_approval_request", on_pre_approval_request)
    ctx.register_hook("post_approval_response", on_post_approval_response)
    ctx.register_hook("subagent_start", on_subagent_start)
    ctx.register_hook("subagent_stop", on_subagent_stop)
    ctx.register_hook("on_session_end", on_session_end)
    ctx.register_hook("on_session_finalize", on_session_finalize)
