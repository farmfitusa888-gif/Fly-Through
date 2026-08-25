"""Provider payload validation and the HTTP submit/poll loop.

Every test here runs against a recorded schema or a local server. None of it
spends a credit, which is the point: payload drift is silent and expensive --
a renamed field or a float where an integer is required produces a rejected
job, which reaches the customer as a failed render they already paid for and
reaches the operator looking exactly like a provider outage.
"""

from __future__ import annotations

import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flythrough import providers as pv  # noqa: E402
from flythrough.planner import Shot  # noqa: E402
from flythrough.providers.http import (Connection, ProviderError, dig,  # noqa: E402
                                       make)
from flythrough.render import OpenArtAdapter  # noqa: E402


@pytest.fixture()
def profile():
    return pv.load("wan2-7", "image2video")


def a_shot(**kw) -> Shot:
    base = dict(index=0, move="orbit_left", move_label="orbit", seconds=4,
                start_frame="https://x/a.jpg", end_frame="https://x/b.jpg",
                from_room="kitchen", to_room="living",
                prompt="a prompt", negative_prompt="a negative")
    base.update(kw)
    return Shot(**base)


# ------------------------------------------------------------- the schema


def test_the_recorded_schema_matches_what_the_adapter_builds(profile):
    """The one that matters. If this fails, real jobs are being rejected."""
    pv.validate(OpenArtAdapter().build(None, a_shot()).params, profile)


def test_every_move_at_every_tempo_produces_a_valid_payload(profile):
    """A tempo that floors a duration below the provider's minimum would fail
    only on the shots that used that move -- the worst kind of partial
    failure, because the batch looks like it half-worked."""
    from flythrough import moves as mv
    for key, move in mv.MOVES.items():
        for tempo in ("tour", "ad", "hype"):
            secs = mv.at_tempo(move, tempo).seconds
            params = OpenArtAdapter().build(
                None, a_shot(move=key, seconds=secs)).params
            pv.validate(params, profile)


@pytest.mark.parametrize("mutate,why", [
    (lambda p: {**p, "duration": 4.5}, "float duration"),
    (lambda p: {**p, "duration": 99}, "duration over the maximum"),
    (lambda p: {**p, "duration": 1}, "duration under the minimum"),
    (lambda p: {**p, "duration": True}, "bool as duration"),
    (lambda p: {**p, "resolution": "4k"}, "resolution not in the enum"),
    (lambda p: {**p, "videoCount": 0}, "videoCount under the minimum"),
    (lambda p: {**p, "seed": 7}, "field the provider does not accept"),
    (lambda p: {k: v for k, v in p.items() if k != "negativePrompt"},
     "missing required field"),
    (lambda p: {**p, "startFrame": {"type": "image", "id": "a", "url": "u"}},
     "frame missing label"),
    (lambda p: {**p, "startFrame": {"type": "video", "id": "a", "url": "u",
                                    "label": "l"}}, "frame of the wrong type"),
    (lambda p: {**p, "startFrame": {"type": "image", "id": "a", "url": "",
                                    "label": "l"}}, "frame with an empty url"),
    (lambda p: {**p, "enablePromptExpansion": "no"}, "string as a boolean"),
])
def test_bad_payloads_are_caught_before_they_cost_anything(profile, mutate, why):
    params = OpenArtAdapter().build(None, a_shot()).params
    with pytest.raises(pv.PayloadInvalid):
        pv.validate(mutate(params), profile)


def test_the_error_lists_everything_wrong_at_once(profile):
    """Fixing one field, resubmitting, and discovering the next is how a
    debugging session becomes four rejected jobs."""
    params = OpenArtAdapter().build(None, a_shot()).params
    params.update({"duration": 99, "resolution": "4k", "seed": 1})
    with pytest.raises(pv.PayloadInvalid) as e:
        pv.validate(params, profile)
    msg = str(e.value)
    assert "duration" in msg and "resolution" in msg and "seed" in msg


