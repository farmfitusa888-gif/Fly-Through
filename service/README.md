# FlyThrough service

The V2 self-serve product: a customer uploads photographs, pays, and the
existing pipeline renders and delivers the film without an email round-trip.

    python3 service/run.py        # http://localhost:8000

Dev mode needs no credentials. Mail spools to `service/data/outbox.jsonl`
instead of sending, and the render worker stays off until a provider is
configured — so the shop, the dashboard and the partner ledger are all fully
usable on a laptop with nothing set up and no way to email a real person by
accident.

## The one ordering decision everything else follows from

**Photographs are uploaded and validated before payment.** Any other sequence
occasionally charges someone whose photos cannot make a film — which is a
refund, an apology, and the review that says "they took my money and then told
me no". The Pay button does not appear until the set passes.

## Routes

| | |
|---|---|
| `/` | the shop |
| `/order/{id}` | upload photographs, answer three questions |
| `/start` | post-payment landing — shows status, never sets it |
| `/webhooks/stripe` | the **only** thing that may mark an order paid |
| `/login` `/auth` | magic link, no passwords |
| `/orders` | customer dashboard: status, downloads, reorder |
| `/partner` | reseller ledger and referral link |
| `/partner/join` | enrolment |
| `/shoot/{id}` | the shot list, on the phone, on site |
| `/o/{id}` | "did it sell?" — one question, no login needed |
| `/admin/queue` | operator view: render queue and outcome stats |
| `/healthz` | liveness |

## Layout

| File | What it does |
|---|---|
| `config.py` | One settings object, read from `site/config.json`. Secrets from the environment only, `repr=False`. Refuses to start in production without all four. |
| `db.py` | SQLite, 11 tables, WAL, foreign keys on. Money in integer cents. Tokens hashed. Append-only event log. Webhook de-duplication. |
| `storage.py` | Content-addressed blobs. Type sniffed from magic bytes. Originals `chmod 444`, no edit path. |
| `auth.py` | Magic links, hashed tokens, single use, CSRF derived from the session. |
| `orders.py` | The state machine. Illegal transitions raise; repeated ones are no-ops. |
| `payments.py` | Signature verified before parsing. Exactly-once. Amount checked against the quote. |
| `reseller.py` | 25% lifetime, first-touch attribution, reversal on refund. |
| `queue.py` | Atomic claim on a status-guarded UPDATE. Retries twice, then fails loudly. |
| `render.py` | Arranges uploads into what the pipeline expects. No rendering logic of its own. |
| `notify.py` | Four transactional emails and no others. Each claimed in the event log before sending, so nobody is emailed twice about one order. |
| `limits.py` | Rate limiting in the database, not in memory — workers do not share memory and a restart must not reset a limit. |
| `outcomes.py` | "Did it sell?" Stored against the brief. The compounding asset. |
| `ui.py` | HTML in the marketing site's visual language. Everything escaped. |
| `app.py` | Routes. |

## Environment

| Variable | Needed | What for |
|---|---|---|
| `FLYTHROUGH_ENV` | no | `production` turns on the secret requirements |
| `FLYTHROUGH_SECRET_KEY` | production | CSRF derivation |
| `STRIPE_SECRET_KEY` | production | Stripe API |
| `STRIPE_WEBHOOK_SECRET` | production | webhook signatures |
| `FLYTHROUGH_SMTP_URL` | production | outbound mail |
| `FLYTHROUGH_PROVIDER` | to render | which render provider to use |
| `FLYTHROUGH_DATA` | no | data directory, defaults to `service/data` |

A production boot without the four required secrets **refuses to start**. A
service missing `STRIPE_WEBHOOK_SECRET` would mark orders paid on anyone's POST.

## Backup

    cp -r service/data /somewhere/safe

That is the whole procedure. The database, the customer's originals and every
rendered deliverable are all under it.

## Tests

    python3 -m pytest service/tests -q

`test_service.py` covers the layers directly; `test_http.py` drives the real
ASGI app over HTTP, because the routing, cookies, CSRF checks and redirects are
the parts most likely to be wrong and calling handlers directly skips all of it.

## The two loops that make this more than a renderer

**Shoot-time capture** (`/shoot/{id}`). Every quality problem this project has
hit traces to the source set: an aerial framed over the wrong side, a missing
bridge between the front and the back of a property, a dark infotainment screen.
The shot guides are good and are read the night before. This runs the same
checks *at the moment of capture*, on the phone, and says "you can leave" only
when the set actually holds together. A re-shoot is free while you are standing
in the room and impossible once you have driven away.

**Outcome capture** (`/o/{id}`). One question thirty days after delivery — did
it sell? — stored against the brief that produced the film. Model quality
converges and is a subscription anyone can buy. A competitor with a better
renderer still cannot tell a customer which opening frame moves a listing in
their price band, because they have never delivered a film and asked what
happened next.

The advice it produces is deliberately hard to trigger: both groups need twelve
samples and a five-day gap, or it says nothing. A finding from four listings is
a coincidence, and saying nothing is free while saying something wrong costs the
credibility everything else here rests on.

## Environment additions

| Variable | Needed | What for |
|---|---|---|
| `FLYTHROUGH_OPERATORS` | production | Comma-separated addresses allowed on `/admin/*`. **Empty admits nobody.** |

## Security posture

Audited rather than assumed. What is enforced, and why:

| | |
|---|---|
| **Every response carries CSP, nosniff, Referrer-Policy, X-Frame-Options** | The static site gets these from `_headers`, which the app never sees — so the pages a customer actually transacts on were the unprotected ones. |
| **CSP uses a per-response nonce, never `unsafe-inline`** | A policy with `unsafe-inline` stops almost nothing. The shot list's auto-submit moved out of an inline `onchange` into a nonce'd script specifically so the policy could stay strict. |
| **`next=` is allow-shaped, not blocklisted** | `startswith("/")` was the bug: `//evil.com` passes it and a browser reads it as absolute. An attacker could mail `/login?next=//evil.com`, the victim signs in with us and lands on their page. |
| **Public file route checks the name *and* the resolved path** | The basename check alone was safe by accident — `Path("..").name` is `".."`, not `""`. The decisive check is that the resolved path is inside the originals directory. |
| **All SQL is parameterised** | One f-string exists, in `orders.transition`, over a value from a literal dict. It carries an assert so a future edit fails loudly rather than becoming an injection. |
| **Errors leak nothing** | Probed: no traceback, file path, module name or SQL reaches a response body. |
| **404 rather than 403 on operator routes** | A 403 confirms an operator console exists at that path and is worth attacking. |
| **Rate limits live in the database** | Workers do not share memory, and a restart must not reset a limit. |
| **Secrets are `repr=False`** | FastAPI puts locals in tracebacks; without it a live Stripe key rides into the error log. |
| **HSTS only in production** | Sending it from a dev server on http pins a name to https on the developer's own machine. |
