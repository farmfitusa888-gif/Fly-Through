"""The render queue.

A background worker, not a request handler. Rendering takes minutes and costs
money; doing it inside the webhook would mean Stripe times out, retries, and we
render twice.

Claiming is a single atomic UPDATE with a status guard. Two workers racing for
one job both run the statement; SQLite serialises them and exactly one sees
rowcount 1. That is the whole concurrency design, and it is why the queue does
not need a broker.
"""

from __future__ import annotations

import json
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from . import notify, orders, render
from .db import Database, new_id, now

MAX_ATTEMPTS = 3


class Renderer(Protocol):
    """What the worker needs from a renderer.

    A protocol rather than a direct call so the queue is testable without
    spending credits, and so a provider change never reaches this file.
    """

    def __call__(self, *, order_id: str, vertical: str, slug: str,
                 originals: Path, out_dir: Path, brief: dict,
                 placement: str, originals_url: str) -> list[tuple[str, Path]]:
        """Returns [(kind, path)] -- master, vertical, thumb, disclosure."""


@dataclass
class Worker:
    db: Database
    data_dir: Path
    renderer: Renderer
    concurrency: int = 2
    # Optional so the queue is testable without a mail transport. When they are
    # supplied a delivered order tells the customer, and a failed one tells them
    # too -- a customer who has to ask what happened to the film they paid for
    # is already a refund.
    mailer: object = None
    settings: object = None

    _stop: threading.Event = None            # type: ignore[assignment]
    _threads: list = None                    # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._stop = threading.Event()
        self._threads = []

    # ---------------------------------------------------------------- queueing
    def enqueue(self, order_id: str) -> str:
        jid = new_id("job")
        with self.db.tx() as c:
            existing = c.execute(
                "SELECT id FROM jobs WHERE order_id = ? AND status IN"
                " ('queued','running','done')", (order_id,)).fetchone()
            if existing:
                return existing["id"]        # one render per order, ever
            c.execute("INSERT INTO jobs(id, order_id, status, queued_at)"
                      " VALUES(?,?,?,?)", (jid, order_id, "queued", now()))
            self.db.log(c, "job.queued", order_id, jid)
        return jid

    def claim(self) -> dict | None:
        with self.db.tx() as c:
            row = c.execute(
                "SELECT id, order_id, attempts FROM jobs WHERE status = 'queued'"
                " ORDER BY queued_at LIMIT 1").fetchone()
            if row is None:
                return None
            # The guard is the lock. If another worker got here first its UPDATE
            # already moved the row out of 'queued' and this one matches nothing.
            changed = c.execute(
                "UPDATE jobs SET status='running', started_at=?, attempts=attempts+1"
                " WHERE id = ? AND status = 'queued'", (now(), row["id"])).rowcount
            if changed != 1:
                return None
            return {"id": row["id"], "order_id": row["order_id"],
                    "attempts": row["attempts"] + 1}

    # ----------------------------------------------------------------- running
    def run_one(self) -> str | None:
        job = self.claim()
        if job is None:
            return None
        oid = job["order_id"]
        try:
            self._render(oid)
            with self.db.tx() as c:
                c.execute("UPDATE jobs SET status='done', finished_at=?, error=''"
                          " WHERE id = ?", (now(), job["id"]))
                orders.transition(c, self.db, oid, "delivered")
                self.db.log(c, "job.done", oid, job["id"])
            # AFTER the commit. An email announcing a delivery that then rolled
            # back is worse than a late email.
            self._tell(oid, delivered=True)
            return job["id"]
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            final = job["attempts"] >= MAX_ATTEMPTS
            with self.db.tx() as c:
                c.execute(
                    "UPDATE jobs SET status=?, finished_at=?, error=? WHERE id=?",
                    ("failed" if final else "queued",
                     now() if final else None, detail[:2000], job["id"]))
                if final:
                    # The order is marked failed so it appears in the dashboard
                    # as needing attention. It is NOT auto-refunded: a human
                    # decides whether to re-cut or refund.
                    try:
                        orders.transition(c, self.db, oid, "failed")
                    except orders.OrderError:
                        pass
                self.db.log(c, "job.failed" if final else "job.retry", oid,
                            detail[:500])
            if final:
                (self.data_dir / "failures").mkdir(parents=True, exist_ok=True)
                (self.data_dir / "failures" / f"{job['id']}.txt").write_text(
                    traceback.format_exc())
                self._tell(oid, delivered=False)
            return job["id"]

    def _render(self, order_id: str) -> None:
        o = orders.get(self.db, order_id)
        if o is None:
            raise RuntimeError("order vanished")
        if o["status"] == "paid":
            with self.db.tx() as c:
                orders.transition(c, self.db, order_id, "rendering")
        with self.db.tx() as c:
            ups = [dict(r) for r in c.execute(
                "SELECT * FROM uploads WHERE order_id = ? ORDER BY position",
                (order_id,)).fetchall()]
        if not ups:
            raise RuntimeError("no uploads on a paid order")

        brief = json.loads(o["brief"] or "{}")
        prep = render.prepare(o["vertical"], ups)
        if prep.blocks:
            raise RuntimeError("shot set cannot be filmed: " + "; ".join(prep.blocks))

        slug = render.slug_for(order_id, brief)
        originals = render.stage_originals(self.data_dir, order_id, prep.photos)
        out_dir = render.output_dir(self.data_dir, order_id) / "delivery"
        out_dir.mkdir(parents=True, exist_ok=True)

        # The disclosure URL has to be known BEFORE the render: it is burned
        # into the QR code and the caption, so it cannot be filled in after.
        # The order id is already unguessable, so the address is stable from the
        # moment the order exists.
        base = getattr(self.settings, "base_url", "") if self.settings else ""
        originals_url = f"{base}/o/{order_id}/originals" if base else ""

        produced = self.renderer(
            order_id=order_id, vertical=o["vertical"], slug=slug,
            originals=originals, out_dir=out_dir, brief=brief,
            placement=render.placement_for(o["vertical"]),
            originals_url=originals_url)

        with self.db.tx() as c:
            for kind, path in produced:
                p = Path(path)
                c.execute("INSERT INTO deliverables(id, order_id, kind, path,"
                          " bytes, created_at) VALUES(?,?,?,?,?,?)",
                          (new_id("dlv"), order_id, kind, str(p),
                           p.stat().st_size if p.is_file() else 0, now()))

    def deliver_manual(self, order_id: str, clips: list) -> None:
        """Finish an order the operator rendered by hand.

        Goes through the SAME assemble path as the automatic route, so a
        hand-worked order and a machine-worked one produce an identical file.
        The only difference is where the clips came from, and that must not be
        visible in the delivery.
        """
        from flythrough.assemble import deliver
        o = orders.get(self.db, order_id)
        if o is None:
            raise RuntimeError("no such order")
        if o["status"] not in ("paid", "rendering"):
            raise RuntimeError(f"order is {o['status']}, not awaiting a render")
        if not clips:
            raise RuntimeError("no clips")

        with self.db.tx() as c:
            if o["status"] == "paid":
                orders.transition(c, self.db, order_id, "rendering")

        out = render.output_dir(self.data_dir, order_id) / "delivery"
        out.mkdir(parents=True, exist_ok=True)
        slug = render.slug_for(order_id, json.loads(o["brief"] or "{}"))
        # Sorted by filename, which is why the operator is told to name them
        # shot_01, shot_02. Cut order is the product; a shuffled delivery is
        # not a lesser version of it, it is a different film.
        d = deliver(sorted(clips, key=lambda p: Path(p).name), out,
                    slug=slug, crossfade=0.0, fps=30)

        produced = [("master", Path(d.master_web or d.master))]
        if d.vertical:
            produced.append(("vertical", Path(d.vertical_web or d.vertical)))
        if d.thumbnail:
            produced.append(("thumb", Path(d.thumbnail)))

        with self.db.tx() as c:
            c.execute("DELETE FROM deliverables WHERE order_id = ?", (order_id,))
            for kind, path in produced:
                c.execute("INSERT INTO deliverables(id, order_id, kind, path,"
                          " bytes, created_at) VALUES(?,?,?,?,?,?)",
                          (new_id("dlv"), order_id, kind, str(path),
                           path.stat().st_size if path.is_file() else 0, now()))
            c.execute("UPDATE jobs SET status='done', finished_at=?, error=''"
                      " WHERE order_id = ? AND status IN ('queued','running')",
                      (now(), order_id))
            orders.transition(c, self.db, order_id, "delivered")
            self.db.log(c, "job.delivered_by_hand", order_id, str(len(clips)))
        self._tell(order_id, delivered=True)

    def _tell(self, order_id: str, *, delivered: bool) -> None:
        """Notify the customer. Never allowed to undo the job's outcome: the
        film exists either way, and a bounced address must not turn a delivered
        order back into a failed one."""
        if self.mailer is None or self.settings is None:
            return
        o = orders.get(self.db, order_id)
        if o is None:
            return
        from . import catalog_bridge as cat
        sku = cat.skus().get(o["sku"])
        what = sku.name if sku else o["sku"]
        try:
            if delivered:
                kinds = [d["kind"] for d in orders.deliverables(self.db, order_id)]
                notify.delivered(self.db, self.mailer, self.settings, order_id,
                                 what=what, kinds=kinds)
            else:
                notify.failed(self.db, self.mailer, self.settings, order_id,
                              what=what)
        except Exception as exc:                      # noqa: BLE001
            with self.db.tx() as c:
                self.db.log(c, "notify.error", order_id, str(exc)[:300])

    # --------------------------------------------------------------- lifecycle
    def _loop(self) -> None:
        while not self._stop.is_set():
            if self.run_one() is None:
                self._stop.wait(1.0)

    def start(self) -> None:
        for _ in range(self.concurrency):
            t = threading.Thread(target=self._loop, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=timeout)
        self._threads.clear()

    def stats(self) -> dict:
        with self.db.tx() as c:
            rows = c.execute("SELECT status, count(*) n FROM jobs GROUP BY status")
            return {r["status"]: r["n"] for r in rows}