def test_an_unrecorded_model_refuses_rather_than_guessing():
    with pytest.raises(FileNotFoundError) as e:
        pv.load("some-new-model", "image2video")
    assert "guessing" in str(e.value)


def test_prompt_expansion_stays_off(profile):
    """Server-side prompt rewriting reintroduces exactly the invention the
    negative bank exists to suppress -- and it is on by default."""
    params = OpenArtAdapter().build(None, a_shot()).params
    assert params["enablePromptExpansion"] is False


def test_both_frames_are_always_sent(profile):
    """Anchoring is the entire product. A payload with only a start frame is a
    normal AI video, and nobody would be able to tell from the invoice."""
    params = OpenArtAdapter().build(None, a_shot()).params
    assert params["startFrame"]["url"] and params["endFrame"]["url"]


# --------------------------------------------------------------- dotted paths


@pytest.mark.parametrize("path,want", [
    ("data.output.0.url", "https://x/v.mp4"),
    ("status", "SUCCEEDED"),
    ("data.nope", None),
    ("data.output.9.url", None),
    ("status.deeper", None),
    ("", None),
])
def test_dig_walks_responses_without_exploding(path, want):
    payload = {"data": {"output": [{"url": "https://x/v.mp4"}]},
               "status": "SUCCEEDED"}
    assert dig(payload, path) == want


# ------------------------------------------------------------ the HTTP loop


class _Fake(http.server.BaseHTTPRequestHandler):
    script: dict = {}

    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode() if isinstance(obj, dict) else obj
        self.send_response(code)
        self.send_header("Content-Type", self.script.get("ctype",
                                                         "application/json"))
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or "{}")
        self.script.setdefault("submissions", []).append(
            {"body": body, "auth": self.headers.get("Authorization")})
        if self.script.get("submit_code", 200) != 200:
            self._send(self.script.get("submit_body", {"error": "nope"}),
                       self.script["submit_code"])
            return
        self._send(self.script.get("submit_resp", {"id": "job-1"}))

    def do_GET(self):
        self.script["polls"] = self.script.get("polls", 0) + 1
        seq = self.script.get("poll_seq", [{"status": "SUCCEEDED",
                                            "output": {"url": "https://cdn/v.mp4"}}])
        i = min(self.script["polls"] - 1, len(seq) - 1)
        self._send(seq[i])


@pytest.fixture()
def fake():
    _Fake.script = {}
    srv = socketserver.TCPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    yield _Fake.script, Connection(
        submit_url=f"http://127.0.0.1:{port}/submit",
        status_url=f"http://127.0.0.1:{port}/status/{{id}}",
        token="SECRET123", timeout_s=5)
    srv.shutdown()


def test_a_job_is_submitted_and_polled_to_completion(fake):
    script, conn = fake
    script["poll_seq"] = [{"status": "PENDING"}, {"status": "PENDING"},
                          {"status": "SUCCEEDED",
                           "output": {"url": "https://cdn/v.mp4"}}]
    submit, poll = make(conn)
    jid = submit(OpenArtAdapter().build(None, a_shot()))
    assert jid == "job-1"
    assert poll(jid) == ("PENDING", None)
    assert poll(jid) == ("PENDING", None)
    assert poll(jid) == ("DONE", "https://cdn/v.mp4")


def test_the_credential_is_sent_and_the_payload_is_shaped(fake):
    script, conn = fake
    submit, _ = make(conn)
    submit(OpenArtAdapter().build(None, a_shot()))
    sent = script["submissions"][0]
    assert sent["auth"] == "Bearer SECRET123"
    assert sent["body"]["model"] == "wan2-7"
    assert sent["body"]["params"]["duration"] == 4


def test_an_invalid_payload_never_reaches_the_provider(fake):
    """Validation before the network call, so a rejectable job costs nothing
    and never occupies a slot."""
    script, conn = fake
    submit, _ = make(conn)
    job = OpenArtAdapter().build(None, a_shot())
    job.params["duration"] = 99
    with pytest.raises(pv.PayloadInvalid):
        submit(job)
    assert not script.get("submissions"), "a bad payload was sent anyway"


