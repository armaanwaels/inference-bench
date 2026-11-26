import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))

import mock_server  # noqa: E402


@pytest.fixture()
def server():
    with mock_server.MockServer() as running:
        yield running


def call(server, path, body=None, raw=None):
    """One HTTP call to the mock. Returns (status, parsed JSON body)."""
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    request = urllib.request.Request(server.url + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def complete(server, **fields):
    body = {"model": mock_server.DEFAULT_MODEL, "prompt": "the quick brown fox", "max_tokens": 8, **fields}
    status, payload = call(server, "/v1/completions", body)
    assert status == 200, payload
    return payload


def test_server_listens_on_loopback_and_an_ephemeral_port(server):
    assert server.url.startswith("http://127.0.0.1:")
    assert server.port != 0


def test_models_lists_the_served_model(server):
    status, payload = call(server, "/v1/models")
    assert status == 200
    assert [m["id"] for m in payload["data"]] == [mock_server.DEFAULT_MODEL]


def test_same_request_twice_gives_the_same_text(server):
    first = complete(server)
    second = complete(server)
    assert first["choices"][0]["text"] == second["choices"][0]["text"]
    assert first["choices"][0]["text"] != ""


def test_different_prompts_give_different_text(server):
    a = complete(server, prompt="the quick brown fox")
    b = complete(server, prompt="the quick brown dog")
    assert a["choices"][0]["text"] != b["choices"][0]["text"]


def test_different_seeds_give_different_text(server):
    a = complete(server, seed=1)
    b = complete(server, seed=2)
    assert a["choices"][0]["text"] != b["choices"][0]["text"]
    assert complete(server, seed=1)["choices"][0]["text"] == a["choices"][0]["text"]


def test_usage_adds_up(server):
    payload = complete(server, prompt="one two three four five", max_tokens=12)
    usage = payload["usage"]
    assert usage["prompt_tokens"] == 5
    assert usage["completion_tokens"] == 12
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    # Every mock token is one word with a leading space, so the text can be counted.
    assert len(payload["choices"][0]["text"].split()) == usage["completion_tokens"]


def test_max_tokens_is_honoured_and_a_shorter_output_is_a_prefix(server):
    short = complete(server, max_tokens=5)["choices"][0]
    long = complete(server, max_tokens=9)["choices"][0]
    assert len(short["text"].split()) == 5
    assert long["text"].startswith(short["text"])
    assert short["finish_reason"] == "length"


def test_max_tokens_zero_gives_empty_text(server):
    payload = complete(server, max_tokens=0)
    assert payload["choices"][0]["text"] == ""
    assert payload["usage"]["completion_tokens"] == 0


def test_tokens_are_a_pure_function_of_prompt_seed_and_position():
    tokens = mock_server.generate_tokens("hello world", seed=7, count=6)
    assert tokens == mock_server.generate_tokens("hello world", seed=7, count=6)
    assert tokens[:3] == mock_server.generate_tokens("hello world", seed=7, count=3)
    assert tokens != mock_server.generate_tokens("hello world", seed=8, count=6)
    assert tokens != mock_server.generate_tokens("hello there", seed=7, count=6)
    assert all(token.startswith(" ") for token in tokens)


def test_unknown_path_gives_404(server):
    assert call(server, "/v1/nothing")[0] == 404
    assert call(server, "/v1/nothing", {"prompt": "x"})[0] == 404
    # A known path with the wrong method is also not found.
    assert call(server, "/v1/models", {"prompt": "x"})[0] == 404


@pytest.mark.parametrize(
    "raw",
    [
        b"{not json",
        b"[1, 2, 3]",
        json.dumps({"model": "m"}).encode(),  # no prompt
        json.dumps({"prompt": 5}).encode(),
        json.dumps({"prompt": "x", "max_tokens": -1}).encode(),
        json.dumps({"prompt": "x", "max_tokens": "many"}).encode(),
        json.dumps({"prompt": "x", "max_tokens": True}).encode(),
        json.dumps({"prompt": "x", "seed": "abc"}).encode(),
    ],
)
def test_bad_request_gives_400_with_a_message(server, raw):
    status, payload = call(server, "/v1/completions", raw=raw)
    assert status == 400
    assert payload["error"]["message"]


@pytest.mark.parametrize("fields", [{"stream": True}, {"prompt": ["a", "b"]}])
def test_features_of_later_slices_are_refused_not_ignored(server, fields):
    # Streaming arrives in slice 3 and prompt lists in slice 5. Until then the mock must say no,
    # because silently answering in another shape would make a client test pass for the wrong reason.
    body = {"model": mock_server.DEFAULT_MODEL, "prompt": "x", "max_tokens": 4, **fields}
    status, payload = call(server, "/v1/completions", body)
    assert status == 400
    assert "not supported" in payload["error"]["message"]


def test_server_stops_and_frees_the_port():
    with mock_server.MockServer() as running:
        url = running.url
        assert call(running, "/v1/models")[0] == 200
    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen(url + "/v1/models", timeout=2)
