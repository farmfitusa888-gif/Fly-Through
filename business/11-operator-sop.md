# Operator SOP

Everything a person has to do, in the order they do it, written so someone who
is not the founder can run a day of this.

The system is deliberately one-person-in-the-loop. Payouts are recorded by hand,
outcome asks fire on a button, and a failed render waits for a human rather than
auto-refunding. That is not missing automation — each of those is a place where
being wrong costs more than the minute it saves, so a person looks first.

---

## Daily — about ten minutes

### 1. Open `/admin/queue`

| What you see | What it means | What to do |
|---|---|---|
| `queued` climbing | Renders are backing up | Check the worker is running: `curl localhost:8000/healthz` |
| `failed` non-zero | A render gave up after 3 tries | Below, **A failed render** |
| Empty | Nothing waiting | Nothing to do |

### 2. Check the inbox

The four automatic emails go out on their own. What lands in the inbox is the
part that needs a person:

- **A reply to "did it sell?"** → open `/o/<order-id>`, type what they said, send.
  Takes ten seconds and it is the most valuable ten seconds in the day.
- **A refund request** → below, **A refund**.
- **Anything else** → answer it. There is no ticketing system on purpose; at
  this volume an inbox is faster and a customer can tell.

### 3. If it is Monday, press "Ask the N due"

Sends the thirty-day question to everyone delivered a month ago. It is a button
rather than a cron so nobody gets mailed at 4am because a scheduler fired twice.

---

## A failed render

The order is `failed`, the customer has already been emailed a plain-English
apology and an offer to refund, and nothing has auto-refunded. Your call.

1. **Read the error** on `/admin/queue`, and the traceback in
   `service/data/failures/<job-id>.txt`.
2. **Decide which of three it is:**

   | Error looks like | It is | Do |
   |---|---|---|
   | `cannot reach provider`, `provider returned 5xx` | Their outage | Re-queue in an hour. Nothing is wrong with the order. |
   | `PayloadInvalid: ...` | **Our bug** | Do not re-queue — it will fail identically. Fix the payload, add a test, then re-queue. |
   | `shot set cannot be filmed: ...` | Their photographs | Email the customer with the specific fix from the message. Refund if they cannot re-shoot. |

3. **Re-queue** by marking the order `paid` again; the worker picks it up.
   Do not create a second order — the customer would be charged twice.

**Never** re-queue a `PayloadInvalid` failure without changing something. Three
identical attempts already happened automatically.

---

## A refund

Policy is in `business/09-store.md` and on `/refunds/`: full refund before
delivery, free re-cut after, and the only thing not refunded is a job we warned
about before charging.

1. Refund in Stripe. **Do not edit the database** — the `charge.refunded`
   webhook marks the order and reverses the commission by itself, and doing it
   by hand leaves the two disagreeing.
2. Check `/admin/payouts` if the referring partner was about to be paid. An
   *accrued* commission reverses automatically; one already **paid** does not,
   and never will — that is deliberate. Money already sent is a conversation,
   not a silent ledger edit.

---

## Weekly — about twenty minutes

### Partner payouts

1. `/admin/payouts` lists everyone over the $50 minimum.
2. Pay them by bank transfer.
3. Record it with the bank reference. This emails them and writes the audit row.

Record it **after** the transfer, not before. If the transfer fails you want the
ledger still showing them owed.

### Check the numbers have not drifted

    python3 model/unit_economics.py
    python3 model/ad_pricing.py

If real credit spend or real operator minutes have moved away from the
assumptions, change the model and re-run `python3 site/build_all.py`. Prices on
the site come from the model, so that is the whole update.

---

## Monthly

- **`python3 model/credit_price.py`** against a real top-up receipt. Dollars
  paid ÷ credits received. If it is no longer $0.0030, every margin moves.
- **Read the outcomes.** `/admin/queue` shows the response rate. Once a
  dimension has twelve samples on both sides, a sentence starts appearing on the
  brief page by itself — check that it says something you would defend.
- **Back up.** `cp -r service/data /somewhere/safe`. That is the database, the
  customers' originals and every delivered file.

---

## Things that must never happen

These are enforced in code, and the enforcement is the point — but if you find
yourself working around one, stop and ask why.

- **Never edit a photograph a client sent.** Originals are stored read-only and
  the disclosure page is only true because of it. The moment we retouch, the
  page stops containing originals and the compliance position is gone.
- **Never publish a real-estate film without its disclosure page.** The build
  refuses; do not route around it.
- **Never accept an order for a testimonial**, at any price. FTC Reviews and
  Testimonials Rule, $53,088 per violation, and disclosure does not cure it.
- **Never mark an order paid by hand.** Only a signed Stripe webhook does that.
  If money arrived and the order did not update, the webhook is misconfigured —
  fix that, because the next order will do the same thing.
- **Never put a credential in a connection profile.** It goes in
  `FLYTHROUGH_PROVIDER_TOKEN`. Profiles get committed and code-reviewed.

---

## Escalate rather than guess

- Anything involving a **lawyer's opinion** on disclosure wording.
- A customer asking for something under **Things that must never happen**.
- A provider changing its API — a `PayloadInvalid` across *every* job means the
  schema moved. Re-record it with `openart_model_form_get` before touching the
  payload builder.

---

## Where things live

    /admin/queue      render queue, outcome stats, the weekly ask button
    /admin/payouts    who is owed, and recording that they were paid
    service/data/     database, originals, deliverables, failure tracebacks
    service/data/outbox.jsonl   what mail WOULD have been sent, in dev only