def test_a_failed_status_is_reported_as_failed(fake):
    script, conn = fake
    script["poll_seq"] = [{"status": "FAILED"}]
    _, poll = make(conn)
    assert poll("job-1") == ("FAILED", None)


def test_done_with_no_file_raises_rather_than_hanging(fake):
    """Reporting PENDING there would hang the whole batch until timeout, and
    the operator would be looking for a slow provider instead of a broken one."""
    script, conn = fake
    script["poll_seq"] = [{"status": "SUCCEEDED", "output": {}}]
    _, poll = make(conn)
    with pytest.raises(ProviderError) as e:
        poll("job-1")
    assert "result_path" in str(e.value) or "output.url" in str(e.value)


def test_a_submit_response_without_an_id_says_what_it_saw(fake):
    script, conn = fake
    script["submit_resp"] = {"jobId": "x"}          # wrong key on purpose
    submit, _ = make(conn)
    with pytest.raises(ProviderError) as e:
        submit(OpenArtAdapter().build(None, a_shot()))
    assert "jobId" in str(e.value)


def test_an_http_error_never_leaks_the_credential(fake):
    """Providers echo the request back in error bodies. A token in a log or a
    customer-facing error is a token that has to be rotated."""
    script, conn = fake
    script["submit_code"] = 401
    script["submit_body"] = {"error": "bad token: SECRET123"}
    submit, _ = make(conn)
    with pytest.raises(ProviderError) as e:
        submit(OpenArtAdapter().build(None, a_shot()))
    assert "SECRET123" not in str(e.value)
    assert "***" in str(e.value)


def test_a_non_json_body_is_a_clear_error(fake):
    script, conn = fake
    script["ctype"] = "text/html"
    script["submit_resp"] = b"<html>502 upstream</html>"
    submit, _ = make(conn)
    with pytest.raises(ProviderError) as e:
        submit(OpenArtAdapter().build(None, a_shot()))
    assert "non-JSON" in str(e.value)


def test_an_unreachable_provider_is_a_clear_error():
    conn = Connection(submit_url="http://127.0.0.1:1/submit",
                      status_url="http://127.0.0.1:1/{id}", token="t",
                      timeout_s=2)
    submit, _ = make(conn)
    with pytest.raises(ProviderError) as e:
        submit(OpenArtAdapter().build(None, a_shot()))
    assert "cannot reach provider" in str(e.value)


def test_a_connection_profile_rejects_unknown_keys(tmp_path):
    """A typo in a profile would otherwise be silently ignored and the default
    used instead -- which is how you poll the wrong URL for an hour."""
    p = tmp_path / "conn.json"
    p.write_text(json.dumps({"submit_url": "https://x", "status_url": "https://x/{id}",
                             "resultpath": "output.url"}))
    with pytest.raises(ProviderError) as e:
        Connection.from_file(p, "tok")
    assert "resultpath" in str(e.value)


def test_the_example_profile_loads(tmp_path):
    """It is checked in, so it must at least be structurally valid."""
    example = ROOT / "flythrough" / "providers" / "connection.example.json"
    conn = Connection.from_file(example, "tok")
    assert conn.submit_url and "{id}" in conn.status_url


def test_the_token_is_never_written_into_a_profile():
    example = ROOT / "flythrough" / "providers" / "connection.example.json"
    assert "token" not in json.loads(example.read_text())


# ------------------------------------------- providers that split status/result


