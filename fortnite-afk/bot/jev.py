"""TypeSafe Jev client for the System One endpoint (OpenRouter or TypeSafe direct).

Pure standard library: urllib + json. No requests, no SDK, nothing to install.
"""
from __future__ import annotations

import http.client
import json
import logging
import random
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .capture import Frame
from .config import Config, ConfigError, resolve_api_key
from .geometry import Box, parse_box

log = logging.getLogger(__name__)

SYSTEM_TEXT = (
    "This is a screenshot of the video game Fortnite. "
    "The interface may be in English or Chinese. "
    "Coordinates are fractions of the image, measured from its top-left corner."
)

USER_AGENT = "fortnite-afk/1.0 (Windows; +https://localhost)"


class JevError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class TransportError(RuntimeError):
    pass


@dataclass
class Observation:
    screen: str
    screen_confidence: float
    screen_probabilities: dict[str, float]
    answers: dict[str, dict[str, Any]]
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    # Wall-clock breakdown of this call, in milliseconds. The whole point of the
    # bot's reaction time is here: encode (PNG+base64), http (network+model),
    # total (encode to parsed answer).
    timings: dict[str, float] = field(default_factory=dict)

    def choice(self, name: str) -> tuple[str | None, float]:
        answer = self.answers.get(name) or {}
        if answer.get("type") != "choice":
            return None, 0.0
        return answer.get("choice"), float(answer.get("confidence") or 0.0)

    def noul(self, name: str) -> float | None:
        answer = self.answers.get(name) or {}
        if answer.get("type") != "noul":
            return None
        try:
            return float(answer["noul"])
        except (KeyError, TypeError, ValueError):
            return None

    def raw_box(self, name: str) -> tuple[Box | None, float]:
        answer = self.answers.get(name) or {}
        if answer.get("type") != "box":
            return None, 0.0
        box = parse_box(answer.get("box"))
        try:
            conf = float(answer.get("confidence"))
        except (TypeError, ValueError):
            conf = float("nan")  # null / missing
        return box, conf

    def usable_box(
        self,
        name: str,
        *,
        min_confidence: float,
        min_presence: float = 0.5,
        allow_null: bool = True,
        null_value: float = 0.5,
        max_side: float = 0.92,
    ) -> Box | None:
        """Return a clickable box, or None with a logged reason.

        Box questions cannot answer "not found", so every button box has a
        companion `<name>_visible` Noul in our question sets. A low Noul or a
        low Box confidence rejects the answer instead of clicking blind.
        """
        box, conf = self.raw_box(name)
        if box is None:
            log.info("box %-24s rejected: no/invalid box answer", name)
            return None
        if conf != conf:  # NaN = confidence was null
            if not allow_null:
                log.info("box %-24s rejected: null confidence", name)
                return None
            effective = null_value
        else:
            effective = conf
        if effective < min_confidence:
            log.info("box %-24s rejected: confidence %.2f < %.2f", name, effective, min_confidence)
            return None
        presence = self.noul(f"{name}_visible")
        if presence is not None and presence < min_presence:
            log.info("box %-24s rejected: presence %.2f < %.2f", name, presence, min_presence)
            return None
        if max(box.width, box.height) > max_side:
            log.info("box %-24s rejected: covers %.0f%% of the frame", name,
                     max(box.width, box.height) * 100)
            return None
        return box


def detect_proxy(cfg: Config) -> str | None:
    value = (cfg.proxy or "auto").strip()
    if value.lower() in ("", "none", "off", "direct"):
        return None
    if value.lower() != "auto":
        return value
    try:
        with socket.create_connection(("127.0.0.1", 7890), timeout=0.25):
            return "http://127.0.0.1:7890"
    except OSError:
        return None


