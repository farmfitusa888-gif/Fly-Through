"""A generic submit/poll provider over HTTP.

Configured from a connection profile rather than hard-coded to a vendor,
because the provider is the single most likely thing in this system to change:
the moment a model with better dual-frame anchoring ships, we move. Nothing
above this file knows who is rendering.

What it does NOT do is guess. Endpoint, auth header and response paths come from
the connection profile the operator supplies from their own provider account.
Inventing a URL would produce a component that looks finished, passes review,
and fails the first time real money is behind it.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import PayloadInvalid, load, validate

# Terminal and non-terminal states, normalised. Providers spell these
# differently; the pipeline only understands these three.
PENDING, DONE, FAILED = "PENDING", "DONE", "FAILED"


class ProviderError(RuntimeError):
    pass


def dig(payload: Any, path: str) -> Any:
    """Fetch a dotted path out of a response. 'data.output.0.url' works."""
    cur = payload
    for part in path.split("."):
        if cur is None:
            return None
        if part.isdigit() and isinstance(cur, list):
            idx = int(part)
            cur = cur[idx] if idx < len(cur) else None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


@dataclass
class Connection:
    """Everything vendor-specific, in one object, supplied by the operator.

    submit_url      full URL to POST a job to
    status_url      URL template for polling, containing {id}
    auth_header     header name, e.g. "Authorization"
    auth_format     value template, e.g. "Bearer {token}"
    token           the credential (never logged, never persisted here)
    job_id_path     dotted path to the job id in the submit response
    status_path     dotted path to the status in the poll response
    result_path     dotted path to the finished video URL
    done_values     provider strings that mean finished
    failed_values   provider strings that mean failed
    """
    submit_url: str
    status_url: str
    token: str
    auth_header: str = "Authorization"
    auth_format: str = "Bearer {token}"
    job_id_path: str = "id"
    status_path: str = "status"
    result_path: str = "output.url"
    done_values: tuple[str, ...] = ("DONE", "COMPLETED", "SUCCEEDED", "succeeded")
    failed_values: tuple[str, ...] = ("FAILED", "ERROR", "CANCELLED", "failed")
    timeout_s: float = 60.0

    @classmethod
    def from_file(cls, path: str | Path, token: str) -> "Connection":
        raw = json.loads(Path(path).read_text())
        raw.pop("_note", None)
        known = {f for f in cls.__dataclass_fields__ if f != "token"}
        unknown = set(raw) - known
        if unknown:
            raise ProviderError(
                f"connection profile has unknown keys {sorted(unknown)}; "
                f"expected some of {sorted(known)}")
        return cls(token=token, **raw)

    def _headers(self) -> dict[str, str]:
        return {self.auth_header: self.auth_format.format(token=self.token),
                "Content-Type": "application/json",
                "Accept": "application/json"}

    def _request(self, url: str, data: dict | None = None) -> dict:
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, headers=self._headers(),
                                     method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:400]
            # The credential can appear in an echoed request body. Never let a
            # provider error carry it into a log or a customer-facing message.
            raise ProviderError(
                f"provider returned {e.code}: {_redact(detail, self.token)}") from None
        except urllib.error.URLError as e:
            raise ProviderError(f"cannot reach provider: {e.reason}") from None
        except json.JSONDecodeError:
            raise ProviderError("provider returned a non-JSON body") from None


def _redact(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


def make(conn: Connection, *, model: str = "wan2-7", mode: str = "image2video"):
    """Return (submit, poll) for pipeline.render.submit_all.

    Every payload is validated against the recorded provider schema BEFORE it
    is sent. A rejected job is a render the customer already paid for, and a
    wrong field name looks exactly like an outage from the outside.
    """
    profile = load(model, mode)

    def submit(job) -> str:
        validate(job.params, profile)
        payload = {"model": job.model, "mode": job.mode, "params": job.params}
        resp = conn._request(conn.submit_url, payload)
        job_id = dig(resp, conn.job_id_path)
        if not job_id:
            raise ProviderError(
                f"submit response has nothing at {conn.job_id_path!r}; "
                f"keys were {sorted(resp)[:12]}")
        return str(job_id)

    def poll(job_id: str) -> tuple[str, str | None]:
        resp = conn._request(conn.status_url.format(id=job_id))
        raw = str(dig(resp, conn.status_path) or "")
        if raw in conn.done_values:
            url = dig(resp, conn.result_path)
            if not url:
                # Finished with no file is a provider bug, not a pending job.
                # Reporting PENDING here would hang the batch until timeout.
                raise ProviderError(
                    f"job {job_id} reported done with nothing at "
                    f"{conn.result_path!r}")
            return DONE, str(url)
        if raw in conn.failed_values:
            return FAILED, None
        return PENDING, None

    return submit, poll
