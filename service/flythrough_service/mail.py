"""Outbound email: magic links and delivery notices.

In dev, mail is written to a file and never sent. That is not a stub -- it is
the only safe default for a service whose test suite creates customers with
made-up addresses. Sending real mail requires FLYTHROUGH_SMTP_URL to be set,
which production refuses to start without.
"""

from __future__ import annotations

import json
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class Sent:
    to: str
    subject: str
    body: str


class Mailer:
    """smtp_url form: smtp+tls://user:password@host:port/?from=hello@domain"""

    def __init__(self, smtp_url: str, *, spool: Path, sender: str) -> None:
        self.smtp_url = smtp_url
        self.spool = Path(spool)
        self.sender = sender
        self.spool.parent.mkdir(parents=True, exist_ok=True)

    @property
    def live(self) -> bool:
        return bool(self.smtp_url)

    def send(self, to: str, subject: str, body: str) -> Sent:
        msg = Sent(to=to, subject=subject, body=body)
        if not self.live:
            with open(self.spool, "a") as f:
                f.write(json.dumps({"to": to, "subject": subject,
                                    "body": body}) + "\n")
            return msg
        u = urlparse(self.smtp_url)
        em = EmailMessage()
        em["From"] = self.sender
        em["To"] = to
        em["Subject"] = subject
        em.set_content(body)
        port = u.port or (465 if u.scheme.endswith("ssl") else 587)
        if u.scheme.endswith("ssl"):
            server = smtplib.SMTP_SSL(u.hostname, port,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(u.hostname, port)
            server.starttls(context=ssl.create_default_context())
        with server:
            if u.username:
                server.login(unquote(u.username), unquote(u.password or ""))
            server.send_message(em)
        return msg

    def outbox(self) -> list[Sent]:
        """Dev only: what would have been sent. Used by the tests."""
        if not self.spool.is_file():
            return []
        return [Sent(**json.loads(line))
                for line in self.spool.read_text().splitlines() if line.strip()]