def post_json(url: str, headers: dict[str, str], payload: dict[str, Any],
              proxy: str | None, timeout: float) -> tuple[int, str]:
    """POST JSON and return (status, body). HTTP error statuses are returned, not raised."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {"User-Agent": USER_AGENT, **headers}
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    handlers = [urllib.request.ProxyHandler(
        {"http": proxy, "https": proxy} if proxy else {}
    )]
    opener = urllib.request.build_opener(*handlers)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise TransportError(str(reason)) from exc


class _KeepAlive:
    """One persistent HTTPS connection, reused across Jev calls.

    A fresh `urllib` request pays DNS + TCP + TLS on every frame; through a
    local proxy that is pure overhead. The System One endpoint is HTTP/1.1 and
    keeps the socket open, so reusing it removes the handshake from the hot
    path. If the peer closes the socket anyway (idle timeout, proxy restart),
    `post` reconnects once and replays the request.
    """

    def __init__(self, url: str, proxy: str | None, timeout: float) -> None:
        parts = urllib.parse.urlsplit(url)
        self.scheme = parts.scheme or "https"
        self.host = parts.hostname or ""
        self.port = parts.port or (443 if self.scheme == "https" else 80)
        self.path = parts.path or "/"
        if parts.query:
            self.path += "?" + parts.query
        self.proxy = proxy
        self.timeout = timeout
        # One SSLContext lets OpenSSL resume a TLS session even when the socket
        # has to be rebuilt, which is still cheaper than a full handshake.
        self.ssl_context = ssl.create_default_context()
        self.conn: http.client.HTTPConnection | None = None
        # One socket carries one request at a time. The session loop keeps
        # several requests in flight and can also reuse a client from the main
        # thread when a stale answer is discarded, so the socket is serialized
        # here instead of relying on callers never overlapping.
        self._lock = threading.RLock()

    def _connect(self) -> http.client.HTTPConnection:
        if self.scheme == "https":
            if self.proxy:
                p = urllib.parse.urlsplit(self.proxy)
                conn = http.client.HTTPSConnection(
                    p.hostname or "127.0.0.1", p.port or 3128,
                    timeout=self.timeout, context=self.ssl_context)
                conn.set_tunnel(self.host, self.port)
                return conn
            return http.client.HTTPSConnection(
                self.host, self.port, timeout=self.timeout, context=self.ssl_context)
        if self.proxy:
            p = urllib.parse.urlsplit(self.proxy)
            return http.client.HTTPConnection(
                p.hostname or "127.0.0.1", p.port or 3128, timeout=self.timeout)
        return http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)

    def close(self) -> None:
        with self._lock:
            if self.conn is not None:
                try:
                    self.conn.close()
                except Exception:  # noqa: BLE001 - closing must never raise
                    pass
                self.conn = None

    def post(self, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
        with self._lock:
            return self._post_locked(body, headers)

    def _post_locked(self, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
        last: Exception | None = None
        for _attempt in (1, 2):
            reused = self.conn is not None
            if self.conn is None:
                self.conn = self._connect()
            try:
                self.conn.request("POST", self.path, body=body, headers=headers)
                response = self.conn.getresponse()
                data = response.read()
                if response.will_close:
                    self.close()
                return response.status, data.decode("utf-8", "replace")
            except (http.client.HTTPException, OSError) as exc:
                last = exc
                self.close()
                if not reused:
                    break  # a fresh connection failed: replaying will not help
                log.debug("keep-alive socket was stale (%s); reconnecting", exc)
        raise TransportError(str(last) if last else "keep-alive request failed")


class JevClient:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.api_key = resolve_api_key(cfg)
        self.proxy_url = detect_proxy(cfg)
        self.total_cost = 0.0
        self.calls = 0
        self.rng = random.Random()
        self.last_http_ms = 0.0
        self.last_encode_ms = 0.0
        # Keep-alive socket, so the TLS handshake is paid once per run instead
        # of once per decision. Reset automatically if the endpoint changes.
        self._keepalive: _KeepAlive | None = None
        self._keepalive_key: tuple[str, str | None] | None = None
        # Benchmarks flip this off to measure the cost of a fresh TLS handshake.
        self.use_keepalive = True

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "TypeSafe-Danger-Zone-Images": "true",
            "HTTP-Referer": "https://localhost/fortnite-afk",
            "X-Title": "fortnite-afk",
        }

    def _body(self, frame: Frame, questions: dict[str, Any]) -> dict[str, Any]:
        b64 = frame.png_base64()
        if self.cfg.backend == "typesafe":
            asset_id = "screenshot"
            return {
                "model": self.cfg.model,
                "state": {asset_id: asset_id},
                "assets": {
                    asset_id: {"type": "image", "format": "png", "data_base64": b64},
                },
                "questions": questions,
            }
        return {
            "model": self.cfg.model,
            "state": [
                {"type": "text", "text": SYSTEM_TEXT},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
            ],
            "questions": questions,
        }

    def ask(self, frame: Frame, questions: dict[str, Any], *, context: str = "") -> Observation:
        started = time.monotonic()
        body = self._body(frame, questions)
        return self._finish(body, questions, started, context)

    def ask_pair(self, before: Frame, after: Frame, questions: dict[str, Any],
                 *, context: str = "") -> Observation:
        """Two frames in one call: what changed between them.

        Sensitivity is about the relationship between a mouse delta and the
        resulting camera angle, and that relationship only exists across two
        frames. Showing the model both - labelled BEFORE and AFTER - lets it
        judge "barely moved / about right / way too far" directly, instead of
        the code guessing from a single image.
        """
        started = time.monotonic()
        state: list[dict[str, Any]] = [
            {"type": "text", "text": SYSTEM_TEXT},
            {"type": "text", "text": "BEFORE the mouse movement:"},
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64," + before.png_base64()}},
            {"type": "text", "text": "AFTER the mouse movement:"},
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64," + after.png_base64()}},
        ]
        body = {"model": self.cfg.model, "state": state, "questions": questions}
        return self._finish(body, questions, started, context)

    def _finish(self, body: dict[str, Any], questions: dict[str, Any],
                started: float, context: str) -> Observation:
        encode_ms = (time.monotonic() - started) * 1000.0
        if context and isinstance(body["state"], list):
            body["state"].append({"type": "text", "text": context})
        data = self._post(body)
        answers = data.get("answers")
        if not isinstance(answers, dict) or not answers:
            raise JevError(f"Jev returned no answers: {str(data)[:300]}")
        screen, screen_conf = self._read_screen(answers)
        usage = data.get("usage") or {}
        cost = usage.get("cost")
        if isinstance(cost, (int, float)):
            self.total_cost += float(cost)
        self.calls += 1
        total_ms = (time.monotonic() - started) * 1000.0
        self.last_encode_ms = encode_ms
        log.info(
            "Jev #%d screen=%s(%.2f) tokens=%s/%s cost=%s total=$%.4f "
            "| encode=%.0fms http=%.0fms total=%.0fms",
            self.calls, screen, screen_conf, usage.get("input_tokens"),
            usage.get("output_tokens"), cost, self.total_cost,
            encode_ms, self.last_http_ms, total_ms,
        )
        return Observation(
            screen=screen,
            screen_confidence=screen_conf,
            screen_probabilities=(answers.get("screen") or {}).get("probabilities") or {},
            answers=answers,
            model=data.get("model", ""),
            usage=usage,
            timings={"encode_ms": round(encode_ms, 1),
                     "http_ms": round(self.last_http_ms, 1),
                     "total_ms": round(total_ms, 1)},
        )

    @staticmethod
    def _read_screen(answers: dict[str, Any]) -> tuple[str, float]:
        answer = answers.get("screen") or {}
        if answer.get("type") != "choice":
            return "unknown", 0.0
        return str(answer.get("choice") or "unknown"), float(answer.get("confidence") or 0.0)

    def _send(self, raw: bytes, body: dict[str, Any],
              proxy: str | None) -> tuple[int, str]:
        """Preferred path: the reused socket. Fallback: a clean urllib request."""
        key = (self.cfg.api_url, proxy)
        if not self.use_keepalive:
            return post_json(self.cfg.api_url, self._headers(), body, proxy,
                             self.cfg.request_timeout_s)
        if self._keepalive is None or self._keepalive_key != key:
            self._keepalive = _KeepAlive(self.cfg.api_url, proxy, self.cfg.request_timeout_s)
            self._keepalive_key = key
        try:
            return self._keepalive.post(raw, self._headers())
        except TransportError:
            # Reset so the next attempt starts from a known-good socket; the
            # urllib fallback below also covers proxies that dislike reuse.
            self._keepalive = None
            self._keepalive_key = None
            return post_json(self.cfg.api_url, self._headers(), body, proxy,
                             self.cfg.request_timeout_s)

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        cfg = self.cfg
        proxy = self.proxy_url
        last_error: Exception | None = None
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        for attempt in range(1, cfg.max_retries + 1):
            started = time.monotonic()
            try:
                status, text = self._send(raw, body, proxy)
            except TransportError as exc:
                last_error = exc
                if proxy is not None:
                    log.warning("Jev transport error via proxy (%s); retrying direct", exc)
                    proxy = None
                    continue
                log.warning("Jev transport error (attempt %d/%d): %s",
                            attempt, cfg.max_retries, exc)
                self._sleep_backoff(attempt)
                continue

            self.last_http_ms = (time.monotonic() - started) * 1000.0
            if status == 200:
                try:
                    data = json.loads(text)
                except ValueError as exc:
                    raise JevError(f"Jev returned non-JSON (HTTP 200): {text[:200]}") from exc
                if not isinstance(data, dict) or data.get("error"):
                    raise JevError(f"Jev error response: {str(data)[:300]}")
                log.debug("Jev HTTP 200 in %.2fs", self.last_http_ms / 1000.0)
                return data

            if status in (400, 401, 402, 403, 404, 422):
                hint = ""
                if status == 401:
                    hint = " (check OPENROUTER_API_KEY / api_key_file)"
                elif status == 402:
                    hint = " (OpenRouter credit exhausted)"
                raise JevError(f"Jev HTTP {status}{hint}: {text[:500]}", status)
            if status == 429 or status >= 500:
                last_error = JevError(f"HTTP {status}: {text[:500]}", status)
                log.warning("Jev HTTP %d (attempt %d/%d); backing off",
                            status, attempt, cfg.max_retries)
                self._sleep_backoff(attempt)
                continue
            raise JevError(f"Jev HTTP {status}: {text[:500]}", status)
        raise JevError(f"Jev request failed after {cfg.max_retries} attempts: {last_error}")

    def _sleep_backoff(self, attempt: int) -> None:
        time.sleep(min(20.0, (1.6 ** attempt)) + self.rng.uniform(0.0, 0.6))

    def close(self) -> None:
        if self._keepalive is not None:
            self._keepalive.close()
            self._keepalive = None


def check_api(cfg: Config) -> tuple[bool, str]:
    """Tiny text-only call used by `doctor`; verifies key, model and network."""
    try:
        key = resolve_api_key(cfg)
    except ConfigError as exc:
        return False, str(exc)
    proxy = detect_proxy(cfg)
    body = {
        "model": cfg.model,
        "state": "The sky is blue.",
        "questions": {"blue": {"type": "noul", "instructions": "Is the sky described as blue?"}},
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "User-Agent": USER_AGENT}
    try:
        status, text = post_json(cfg.api_url, headers, body, proxy, cfg.request_timeout_s)
    except TransportError as exc:
        return False, f"network error: {exc}"
    if status != 200:
        return False, f"HTTP {status}: {text[:300]}"
    try:
        value = json.loads(text)["answers"]["blue"]["noul"]
    except Exception:
        return False, f"unexpected response: {text[:300]}"
    return True, f"model={cfg.model} noul={value:.2f} proxy={proxy or 'direct'}"
