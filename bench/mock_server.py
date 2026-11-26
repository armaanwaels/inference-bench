"""A scripted stand-in for an inference engine, so tests run on CPU with no GPU and no network.

It speaks the part of the OpenAI completions API that the load generator and the correctness
client use. The output is not language. Each output token is a pure function of
(prompt, seed, position), so the same request always gets the same tokens, and a client that
compares outputs across runs has something exact to compare.

Standard library only. It listens on 127.0.0.1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_MODEL = "mock-model"
DEFAULT_MAX_TOKENS = 16
MAX_BODY_BYTES = 8 * 1024 * 1024

# Short common words. Every mock token is one of these with a leading space, so a test can
# count tokens by splitting the text.
VOCAB = (
    "time year people way day man thing woman life child world school state family student "
    "group country problem hand part place case week company system program question work "
    "number night point home water room mother area money story fact month lot right study "
    "book eye job word business issue side kind head house service friend father power hour"
).split()


class BadRequest(Exception):
    """The request body cannot be served. Becomes an HTTP 400 with this message."""


def generate_tokens(prompt: str, seed: int, count: int) -> list[str]:
    """The output tokens for a request. A pure function of (prompt, seed, position)."""
    tokens = []
    for position in range(count):
        digest = hashlib.sha256(f"{seed}\x00{position}\x00{prompt}".encode()).digest()
        tokens.append(" " + VOCAB[int.from_bytes(digest[:8], "big") % len(VOCAB)])
    return tokens


def count_prompt_tokens(prompt: str) -> int:
    """The mock's tokenizer: one token per whitespace-separated word."""
    return len(prompt.split())


def _integer(body: dict, key: str, default: int, minimum: int | None = None) -> int:
    value = body.get(key, default)
    # bool is a subclass of int in Python, and "max_tokens": true is not a number.
    if isinstance(value, bool) or not isinstance(value, int):
        raise BadRequest(f"{key} must be an integer")
    if minimum is not None and value < minimum:
        raise BadRequest(f"{key} must be at least {minimum}")
    return value


def complete(body: object, model: str = DEFAULT_MODEL) -> dict:
    """Build the response for one /v1/completions request body."""
    if not isinstance(body, dict):
        raise BadRequest("the request body must be a JSON object")
    if body.get("stream"):
        raise BadRequest("stream is not supported by this mock yet")
    if "prompt" not in body:
        raise BadRequest("prompt is required")
    prompt = body["prompt"]
    if isinstance(prompt, list):
        raise BadRequest("a list of prompts is not supported by this mock yet")
    if not isinstance(prompt, str):
        raise BadRequest("prompt must be a string")
    max_tokens = _integer(body, "max_tokens", DEFAULT_MAX_TOKENS, minimum=0)
    seed = _integer(body, "seed", 0)

    tokens = generate_tokens(prompt, seed, max_tokens)
    prompt_tokens = count_prompt_tokens(prompt)
    request_id = hashlib.sha256(f"{seed}\x00{max_tokens}\x00{prompt}".encode()).hexdigest()[:16]
    return {
        "id": f"cmpl-mock-{request_id}",
        "object": "text_completion",
        "created": int(time.time()),
        "model": body.get("model") or model,
        # The mock never stops early, like an engine run with ignore_eos.
        "choices": [{"index": 0, "text": "".join(tokens), "logprobs": None, "finish_reason": "length"}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": len(tokens),
            "total_tokens": prompt_tokens + len(tokens),
        },
    }


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002 - the name is set by the base class
        pass  # a test run should not print one line per request

    def _send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, status: int, message: str) -> None:
        self._send_json(status, {"error": {"message": message, "type": "mock_error", "code": status}})

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as error:
            raise BadRequest("Content-Length is not a number") from error
        if length < 0:
            raise BadRequest("Content-Length is negative")
        if length > MAX_BODY_BYTES:
            raise BadRequest("the request body is too large")
        return self.rfile.read(length)

    def do_GET(self):  # noqa: N802 - the name is set by the base class
        if self.path == "/v1/models":
            model = self.server.model
            self._send_json(200, {"object": "list", "data": [{"id": model, "object": "model", "owned_by": "mock"}]})
            return
        self._send_error(404, f"no such path: GET {self.path}")

    def do_POST(self):  # noqa: N802 - the name is set by the base class
        try:
            raw = self._read_body()
        except BadRequest as error:
            # The body was not read, so the connection cannot be reused.
            self.close_connection = True
            self._send_error(400, str(error))
            return
        if self.path != "/v1/completions":
            self._send_error(404, f"no such path: POST {self.path}")
            return
        try:
            try:
                body = json.loads(raw)
            except ValueError as error:
                raise BadRequest(f"the request body is not valid JSON: {error}") from error
            payload = complete(body, self.server.model)
        except BadRequest as error:
            self._send_error(400, str(error))
            return
        self._send_json(200, payload)


class MockServer:
    """The mock on a background thread. Use it as a context manager in tests.

    Port 0 asks the operating system for a free port, which is what tests should use.
    """

    def __init__(self, model: str = DEFAULT_MODEL, port: int = 0):
        self._httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
        self._httpd.daemon_threads = True
        self._httpd.model = model
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> MockServer:
        # The short poll interval keeps stop() quick, which matters with one server per test.
        self._thread = threading.Thread(target=self._httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._thread is not None:
            self._httpd.shutdown()
            self._thread.join(timeout=5)
            self._thread = None
        self._httpd.server_close()

    def serve_forever(self) -> None:
        try:
            self._httpd.serve_forever()
        finally:
            self._httpd.server_close()

    def __enter__(self) -> MockServer:
        return self.start()

    def __exit__(self, *exc_info) -> None:
        self.stop()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8000, help="port on 127.0.0.1, 0 picks a free one")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="model name to report")
    args = ap.parse_args()

    server = MockServer(model=args.model, port=args.port)
    print(f"mock inference server on {server.url}, model {args.model}. Ctrl-C stops it.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