class _Queue(http.server.BaseHTTPRequestHandler):
    """Shaped like fal.ai: submit returns request_id, status and result are
    separate GETs, and the video URL only ever appears on the result."""
    script: dict = {}

    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.script["body"] = json.loads(self.rfile.read(n) or "{}")
        self.script["auth"] = self.headers.get("Authorization")
        self._send({"request_id": "req-42"})

    def do_GET(self):
        if self.path.endswith("/status"):
            self.script["status_calls"] = self.script.get("status_calls", 0) + 1
            seq = self.script.get("seq", ["IN_QUEUE", "IN_PROGRESS", "COMPLETED"])
            i = min(self.script["status_calls"] - 1, len(seq) - 1)
            self._send({"status": seq[i]})
        else:
            self.script["result_calls"] = self.script.get("result_calls", 0) + 1
            self._send(self.script.get("result",
                                       {"video": {"url": "https://cdn/out.mp4"}}))


@pytest.fixture()
def queue_provider():
    _Queue.script = {}
    srv = socketserver.TCPServer(("127.0.0.1", 0), _Queue)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/model"
    yield _Queue.script, Connection(
        submit_url=base,
        status_url=base + "/requests/{id}/status",
        result_url=base + "/requests/{id}",
        body_mode="params", auth_format="Key {token}",
        job_id_path="request_id", result_path="video.url",
        done_values=("COMPLETED",), token="FALKEY", timeout_s=5)
    srv.shutdown()


def test_a_split_status_and_result_provider_works(queue_provider):
    """Reading the video URL off the STATUS body would find nothing there,
    forever -- the batch would time out looking healthy the whole time."""
    script, conn = queue_provider
    submit, poll = make(conn)
    jid = submit(OpenArtAdapter().build(None, a_shot()))
    assert jid == "req-42"
    assert poll(jid) == ("PENDING", None)
    assert poll(jid) == ("PENDING", None)
    assert poll(jid) == ("DONE", "https://cdn/out.mp4")


def test_the_result_endpoint_is_only_called_once_finished(queue_provider):
    """Polling the result of an unfinished job is a wasted round trip against
    a provider that rate-limits."""
    script, conn = queue_provider
    _, poll = make(conn)
    poll("req-42")
    poll("req-42")
    assert script.get("result_calls") is None
    poll("req-42")
    assert script["result_calls"] == 1


def test_params_body_mode_posts_the_model_input_directly(queue_provider):
    """A per-model endpoint expects the input at the top level. Nesting it
    under model/mode/params sends a body the endpoint ignores entirely."""
    script, conn = queue_provider
    submit, _ = make(conn)
    submit(OpenArtAdapter().build(None, a_shot()))
    assert "params" not in script["body"]
    assert script["body"]["duration"] == 4
    assert script["auth"] == "Key FALKEY"


def test_an_unknown_body_mode_is_refused(queue_provider):
    script, conn = queue_provider
    conn.body_mode = "sideways"
    submit, _ = make(conn)
    with pytest.raises(ProviderError) as e:
        submit(OpenArtAdapter().build(None, a_shot()))
    assert "body_mode" in str(e.value)


def test_documentation_keys_are_allowed_but_typos_are_not(tmp_path):
    """A profile is where an operator records where a value came from and what
    still needs confirming. That note is worth more than a bare config file --
    but a typo'd REAL key must still fail rather than silently defaulting."""
    good = tmp_path / "g.json"
    good.write_text(json.dumps({
        "_sourced": "from the provider docs, August 2026",
        "_confirm": "field names before the first paid run",
        "submit_url": "https://x", "status_url": "https://x/{id}"}))
    assert Connection.from_file(good, "t").submit_url == "https://x"

    bad = tmp_path / "b.json"
    bad.write_text(json.dumps({"submit_url": "https://x",
                               "status_url": "https://x/{id}",
                               "statuspath": "state"}))
    with pytest.raises(ProviderError):
        Connection.from_file(bad, "t")


def test_the_shipped_example_profiles_all_load():
    d = ROOT / "flythrough" / "providers"
    for f in sorted(d.glob("*.example.json")):
        conn = Connection.from_file(f, "tok")
        assert conn.submit_url and "{id}" in conn.status_url, f.name
        assert "token" not in json.loads(f.read_text()), f"{f.name} holds a secret"
