"""
PhonePe background task implementations.

Each public function maps 1:1 to a Celery task in phone_worker.py.
All functions are synchronous (matching the autorev backend's sync SQLAlchemy setup).
Tasks iterate over every app that has phonepe_enabled=True and valid credentials.
"""
import json
import logging
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import date, datetime, time as dt_time, timedelta, timezone
from uuid import uuid4

from collections import defaultdict

from sqlalchemy import and_, func, or_, select, text, tuple_
from sqlalchemy.orm import Session, joinedload

from app.api_handler.phonepe import (
    InvalidSubscriptionStateError,
    PhonePeAPIHandler,
    PhonePeException,
    TOKEN_KEY_PREFIX,
    _fetch_token,
)
from app.database import SessionLocal
from app.models.app import App
from app.models.phonepe import (
    PhonePeApp,
    PhonePeScheduledTransaction,
    PhonePeSubscription,
    PhonePeSubscriptionArchive,
    PhonePeSubscriptionTransaction,
)
from app.redis import redis_client
from app import webhooks

logger = logging.getLogger("autorev.worker")

# ── Constants ──────────────────────────────────────────────────────────────────

MAX_SCHEDULE_ATTEMPTS = 4
REATTEMPT_DELAY_HOURS = 24

# FAILED subscriptions are the dominant source of table growth (~50k/day and
# rising), and nothing reads them once they are terminal. Move them out of the
# hot table a few hours after creation rather than waiting for the next IST day,
# which used to leave a full day's failures — 51,909 rows on 2026-09-04 — sitting
# in phonepe_subscriptions and dragging every scan across them.
ARCHIVE_FAILED_AFTER_HOURS = 6
ARCHIVE_BATCH_SIZE = 5000
# Cap the work per run so a backlog drains over several runs instead of holding
# one long transaction against the primary.
ARCHIVE_MAX_ROWS_PER_RUN = 200_000

# _sync_subscription_state polls PhonePe once per non-terminal subscription. The
# setup order created in setup_subscription carries expireAt = now + 10 minutes,
# so a subscription still sitting in INITIATED long after that can never become
# ACTIVE and every poll of it is a wasted HTTP round trip. Without a bound the
# task's workload only ever grows: on 2026-09-10 a client retry storm left 102,862
# rows matching, which one 10-minute run cannot possibly poll. 24h is a generous
# margin over the 10-minute order expiry.
SYNC_STATE_MAX_AGE_HOURS = 24
# Hard ceiling per run so one bad day cannot wedge the worker (and, through it,
# the connection pool). Newest first: a fresh setup is the one a user is waiting on.
SYNC_STATE_MAX_ROWS_PER_RUN = 20000
# The sweep is pure I/O wait — ~59ms per PhonePe status call on a kept-alive
# connection, and nothing between calls depends on the previous one. Running them
# sequentially meant 2,000 rows took ~272s. Threads (not processes) are the right
# tool: the GIL is released during socket waits. Kept deliberately modest to stay
# polite to PhonePe's API rather than maximising local throughput.
PHONEPE_POLL_CONCURRENCY = 12

# The state sweep runs one pass per entry, in order, and SYNC_STATE_MAX_ROWS_PER_RUN
# is divided evenly between them. An even share stops the first pass starving the
# later ones: the INITIATED and ACTIVATION_IN_PROGRESS backlogs are both far larger
# than the budget, so strict priority meant ACTIVATION_IN_PROGRESS was never polled.
# A pass that does not use its share leaves the remainder to the passes after it.
#
# Each entry is (states, apply_age_cutoff). The first pass is exempt from
# SYNC_STATE_MAX_AGE_HOURS: that bound exists for abandoned setups whose 10-minute
# order has expired, but these are live mandates with something in flight — the same
# reasoning as SYNC_TXN_MAX_ROWS_PER_RUN's missing cut-off. Bounded by age they would
# never be polled at all; when this pass was added, 8 of the 9 rows sitting in these
# states were already older than 24h.
#
# INTEROP_IN_PROGRESS joins that pass rather than sitting with ACTIVATION_IN_PROGRESS:
# it was found in no pass at all, so nothing ever polled it, while PhonePe had already
# moved the mandate to ACTIVE. A subscription stuck outside ACTIVE never gets a
# scheduled payment, so the payer is simply never billed. Its volume is a single row,
# and the first pass is the one place a row cannot be starved by a larger backlog.
#
# The first pass runs first precisely because its backlog is tiny: the share it leaves
# unused rolls forward to the two large passes, whereas running it last would strand
# a third of the budget on a handful of rows. INITIATED still precedes
# ACTIVATION_IN_PROGRESS.
SYNC_STATE_PASSES = (
    (["REVOKE_IN_PROGRESS", "CANCEL_IN_PROGRESS", "PAUSE_IN_PROGRESS", "INTEROP_IN_PROGRESS"], False),
    (["INITIATED"], True),
    (["ACTIVATION_IN_PROGRESS"], True),
)

# Redemption polling is capped per run purely to bound how long one run takes;
# fairness is handled by ordering on last_polled_at, so a backlog larger than
# this cap still gets covered completely, just over more runs. Measured at
# 5-6ms per transaction (concurrency 12), 30,000 is about three minutes against
# an hourly schedule.
#
# Deliberately no age cut-off here — unlike an abandoned INITIATED subscription, a
# transaction stuck at PENDING is real money in flight and must keep being polled
# until PhonePe gives it a terminal state.
SYNC_TXN_MAX_ROWS_PER_RUN = 30000

# The notify sweep fires one PhonePe call per due row and has run for 2h27m on a
# 7,500-row backlog. Beat re-fires it hourly regardless, so three executions once
# overlapped: each selected the same SCHEDULED rows (the state only flips after the
# call returns) and each minted its own merchantOrderId, so PhonePe received the
# same subscription notified three times and rejected the extras with "recurring
# transaction limit is breached". The lock makes the task single-flight; the TTL is
# only a backstop for a killed process, since the lock is released in a finally.
NOTIFY_LOCK_KEY = "lock:phonepe-notify-redemption-due"
NOTIFY_LOCK_TTL_SECONDS = 3 * 60 * 60
# Same reasoning as PHONEPE_POLL_CONCURRENCY: the sweep is pure I/O wait, and this
# is deliberately polite to PhonePe rather than maximising local throughput.
NOTIFY_CONCURRENCY = 12

# A payer who re-runs setup ends up with several live mandates on one number and is
# debited once per mandate. This sweep keeps one and revokes the rest, per app.
REVOKE_DUPES_LOCK_KEY = "lock:phonepe-revoke-duplicate-subscriptions"
REVOKE_DUPES_LOCK_TTL_SECONDS = 60 * 60
# Bounded per run for the same reason as the other sweeps: drain over several runs
# rather than hold one long transaction against a few thousand PhonePe calls.
REVOKE_DUPES_MAX_GROUPS_PER_RUN = 1000
REVOKE_DUPES_CONCURRENCY = 12
# Which mandate survives a duplicate group:
#   "paid_first" — the one that has actually collected, newest breaking ties.
#   "newest"     — the most recently created one, regardless of billing history.
# "paid_first": of the 2,212 duplicates found when this was written, 157 older rows
# had collected payments while the newer row on the same number had collected
# nothing. Keeping the newest there would cancel a proven billing mandate in favour
# of an unproven one. Where no member has collected — 2,025 of the groups — this
# falls through to the newest, which is the same choice "newest" would make.
REVOKE_DUPES_KEEP = "paid_first"

# The retry phase of _sync_scheduled_transactions is sequential by design — each
# attempt moves real money — so a large retry queue can outlast the hourly beat
# interval. Without this lock two runs would select the same IN_PROGRESS rows and
# debit them twice, exactly the failure the notify sweep hit.
SYNC_SCHED_LOCK_KEY = "lock:phonepe-sync-scheduled-transactions"
SYNC_SCHED_LOCK_TTL_SECONDS = 3 * 60 * 60

# PAUSED is swept once a day rather than joining SYNC_STATE_PASSES, which runs every
# five minutes. Nothing about a pause is time-critical, and a mandate un-pauses at most
# once per pause — folding PAUSED into the frequent sweep would spend tens of thousands of
# PhonePe calls a day to catch a handful of transitions.
SYNC_PAUSED_MAX_ROWS_PER_RUN = 20000

IST = timezone(timedelta(hours=5, minutes=30))

# PhonePe may only be triggered during these IST windows (night/morning span midnight)
NON_PEAK_WINDOWS_IST = [
    (dt_time(21, 31), dt_time(23, 59, 59)),   # 09:31 PM – midnight
    (dt_time(0, 0),   dt_time(9, 59)),         # midnight – 09:59 AM
    (dt_time(13, 1),  dt_time(16, 59)),        # 01:01 PM – 04:59 PM
]

# ── Utilities ──────────────────────────────────────────────────────────────────

def _is_non_peak_hour() -> bool:
    t = datetime.now(timezone.utc).astimezone(IST).time()
    return any(start <= t <= end for start, end in NON_PEAK_WINDOWS_IST)


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _today_end_ms() -> int:
    """Epoch ms for end of today in IST — used to find payments due today or earlier."""
    IST = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(IST).date()
    eod = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=IST)
    return int(eod.timestamp() * 1000)


def _date_to_epoch_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def _epoch_ms_to_date(ms: int) -> date:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()


def _next_payment_date(ref: date, frequency: str, trail_days: int = 0) -> date | None:
    from dateutil.relativedelta import relativedelta

    if trail_days > 0:
        return ref + timedelta(days=trail_days)

    offsets = {
        "DAILY":       timedelta(days=1),
        "WEEKLY":      timedelta(weeks=1),
        "FORTNIGHTLY": timedelta(weeks=2),
        "MONTHLY":     relativedelta(months=1),
        "BIMONTHLY":   relativedelta(months=2),
        "QUARTERLY":   relativedelta(months=3),
        "HALFYEARLY":  relativedelta(months=6),
        "YEARLY":      relativedelta(years=1),
        "ON_DEMAND":   None,
    }
    offset = offsets.get(frequency)
    if offset is None:
        return None
    return ref + offset


def _extract_transaction_id(response: dict) -> str | None:
    """
    PhonePe's own payment transaction id only appears in paymentDetails once the
    redemption reaches a terminal state; before that, fall back to the order id
    so support can still look the attempt up on PhonePe's dashboard.
    """
    for detail in response.get("paymentDetails") or []:
        if detail.get("transactionId"):
            return detail["transactionId"]
    return response.get("orderId")


def _get_handler(app_id: str, detail: PhonePeApp) -> PhonePeAPIHandler:
    """Build a PhonePeAPIHandler, pre-loading any cached token from Redis."""
    handler = PhonePeAPIHandler(
        app_id=detail.app_id,
        client_id=detail.phonepe_client_id,
        client_secret=detail.phonepe_client_secret,
        environment=detail.phonepe_environment or "UAT",
        custom=True,
    )
    cached = redis_client.get(f"{TOKEN_KEY_PREFIX}{app_id}")
    if cached:
        token_data = json.loads(cached)
        handler.access_token = token_data.get("access_token")
        handler.expires_at = token_data.get("expires_at")
    return handler


def _resync_after_invalid_state(db: Session, handler: PhonePeAPIHandler, sub: PhonePeSubscription, sched: PhonePeScheduledTransaction) -> None:
    """
    PhonePe rejected a redemption call because its view of the subscription state
    disagrees with ours (e.g. the payer paused/revoked the mandate on their side).
    Refetch the real state and cancel the scheduled transaction if it's no longer ACTIVE,
    so we stop retrying a redemption PhonePe will never accept.
    """
    try:
        remote = handler.subscription_status(sub.id)
    except Exception as sync_err:
        logger.error(f"{sched.id}: failed to resync subscription status after invalid-state error: {sync_err}")
        return

    remote_state = remote.get("state", sub.state)
    logger.warning(f"{sched.id}: PhonePe reports invalid subscription state; local={sub.state} remote={remote_state}")
    sub.state = remote_state
    db.add(sub)

    if remote_state != "ACTIVE":
        sched.state = "CANCELLED"
        db.add(sched)
        sub.last_payment_status = "CANCELLED"
        db.add(sub)
        logger.info(f"{sched.id}: subscription is {remote_state} on PhonePe, cancelling scheduled transaction")
    else:
        logger.warning(f"{sched.id}: PhonePe still reports ACTIVE despite invalid-state error, leaving SCHEDULED for manual review")

    db.commit()

    # One of the few places an ACTIVE mandate is discovered to be paused or
    # revoked: nothing polls ACTIVE subscriptions, so the rejected redemption is
    # how we find out.
    _dispatch_state_webhooks(db, [sub.id])


def _get_all_phonepe_apps(db: Session) -> list[tuple[App, PhonePeApp]]:
    """Return (App, PhonePeApp) for every enabled app that has credentials."""
    rows = (
        db.query(App, PhonePeApp)
        .join(PhonePeApp, PhonePeApp.app_id == App.id)
        .filter(
            App.enabled == True,
            App.phonepe_enabled == True,
            PhonePeApp.phonepe_client_id.isnot(None),
            PhonePeApp.phonepe_client_secret.isnot(None),
        )
        .all()
    )
    return rows


def _has_phonepe_apps() -> bool:
    """True when at least one enabled app has PhonePe turned on with credentials."""
    db = SessionLocal()
    try:
        return bool(_get_all_phonepe_apps(db))
    finally:
        db.close()


# ── Tasks ──────────────────────────────────────────────────────────────────────

def _fetch_one_state(sub_id: str, handler: PhonePeAPIHandler) -> tuple[str, str | None, str | None]:
    """Fetch one subscription's remote state. Runs on a worker thread: no DB access."""
    try:
        response = handler.subscription_status(sub_id)
        return sub_id, response.get("state"), None
    except Exception as e:
        return sub_id, None, str(e)


def _build_handlers(app_detail_map: dict) -> dict:
    """One PhonePeAPIHandler per app, with its token warmed on this thread.

    _get_handler pre-loads the cached token from Redis; the probe only fires when
    it is missing or expired, so a refresh happens once here rather than several
    pool threads racing on it mid-sweep.
    """
    handlers: dict[str, PhonePeAPIHandler] = {}
    for app_id, (_, detail) in app_detail_map.items():
        handler = _get_handler(app_id, detail)
        if not handler.access_token or (handler.expires_at and time.time() >= handler.expires_at):
            try:
                handler.subscription_status("autorev-token-warmup")
            except Exception:
                pass  # the call is only here to populate the access token
        handlers[app_id] = handler
    return handlers


def _poll_states(db, states: list[str], limit: int, cutoff, app_detail_map: dict, handlers: dict) -> int:
    """Poll PhonePe for one group of states and apply the results. Returns rows polled.

    `cutoff` of None polls the group regardless of age — see SYNC_STATE_PASSES.

    PhonePe calls run on a thread pool; every database read and write happens on
    the calling thread, so no Session is ever touched concurrently.
    """
    q = (
        db.query(PhonePeSubscription)
        .filter(PhonePeSubscription.state.in_(states))
        .filter(PhonePeSubscription.app_id.in_(app_detail_map.keys()))
    )
    if cutoff is not None:
        q = q.filter(PhonePeSubscription.created_at >= cutoff)
    subs = (
        q.order_by(PhonePeSubscription.created_at.desc())
        .limit(limit)
        .all()
    )
    label = "/".join(states)
    logger.info(f"[{label}] {len(subs)} subscriptions to poll (budget {limit})")
    if not subs:
        return 0

    # Snapshot what the update pass needs, so ORM objects are never read from
    # another thread.
    snapshot = {
        sub.id: (sub.app_id, sub.state, sub.created_at, sub.frequency, sub.trail_days or 0)
        for sub in subs
    }

    started = time.monotonic()
    results: list[tuple[str, str | None, str | None]] = []
    with ThreadPoolExecutor(max_workers=PHONEPE_POLL_CONCURRENCY) as pool:
        futures = [
            pool.submit(_fetch_one_state, sub_id, handlers[snap[0]])
            for sub_id, snap in snapshot.items()
            if snap[0] in handlers
        ]
        for done, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if done % 500 == 0:
                logger.info(f"  [{label}] polled {done}/{len(futures)} in {time.monotonic() - started:.1f}s")

    elapsed = time.monotonic() - started
    logger.info(
        f"[{label}] polled {len(results)} in {elapsed:.1f}s "
        f"({elapsed / max(len(results), 1) * 1000:.0f}ms/sub at concurrency {PHONEPE_POLL_CONCURRENCY})"
    )

    updates = []
    changed: list[str] = []
    errors = 0
    for sub_id, new_state, err in results:
        if err:
            errors += 1
            logger.error(f"{sub_id}: error syncing state: {err}")
            continue

        _, old_state, created_at, frequency, trail_days = snapshot[sub_id]
        state = new_state or old_state
        change: dict = {"id": sub_id}

        if state != old_state:
            logger.info(f"{sub_id}: {old_state} → {state}")
            change["state"] = state

        if state == "ACTIVE":
            next_d = _next_payment_date(created_at.date(), frequency, trail_days)
            if next_d:
                change["next_payment_date"] = _date_to_epoch_ms(next_d)
                logger.info(f"{sub_id}: ACTIVE, next_payment_date set to {next_d}")

            # A non-trial signup pays its full amount during setup. Credit that the
            # moment the mandate goes ACTIVE rather than leaving it to the 6-hourly
            # _sync_total_payments recount, which otherwise shows the payer "0
            # payments" for up to six hours after they have paid. Only on the
            # transition, so a later recurring count is never clobbered; the recount
            # stays authoritative and applies the same rule.
            if state != old_state and (trail_days or 0) == 0:
                change["total_payments"] = 1

        if len(change) > 1:
            updates.append(change)
        if state != old_state:
            changed.append(sub_id)

    for i in range(0, len(updates), 500):
        batch = updates[i : i + 500]
        try:
            db.bulk_update_mappings(PhonePeSubscription, batch)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"batch update of {len(batch)} subscriptions failed: {e}")

    # This pass polls the *_IN_PROGRESS trio, so PAUSE_IN_PROGRESS → PAUSED and
    # REVOKE_IN_PROGRESS → REVOKED land here alongside the activations.
    _dispatch_state_webhooks(db, changed)

    logger.info(f"[{label}] updated {len(updates)}, {errors} errors")
    return len(results)


def _sync_subscription_state():
    """
    For every non-terminal subscription across all apps — the revoke/cancel/pause
    in-progress trio, then INITIATED, then ACTIVATION_IN_PROGRESS — fetch the
    PhonePe status and update local state.
    If a subscription just became ACTIVE and has no next_payment_date, compute it.

    Each pass in SYNC_STATE_PASSES gets an equal share of
    SYNC_STATE_MAX_ROWS_PER_RUN, and whatever a pass leaves unused rolls forward to
    the next one. Passes flagged there opt out of the SYNC_STATE_MAX_AGE_HOURS bound.
    """
    logger.info("Starting: _sync_subscription_state")
    db = SessionLocal()
    try:
        app_pairs = _get_all_phonepe_apps(db)
        app_detail_map = {detail.app_id: (app, detail) for app, detail in app_pairs}
        if not app_detail_map:
            logger.info("No PhonePe-enabled apps with credentials, nothing to sync")
            return

        cutoff = datetime.now(timezone.utc) - timedelta(hours=SYNC_STATE_MAX_AGE_HOURS)
        handlers = _build_handlers(app_detail_map)

        n_passes = len(SYNC_STATE_PASSES)
        share = SYNC_STATE_MAX_ROWS_PER_RUN // n_passes
        polled = 0

        for idx, (states, apply_cutoff) in enumerate(SYNC_STATE_PASSES):
            # This pass may use its own share plus anything earlier passes left
            # behind, while still reserving a full share for each pass after it.
            passes_after = n_passes - idx - 1
            budget = SYNC_STATE_MAX_ROWS_PER_RUN - polled - (share * passes_after)
            if budget <= 0:
                logger.warning(f"[{'/'.join(states)}] no budget left this run, skipping")
                continue
            polled += _poll_states(
                db, states, budget, cutoff if apply_cutoff else None, app_detail_map, handlers
            )

        logger.info(
            f"Polled {polled} subscriptions in total "
            f"(budget {SYNC_STATE_MAX_ROWS_PER_RUN}, {share} per pass across {n_passes} passes)"
        )
    finally:
        db.close()
        logger.info("Completed: _sync_subscription_state")


@contextmanager
def _single_flight(key: str, ttl: int):
    """Yield True only to the one caller holding `key`; others get False.

    Released in the finally, with the TTL as a backstop if the process is killed.
    The token guards against releasing a lock that has already expired and been
    taken by the next run.
    """
    token = uuid4().hex
    acquired = False
    try:
        acquired = bool(redis_client.set(key, token, nx=True, ex=ttl))
        yield acquired
    finally:
        if acquired:
            try:
                current = redis_client.get(key)
                if current is not None and (current == token or current == token.encode()):
                    redis_client.delete(key)
            except Exception as e:
                logger.error(f"failed to release lock {key}: {e}")


def _notify_one(payload: dict, handler: PhonePeAPIHandler):
    """Fire one notify. Runs on a worker thread: no DB access in here."""
    try:
        return payload["merchantOrderId"], handler.notify_redemption(payload), None
    except Exception as e:
        return payload["merchantOrderId"], None, e


def _sync_paused_state():
    """Poll PAUSED subscriptions daily and resume the ones PhonePe has un-paused.

    Before this existed nothing moved PAUSED → ACTIVE: neither SYNC_STATE_PASSES nor
    the API path's IN_PROGRESS_STATES covers PAUSED, so a paused mandate stayed paused
    forever and was never billed again.

    This cannot reuse _poll_states. That helper recomputes next_payment_date from
    created_at whenever it sees ACTIVE, which for a mandate paused months ago yields a
    date in the past; _advance_payment_dates then moves such a date forward only one
    period per 6-hourly run, and only once last_payment_status is COMPLETED/FAILED, so
    the payer would first be billed for periods that elapsed while they were paused.

    On resume the next payment is therefore set one period from *today*. The payer gets
    no surprise charge on the day their pause lifts and no back-billing. If billing
    should instead resume immediately, use `today` directly rather than passing it
    through _next_payment_date.
    """
    logger.info("Starting: _sync_paused_state")
    db = SessionLocal()
    try:
        app_pairs = _get_all_phonepe_apps(db)
        app_detail_map = {detail.app_id: (app, detail) for app, detail in app_pairs}
        if not app_detail_map:
            logger.info("No PhonePe-enabled apps with credentials, nothing to sync")
            return

        # No age cut-off: a pause is open-ended, so the oldest rows are exactly the
        # ones most likely to have been un-paused since the last sweep.
        subs = (
            db.query(PhonePeSubscription)
            .filter(
                PhonePeSubscription.state == "PAUSED",
                PhonePeSubscription.app_id.in_(app_detail_map.keys()),
            )
            .order_by(PhonePeSubscription.created_at.desc())
            .limit(SYNC_PAUSED_MAX_ROWS_PER_RUN)
            .all()
        )
        logger.info(f"[PAUSED] {len(subs)} subscriptions to poll")
        if not subs:
            return

        handlers = _build_handlers(app_detail_map)
        # Snapshot before threading: ORM objects are never read off the calling thread.
        snapshot = {sub.id: (sub.app_id, sub.frequency) for sub in subs}

        started = time.monotonic()
        results: list[tuple[str, str | None, str | None]] = []
        with ThreadPoolExecutor(max_workers=PHONEPE_POLL_CONCURRENCY) as pool:
            futures = [
                pool.submit(_fetch_one_state, sub_id, handlers[snap[0]])
                for sub_id, snap in snapshot.items()
                if snap[0] in handlers
            ]
            for done, future in enumerate(as_completed(futures), 1):
                results.append(future.result())
                if done % 500 == 0:
                    logger.info(f"  [PAUSED] polled {done}/{len(futures)} in {time.monotonic() - started:.1f}s")

        elapsed = time.monotonic() - started
        logger.info(
            f"[PAUSED] polled {len(results)} in {elapsed:.1f}s "
            f"({elapsed / max(len(results), 1) * 1000:.0f}ms/sub at concurrency {PHONEPE_POLL_CONCURRENCY})"
        )

        today = datetime.now(IST).date()
        updates = []
        changed: list[str] = []
        resumed = errors = 0
        for sub_id, new_state, err in results:
            if err:
                errors += 1
                logger.error(f"{sub_id}: error syncing paused state: {err}")
                continue
            if not new_state or new_state == "PAUSED":
                continue

            _, frequency = snapshot[sub_id]
            change: dict = {"id": sub_id, "state": new_state}
            logger.info(f"{sub_id}: PAUSED → {new_state}")

            changed.append(sub_id)

            if new_state == "ACTIVE":
                resumed += 1
                # trail_days deliberately left at its default 0: any trial ended long
                # before the pause did.
                next_d = _next_payment_date(today, frequency)
                if next_d:
                    change["next_payment_date"] = _date_to_epoch_ms(next_d)
                    logger.info(f"{sub_id}: resumed, next_payment_date set to {next_d}")
                else:
                    # ON_DEMAND has no schedule to resume.
                    logger.info(f"{sub_id}: resumed, {frequency} has no next_payment_date")

            updates.append(change)

        for i in range(0, len(updates), 500):
            batch = updates[i : i + 500]
            try:
                db.bulk_update_mappings(PhonePeSubscription, batch)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"batch update of {len(batch)} paused subscriptions failed: {e}")

        # Every row here left PAUSED. A resume is a transition into ACTIVE, which
        # in practice already fired subscription.activated before the pause and so
        # is swallowed by the claim; the case that does send is a mandate PhonePe
        # has since revoked.
        _dispatch_state_webhooks(db, changed)

        logger.info(f"[PAUSED] updated {len(updates)} ({resumed} resumed to ACTIVE), {errors} errors")
    finally:
        db.close()
        logger.info("Completed: _sync_paused_state")


def _notify_redemption_for_due_subscriptions():
    """
    For every SCHEDULED transaction whose payment_date is today or earlier:
    call notify_redemption on PhonePe and create a subscription transaction record.
    Only runs during non-peak IST hours, and only one run at a time.
    """
    logger.info("Starting: _notify_redemption_for_due_subscriptions")
    if not _is_non_peak_hour():
        logger.info("Skipping: outside non-peak IST hours")
        return
    if not _has_phonepe_apps():
        logger.info("No PhonePe-enabled apps with credentials, nothing to notify")
        return

    with _single_flight(NOTIFY_LOCK_KEY, NOTIFY_LOCK_TTL_SECONDS) as acquired:
        if not acquired:
            logger.warning(
                "Another _notify_redemption_for_due_subscriptions run is still in flight, skipping. "
                "Overlapping runs notify the same subscription twice."
            )
            return
        _notify_due_locked()


def _notify_due_locked():
    db = SessionLocal()
    try:
        app_pairs = _get_all_phonepe_apps(db)
        app_detail_map = {detail.app_id: (app, detail) for app, detail in app_pairs}
        if not app_detail_map:
            logger.info("No PhonePe-enabled apps with credentials, nothing to notify")
            return

        due_ms = _today_end_ms()
        sched_items = (
            db.query(PhonePeScheduledTransaction)
            .join(PhonePeSubscription, PhonePeSubscription.id == PhonePeScheduledTransaction.subscription_id)
            .options(joinedload(PhonePeScheduledTransaction.subscription))
            .filter(
                PhonePeScheduledTransaction.state == "SCHEDULED",
                PhonePeScheduledTransaction.payment_date <= due_ms,
                PhonePeSubscription.app_id.in_(app_detail_map.keys()),
            )
            .all()
        )
        logger.info(f"Found {len(sched_items)} due scheduled transactions")

        if not sched_items:
            return

        # ── Phase 1a: confirm each mandate is still ACTIVE at PhonePe ─────────
        # Local state goes stale — a payer can revoke or pause on their side and we
        # only learn when a redemption is rejected with "Invalid Subscription State".
        # Notifying a dead mandate is a wasted call that PhonePe counts against us,
        # so the remote state is checked first and written back. One call per
        # subscription, not per scheduled row, since a subscription can have several.
        candidates = [s for s in sched_items if s.subscription is not None]
        handlers = {}
        for sched in candidates:
            app_id = sched.subscription.app_id
            if app_id not in handlers:
                _, detail = app_detail_map.get(app_id, (None, None))
                if detail:
                    handlers[app_id] = _get_handler(app_id, detail)

        subs_by_id = {s.subscription.id: s.subscription for s in candidates}
        to_check = [(sid, sub.app_id) for sid, sub in subs_by_id.items() if sub.app_id in handlers]

        started = time.monotonic()
        remote_state: dict[str, str] = {}
        status_errors = 0
        with ThreadPoolExecutor(max_workers=NOTIFY_CONCURRENCY) as pool:
            futures = [pool.submit(_fetch_one_state, sid, handlers[app_id]) for sid, app_id in to_check]
            for done, future in enumerate(as_completed(futures), 1):
                sid, state, err = future.result()
                if err:
                    status_errors += 1
                    logger.error(f"{sid}: status check failed: {err}")
                elif state:
                    remote_state[sid] = state
                if done % 500 == 0:
                    logger.info(f"  status-checked {done}/{len(futures)} in {time.monotonic() - started:.1f}s")

        drifted = 0
        drifted_ids: list[str] = []
        for sid, state in remote_state.items():
            sub = subs_by_id[sid]
            if state != sub.state:
                logger.info(f"{sid}: local {sub.state} → PhonePe {state}")
                sub.state = state
                drifted_ids.append(sid)
                drifted += 1
        db.commit()

        # The main detector of ACTIVE → PAUSED/REVOKED. This status check exists
        # because local state goes stale for mandates the payer changed on their
        # side, and those are exactly the transitions worth telling the customer
        # about — otherwise they only find out when a debit stops arriving.
        _dispatch_state_webhooks(db, drifted_ids)
        logger.info(
            f"Status-checked {len(to_check)} subscriptions in {time.monotonic() - started:.1f}s "
            f"({drifted} drifted, {status_errors} errors)"
        )

        # ── Phase 1b: validate and CLAIM, before a single redemption call ─────
        # The claim is the important half. Previously the row only became
        # IN_PROGRESS after its notify returned, so anything else reading the table
        # in that window still saw SCHEDULED and notified it again. Flipping the
        # state first — and committing — means a row is spoken for before any call
        # goes out. A failed call puts it back to SCHEDULED in phase 3.
        work = []
        cancelled = 0
        deferred_dupes = 0
        claimed_subs = set()
        for sched in sched_items:
            sub = sched.subscription
            # sub.state now reflects PhonePe wherever the check succeeded; where it
            # failed we fall back to the local value rather than guess.
            if not sub or sub.state != "ACTIVE":
                logger.info(f"{sched.id}: subscription not ACTIVE, cancelling")
                sched.state = "CANCELLED"
                cancelled += 1
                continue

            if sub.id not in remote_state and sub.id in subs_by_id:
                # Could not confirm with PhonePe this run. Leave it SCHEDULED and
                # try again next run rather than debit on a possibly stale ACTIVE.
                logger.warning(f"{sched.id}: unconfirmed subscription state, deferring")
                continue

            _, detail = app_detail_map.get(sub.app_id, (None, None))
            if not detail:
                logger.error(f"{sched.id}: no app detail found for app_id {sub.app_id}")
                continue

            # One notify per subscription per run. Today every subscription has a
            # single pending row, so this never fires — but nothing in the schema
            # enforces that, and two due rows for one mandate would otherwise be two
            # notifications seconds apart, which is exactly what PhonePe objects to.
            # The extra row keeps its SCHEDULED state and goes out next run.
            if sub.id in claimed_subs:
                logger.warning(f"{sched.id}: subscription {sub.id} already claimed this run, deferring")
                deferred_dupes += 1
                continue
            claimed_subs.add(sub.id)

            payload = {
                "merchantOrderId": uuid4().hex,
                "amount": sched.amount,
                "paymentFlow": {
                    "type": "SUBSCRIPTION_REDEMPTION",
                    "merchantSubscriptionId": sub.id,
                    "redemptionRetryStrategy": "STANDARD",
                    "autoDebit": True,
                },
            }
            sched.state = "IN_PROGRESS"
            sched.attempts = (sched.attempts or 0) + 1
            sub.last_payment_status = "PENDING"
            work.append((sched, sub, detail, payload))

        db.commit()
        logger.info(
            f"Claimed {len(work)} rows for notify, cancelled {cancelled} inactive, "
            f"deferred {deferred_dupes} same-subscription duplicates"
        )
        if not work:
            return

        # ── Phase 2: the redemption calls, in parallel. No DB access in here ──
        # `handlers` was built in phase 1a and covers every app_id reaching here.
        started = time.monotonic()
        results: dict[str, tuple] = {}
        with ThreadPoolExecutor(max_workers=NOTIFY_CONCURRENCY) as pool:
            futures = [
                pool.submit(_notify_one, payload, handlers[sub.app_id])
                for _sched, sub, _detail, payload in work
            ]
            for done, future in enumerate(as_completed(futures), 1):
                order_id, response, err = future.result()
                results[order_id] = (response, err)
                if done % 500 == 0:
                    logger.info(f"  notified {done}/{len(futures)} in {time.monotonic() - started:.1f}s")

        elapsed = time.monotonic() - started
        logger.info(
            f"Notified {len(results)} in {elapsed:.1f}s "
            f"({elapsed / max(len(results), 1) * 1000:.0f}ms/call at concurrency {NOTIFY_CONCURRENCY})"
        )

        # ── Phase 3: apply the results ────────────────────────────────────────
        ok = released = 0
        invalid_state = []
        for i, (sched, sub, detail, payload) in enumerate(work, 1):
            order_id = payload["merchantOrderId"]
            response, err = results.get(order_id, (None, RuntimeError("no result returned")))

            # DUPLICATE_REQUEST_ID is benign — the notification went through already.
            if err is None or (isinstance(err, PhonePeException) and err.code == "DUPLICATE_REQUEST_ID"):
                db.add(PhonePeSubscriptionTransaction(
                    id=order_id,
                    subscription_id=sub.id,
                    scheduled_transaction_id=sched.id,
                    amount=sched.amount,
                    payment_due_date=sched.payment_date,
                    state="INITIATED",
                    request_payload=payload,
                    response_payload=response,
                    transaction_id=_extract_transaction_id(response) if response else None,
                ))
                ok += 1
            else:
                # The call never landed, so release the claim and let the next run
                # pick it up — restoring exactly what the sequential code did.
                sched.state = "SCHEDULED"
                sched.attempts = max((sched.attempts or 1) - 1, 0)
                released += 1
                if isinstance(err, InvalidSubscriptionStateError):
                    invalid_state.append((sched, sub, detail))
                else:
                    logger.error(f"{sched.id}: PhonePe error: {err}")

            # Commit in batches so one bad row cannot roll back the whole sweep and
            # leave thousands of rows claimed with no transaction to show for it.
            if i % 500 == 0:
                db.commit()
        db.commit()
        logger.info(f"Applied: {ok} notified, {released} released back to SCHEDULED")

        # Each of these needs another PhonePe call; few enough to do serially.
        for sched, sub, detail in invalid_state:
            try:
                _resync_after_invalid_state(db, _get_handler(sub.app_id, detail), sub, sched)
            except Exception as e:
                logger.error(f"{sched.id}: resync after invalid state failed: {e}")
                db.rollback()
    finally:
        db.close()
        logger.info("Completed: _notify_redemption_for_due_subscriptions")


def _fetch_one_redemption(txn_id: str, handler: PhonePeAPIHandler) -> tuple[str, dict | None, str | None]:
    """Fetch one redemption order's status. Runs on a worker thread: no DB access."""
    try:
        return txn_id, handler.redemption_order_status(txn_id), None
    except Exception as e:
        return txn_id, None, str(e)


def _sync_redemption_txn_state():
    """
    For every non-terminal PhonePeSubscriptionTransaction, fetch the redemption
    order status from PhonePe and update local state.

    As in _sync_subscription_state, the PhonePe calls run on a thread pool while
    every database read and write stays on this thread.
    """
    logger.info("Starting: _sync_redemption_txn_state")
    db = SessionLocal()
    try:
        app_pairs = _get_all_phonepe_apps(db)
        app_detail_map = {detail.app_id: (app, detail) for app, detail in app_pairs}
        if not app_detail_map:
            logger.info("No PhonePe-enabled apps with credentials, nothing to sync")
            return

        terminal = {"FAILED", "COMPLETED", "REVOKED", "CANCELLED"}
        # app_id comes back from the join, so the per-transaction
        # db.get(PhonePeSubscription, ...) lookup this loop used to do is gone.
        # Half the budget from each end of the backlog. A single newest-first pass
        # starves the tail the moment the backlog outgrows the cap: rows older than
        # the newest SYNC_TXN_MAX_ROWS_PER_RUN are never selected again, and new
        # rows keep pushing them further out. That had left 36,625 transactions —
        # every 15 Sep payment among them — permanently unpolled while PhonePe had
        # long since settled them. Newest-first still gets its share so a payment
        # someone is actively waiting on stays fresh.
        base = (
            db.query(
                PhonePeSubscriptionTransaction.id,
                PhonePeSubscriptionTransaction.state,
                PhonePeSubscription.app_id,
            )
            .join(PhonePeSubscription, PhonePeSubscription.id == PhonePeSubscriptionTransaction.subscription_id)
            .filter(
                PhonePeSubscriptionTransaction.state.not_in(terminal),
                PhonePeSubscription.app_id.in_(app_detail_map.keys()),
            )
        )
        # Least-recently-polled first, never-polled (NULL) ahead of everything.
        # Two-ended selection on created_at came before this and starved: the
        # oldest rows are the ones PhonePe never resolves, so polling oldest-first
        # re-read the same block every run and the middle was never reached once
        # the backlog outgrew the cap. Ordering by when we last asked rotates
        # through the whole backlog however large it is, and NULLS FIRST still
        # gives a brand-new transaction its answer on the very next run.
        rows = (
            base.order_by(PhonePeSubscriptionTransaction.last_polled_at.asc().nullsfirst())
            .limit(SYNC_TXN_MAX_ROWS_PER_RUN)
            .all()
        )
        backlog = base.count()
        logger.info(
            f"Found {len(rows)} non-terminal transactions to sync "
            f"(backlog {backlog}, oldest-polled first)"
        )
        if not rows:
            return

        current_state = {r.id: r.state for r in rows}

        handlers: dict[str, PhonePeAPIHandler] = {}
        for app_id, (_, detail) in app_detail_map.items():
            handler = _get_handler(app_id, detail)
            if not handler.access_token or (handler.expires_at and time.time() >= handler.expires_at):
                try:
                    handler.subscription_status("autorev-token-warmup")
                except Exception:
                    pass  # the call is only here to populate the access token
            handlers[app_id] = handler

        started = time.monotonic()
        results: list[tuple[str, dict | None, str | None]] = []
        with ThreadPoolExecutor(max_workers=PHONEPE_POLL_CONCURRENCY) as pool:
            futures = [
                pool.submit(_fetch_one_redemption, r.id, handlers[r.app_id])
                for r in rows
                if r.app_id in handlers
            ]
            for done, future in enumerate(as_completed(futures), 1):
                results.append(future.result())
                if done % 500 == 0:
                    logger.info(f"  polled {done}/{len(futures)} in {time.monotonic() - started:.1f}s")

        elapsed = time.monotonic() - started
        logger.info(
            f"Polled {len(results)} transactions in {elapsed:.1f}s "
            f"({elapsed / max(len(results), 1) * 1000:.0f}ms/txn at concurrency {PHONEPE_POLL_CONCURRENCY})"
        )

        updates = []
        failed_ids: set[str] = set()
        errors = 0
        for txn_id, response, err in results:
            if err:
                errors += 1
                failed_ids.add(txn_id)
                logger.error(f"{txn_id}: error syncing: {err}")
                continue
            new_state = (response or {}).get("state")
            if new_state and new_state != current_state[txn_id]:
                updates.append({
                    "id": txn_id,
                    "state": new_state,
                    "response_payload": response,
                    "transaction_id": _extract_transaction_id(response),
                })
                logger.info(f"{txn_id}: state → {new_state}")

        for i in range(0, len(updates), 500):
            batch = updates[i : i + 500]
            try:
                db.bulk_update_mappings(PhonePeSubscriptionTransaction, batch)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"batch update of {len(batch)} transactions failed: {e}")

        # Stamp everything that was asked about, changed or not. Only stamping
        # the ones that moved would leave the unchanged rows — the majority —
        # permanently at the front of the queue, recreating the starvation this
        # ordering exists to prevent. Rows whose poll errored are left unstamped
        # so they are retried first next run.
        polled = [r.id for r in rows if r.id not in failed_ids]
        now = datetime.now(timezone.utc)
        for i in range(0, len(polled), 1000):
            chunk = polled[i : i + 1000]
            try:
                db.query(PhonePeSubscriptionTransaction).filter(
                    PhonePeSubscriptionTransaction.id.in_(chunk)
                ).update({"last_polled_at": now}, synchronize_session=False)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"stamping {len(chunk)} polled transactions failed: {e}")

        logger.info(
            f"Updated {len(updates)} transactions, {errors} errors, "
            f"{len(polled)} stamped as polled"
        )
    finally:
        db.close()
        logger.info("Completed: _sync_redemption_txn_state")


def _latest_txn_by_sched(db: Session, sched_ids: list[str]) -> dict:
    """Newest linked transaction for each scheduled transaction, in one query per chunk.

    Replaces a per-row ORDER BY created_at DESC LIMIT 1, which was one round trip
    to the database for every IN_PROGRESS row.
    """
    latest: dict = {}
    for i in range(0, len(sched_ids), 1000):
        chunk = sched_ids[i : i + 1000]
        rows = (
            db.query(PhonePeSubscriptionTransaction)
            .filter(PhonePeSubscriptionTransaction.scheduled_transaction_id.in_(chunk))
            .distinct(PhonePeSubscriptionTransaction.scheduled_transaction_id)
            .order_by(
                PhonePeSubscriptionTransaction.scheduled_transaction_id,
                PhonePeSubscriptionTransaction.created_at.desc(),
            )
            .all()
        )
        for t in rows:
            latest[t.scheduled_transaction_id] = t
    return latest


def _sync_scheduled_transactions():
    """
    For every IN_PROGRESS scheduled transaction:
    - Latest linked txn COMPLETED → mark COMPLETED, bump total_payments
    - Latest linked txn FAILED, attempts < MAX, past reattempt delay, non-peak → retry
    - Latest linked txn FAILED, attempts >= MAX → mark FAILED

    Bookkeeping happens first, in bulk. The retry path issues a real debit, so it
    stays sequential with its own commit per attempt — see the note below.

    Single-flight, for the same reason as the notify sweep: the retry phase is
    sequential and can run for tens of minutes on a large queue, while beat re-fires
    this hourly. Two overlapping runs would both select the same IN_PROGRESS rows
    and both debit them, since attempts is only incremented after the call returns.
    """
    logger.info("Starting: _sync_scheduled_transactions")
    if not _has_phonepe_apps():
        logger.info("No PhonePe-enabled apps with credentials, nothing to sync")
        return
    with _single_flight(SYNC_SCHED_LOCK_KEY, SYNC_SCHED_LOCK_TTL_SECONDS) as acquired:
        if not acquired:
            logger.warning(
                "Another _sync_scheduled_transactions run is still in flight, skipping. "
                "Overlapping runs would retry the same debit twice."
            )
            return
        _sync_scheduled_locked()


def _sync_scheduled_locked():
    db = SessionLocal()
    try:
        app_pairs = _get_all_phonepe_apps(db)
        app_detail_map = {detail.app_id: (app, detail) for app, detail in app_pairs}
        if not app_detail_map:
            logger.info("No PhonePe-enabled apps with credentials, nothing to sync")
            return

        # joinedload pulls each row's subscription in the same query; the loop used
        # to call db.get(PhonePeSubscription, ...) once per scheduled transaction.
        sched_items = (
            db.query(PhonePeScheduledTransaction)
            .join(PhonePeSubscription, PhonePeSubscription.id == PhonePeScheduledTransaction.subscription_id)
            .options(joinedload(PhonePeScheduledTransaction.subscription))
            .filter(
                PhonePeScheduledTransaction.state == "IN_PROGRESS",
                PhonePeSubscription.app_id.in_(app_detail_map.keys()),
            )
            .all()
        )
        logger.info(f"Found {len(sched_items)} IN_PROGRESS scheduled transactions")
        if not sched_items:
            return

        latest_by_sched = _latest_txn_by_sched(db, [s.id for s in sched_items])

        # ── Phase 1: bookkeeping only, no external calls ──────────────────────
        retry_candidates = []
        changed = 0
        for sched in sched_items:
            sub = sched.subscription
            if not sub:
                logger.error(f"{sched.id}: subscription not found, cancelling")
                sched.state = "CANCELLED"
                changed += 1
                continue

            if sub.state != "ACTIVE":
                logger.warning(f"{sched.id}: subscription {sub.id} not ACTIVE, cancelling")
                sched.state = "CANCELLED"
                changed += 1
                continue

            latest_txn = latest_by_sched.get(sched.id)
            if not latest_txn:
                logger.warning(f"{sched.id}: no linked transactions, skipping")
                continue

            if latest_txn.state == "COMPLETED":
                sched.state = "COMPLETED"
                sub.last_payment_status = "COMPLETED"
                sub.total_payments = (sub.total_payments or 0) + 1
                changed += 1
                logger.info(f"{sched.id}: COMPLETED, total_payments={sub.total_payments}")

            elif latest_txn.state == "FAILED":
                if sched.attempts >= MAX_SCHEDULE_ATTEMPTS:
                    sched.state = "FAILED"
                    sub.last_payment_status = "FAILED"
                    changed += 1
                    logger.info(f"{sched.id}: max attempts reached, FAILED")
                elif latest_txn.created_at and (
                    datetime.now(timezone.utc) - latest_txn.created_at
                ) < timedelta(hours=REATTEMPT_DELAY_HOURS):
                    logger.info(f"{sched.id}: waiting {REATTEMPT_DELAY_HOURS}h before retry")
                elif not _is_non_peak_hour():
                    logger.info(f"{sched.id}: retry due but outside non-peak hours, skipping")
                else:
                    _, detail = app_detail_map.get(sub.app_id, (None, None))
                    if detail:
                        retry_candidates.append((sched, sub, detail))

            else:
                # Still in flight. The old code wrote and COMMITTED this on every
                # pass even when the value was already PENDING — 2,600+ redundant
                # transactions per run.
                if sub.last_payment_status != "PENDING":
                    sub.last_payment_status = "PENDING"
                    changed += 1

        try:
            db.commit()
            logger.info(f"Bookkeeping applied for {changed} rows")
        except Exception as e:
            db.rollback()
            logger.error(f"bookkeeping commit failed: {e}")
            return

        # ── Phase 2: retries. Each one debits a real mandate ──────────────────
        # Left sequential on purpose: every attempt mints a new merchantOrderId and
        # moves money, and sched.attempts gates MAX_SCHEDULE_ATTEMPTS. A per-attempt
        # commit keeps one failure from rolling back another attempt's audit row.
        logger.info(f"{len(retry_candidates)} scheduled transactions due for retry")
        for sched, sub, detail in retry_candidates:
            handler = None
            try:
                merchant_order_id = uuid4().hex
                payload = {
                    "merchantOrderId": merchant_order_id,
                    "amount": sched.amount,
                    "paymentFlow": {
                        "type": "SUBSCRIPTION_REDEMPTION",
                        "merchantSubscriptionId": sub.id,
                        "redemptionRetryStrategy": "STANDARD",
                        "autoDebit": True,
                    },
                }
                retry_txn = PhonePeSubscriptionTransaction(
                    id=merchant_order_id,
                    subscription_id=sub.id,
                    scheduled_transaction_id=sched.id,
                    amount=sched.amount,
                    payment_due_date=sched.payment_date,
                    state="PENDING",
                    request_payload=payload,
                )
                handler = _get_handler(sub.app_id, detail)
                response = handler.notify_redemption(payload)
                retry_txn.state = "INITIATED"
                retry_txn.response_payload = response
                retry_txn.transaction_id = _extract_transaction_id(response)
                db.add(retry_txn)
                sched.attempts += 1
                sub.last_payment_status = "PENDING"
                db.commit()
                logger.info(f"{sched.id}: retry attempt {sched.attempts}/{MAX_SCHEDULE_ATTEMPTS} triggered")
            except InvalidSubscriptionStateError:
                db.rollback()
                if handler is not None:
                    _resync_after_invalid_state(db, handler, sub, sched)
            except Exception as e:
                logger.error(f"{sched.id}: error: {e}")
                db.rollback()
    finally:
        db.close()
        logger.info("Completed: _sync_scheduled_transactions")


def _dupe_survivor_key(sub: PhonePeSubscription):
    """Sort key placing the mandate that should survive first. See REVOKE_DUPES_KEEP."""
    created = sub.created_at.timestamp() if sub.created_at else 0
    if REVOKE_DUPES_KEEP == "paid_first":
        return (-(sub.total_payments or 0), -created)
    return (-created, -(sub.total_payments or 0))


def _revoke_one(sub_id: str, handler: PhonePeAPIHandler):
    """Cancel one mandate at PhonePe. Runs on a worker thread: no DB access in here."""
    try:
        handler.cancel_subscription(sub_id)
        return sub_id, None
    except Exception as e:
        return sub_id, e


def _revoke_duplicate_active_subscriptions():
    """
    For a phone number holding several ACTIVE subscriptions within one app, keep one
    (see REVOKE_DUPES_KEEP) and revoke the rest at PhonePe, so the payer is debited
    once rather than once per mandate.
    """
    logger.info("Starting: _revoke_duplicate_active_subscriptions")
    if not _has_phonepe_apps():
        logger.info("No PhonePe-enabled apps with credentials, nothing to do")
        return
    with _single_flight(REVOKE_DUPES_LOCK_KEY, REVOKE_DUPES_LOCK_TTL_SECONDS) as acquired:
        if not acquired:
            logger.warning("Another _revoke_duplicate_active_subscriptions run is in flight, skipping")
            return
        _revoke_dupes_locked()


def _revoke_dupes_locked():
    db = SessionLocal()
    try:
        app_pairs = _get_all_phonepe_apps(db)
        app_detail_map = {detail.app_id: (app, detail) for app, detail in app_pairs}
        if not app_detail_map:
            logger.info("No PhonePe-enabled apps with credentials, nothing to do")
            return

        groups = (
            db.query(PhonePeSubscription.app_id, PhonePeSubscription.phone_number)
            .filter(
                PhonePeSubscription.state == "ACTIVE",
                PhonePeSubscription.app_id.in_(app_detail_map.keys()),
            )
            .group_by(PhonePeSubscription.app_id, PhonePeSubscription.phone_number)
            .having(func.count(PhonePeSubscription.id) > 1)
            .limit(REVOKE_DUPES_MAX_GROUPS_PER_RUN)
            .all()
        )
        logger.info(f"Found {len(groups)} (app, phone) groups with multiple ACTIVE subscriptions")
        if not groups:
            return

        subs = (
            db.query(PhonePeSubscription)
            .filter(
                PhonePeSubscription.state == "ACTIVE",
                tuple_(PhonePeSubscription.app_id, PhonePeSubscription.phone_number).in_(
                    [(a, p) for a, p in groups]
                ),
            )
            .all()
        )

        handlers = {}
        for sub in subs:
            if sub.app_id not in handlers:
                _, detail = app_detail_map.get(sub.app_id, (None, None))
                if detail:
                    handlers[sub.app_id] = _get_handler(sub.app_id, detail)

        # ── Confirm each member is really ACTIVE before choosing a survivor ───
        # Local state drifts, and picking a survivor from a stale view could revoke
        # a payer's only live mandate and keep one PhonePe already cancelled.
        started = time.monotonic()
        remote: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=REVOKE_DUPES_CONCURRENCY) as pool:
            futures = [
                pool.submit(_fetch_one_state, sub.id, handlers[sub.app_id])
                for sub in subs
                if sub.app_id in handlers
            ]
            for future in as_completed(futures):
                sub_id, state, err = future.result()
                if err:
                    logger.error(f"{sub_id}: status check failed: {err}")
                elif state:
                    remote[sub_id] = state

        drifted = 0
        for sub in subs:
            state = remote.get(sub.id)
            if state and state != sub.state:
                logger.info(f"{sub.id}: local {sub.state} → PhonePe {state}")
                sub.state = state
                drifted += 1
        db.commit()
        logger.info(
            f"Status-checked {len(subs)} subscriptions in {time.monotonic() - started:.1f}s ({drifted} drifted)"
        )

        # ── Choose a survivor per group, from confirmed-ACTIVE members only ───
        by_group = defaultdict(list)
        for sub in subs:
            if remote.get(sub.id) == "ACTIVE":
                by_group[(sub.app_id, sub.phone_number)].append(sub)

        to_revoke = []
        for (app_id, phone), members in by_group.items():
            if len(members) < 2:
                continue
            members.sort(key=_dupe_survivor_key)
            survivor, losers = members[0], members[1:]
            logger.info(
                f"{phone}: keeping {survivor.id} (created {survivor.created_at}, "
                f"{survivor.total_payments or 0} payments), revoking {len(losers)}"
            )
            to_revoke.extend(losers)

        logger.info(f"{len(to_revoke)} duplicate mandates to revoke across {len(by_group)} numbers")
        if not to_revoke:
            return

        # ── Revoke at PhonePe, in parallel ───────────────────────────────────
        started = time.monotonic()
        results: dict[str, Exception | None] = {}
        with ThreadPoolExecutor(max_workers=REVOKE_DUPES_CONCURRENCY) as pool:
            futures = [pool.submit(_revoke_one, sub.id, handlers[sub.app_id]) for sub in to_revoke]
            for done, future in enumerate(as_completed(futures), 1):
                sub_id, err = future.result()
                results[sub_id] = err
                if done % 200 == 0:
                    logger.info(f"  revoked {done}/{len(futures)} in {time.monotonic() - started:.1f}s")

        revoked = failed = 0
        revoked_ids: list[str] = []
        for i, sub in enumerate(to_revoke, 1):
            err = results.get(sub.id)
            if err is None:
                sub.state = "REVOKED"
                revoked_ids.append(sub.id)
                revoked += 1
            else:
                # Already cancelled on PhonePe's side is not an error worth retrying;
                # the next run's status check will reconcile it either way.
                logger.error(f"{sub.id}: revoke failed: {err}")
                failed += 1
            if i % 500 == 0:
                db.commit()
        db.commit()
        logger.info(f"Revoked {revoked} duplicate mandates, {failed} failed")

        # These are revocations we initiated, not ones the payer made, but the
        # customer's system has no other way to learn the mandate is dead.
        _dispatch_state_webhooks(db, revoked_ids)
    finally:
        db.close()
        logger.info("Completed: _revoke_duplicate_active_subscriptions")


def _advance_payment_dates():
    """
    For every ACTIVE subscription:
    - If next_payment_date is None → initialise it
    - If next_payment_date is in the past AND last_payment_status is COMPLETED or FAILED → advance it
    """
    logger.info("Starting: _advance_payment_dates")
    db = SessionLocal()
    try:
        app_pairs = _get_all_phonepe_apps(db)
        app_id_set = {detail.app_id for _, detail in app_pairs}
        if not app_id_set:
            logger.info("No PhonePe-enabled apps with credentials, nothing to advance")
            return

        today_ms = _date_to_epoch_ms(datetime.now(timezone.utc).date())

        # Only the rows that can actually change are fetched. The previous version
        # loaded every ACTIVE subscription (4,035 rows) and skipped almost all of
        # them in Python; the two branches below are exactly the two branches the
        # loop acts on, so the outcome is identical.
        subs = (
            db.query(PhonePeSubscription)
            .filter(
                PhonePeSubscription.state == "ACTIVE",
                PhonePeSubscription.app_id.in_(app_id_set),
                or_(
                    PhonePeSubscription.next_payment_date.is_(None),
                    and_(
                        PhonePeSubscription.next_payment_date < today_ms,
                        PhonePeSubscription.last_payment_status.in_(("COMPLETED", "FAILED")),
                    ),
                ),
            )
            .all()
        )
        logger.info(f"Found {len(subs)} ACTIVE subscriptions needing a next_payment_date update")

        # The date arithmetic is pure Python, so the whole set is computed first and
        # written in batches. This used to commit — and log — once per subscription:
        # at 24,106 candidates that is 24,106 round trips to a remote primary for
        # work that is a handful of statements.
        changes = []
        # The previous date per subscription, for the ones whose advance follows a
        # confirmed payment. Captured here because bulk_update_mappings below
        # bypasses the ORM, leaving these in-memory rows holding the old value.
        previous_date: dict[str, int] = {}
        initialised = advanced = on_demand = 0
        for sub in subs:
            if sub.next_payment_date is None:
                next_d = _next_payment_date(sub.created_at.date(), sub.frequency, sub.trail_days or 0)
                initialised += 1
            else:
                next_d = _next_payment_date(_epoch_ms_to_date(sub.next_payment_date), sub.frequency)
                advanced += 1
                # Only a COMPLETED payment counts as confirmed. The query above also
                # advances past a FAILED one so billing keeps its cadence, but
                # nothing was collected, so there is nothing to announce. The
                # initialise branch is skipped too: that is activation, and
                # subscription.activated already carries the first date.
                if sub.last_payment_status == "COMPLETED":
                    previous_date[sub.id] = sub.next_payment_date

            if next_d is None:
                # ON_DEMAND has no next date to compute.
                on_demand += 1
                if sub.next_payment_date is None:
                    initialised -= 1
                else:
                    advanced -= 1
                continue

            changes.append({"id": sub.id, "next_payment_date": _date_to_epoch_ms(next_d)})

        updated = 0
        for i in range(0, len(changes), 500):
            batch = changes[i : i + 500]
            try:
                db.bulk_update_mappings(PhonePeSubscription, batch)
                db.commit()
                updated += len(batch)
            except Exception as e:
                db.rollback()
                logger.error(f"batch update of {len(batch)} next_payment_dates failed: {e}")

        logger.info(
            f"Updated next_payment_date for {updated}/{len(subs)} subscriptions "
            f"({initialised} initialised, {advanced} advanced, {on_demand} ON_DEMAND skipped)"
        )

        _dispatch_next_payment_webhooks(db, previous_date)
    finally:
        db.close()
        logger.info("Completed: _advance_payment_dates")


def _ensure_scheduled_transactions():
    """
    For every ACTIVE subscription that has a next_payment_date set:
    create a SCHEDULED transaction if one doesn't already exist for that date.
    """
    logger.info("Starting: _ensure_scheduled_transactions")
    db = SessionLocal()
    try:
        app_pairs = _get_all_phonepe_apps(db)
        app_id_set = {detail.app_id for _, detail in app_pairs}
        if not app_id_set:
            logger.info("No PhonePe-enabled apps with credentials, nothing to schedule")
            return

        subs = (
            db.query(
                PhonePeSubscription.id,
                PhonePeSubscription.next_payment_date,
                PhonePeSubscription.max_amount,
            )
            .filter(
                PhonePeSubscription.state == "ACTIVE",
                PhonePeSubscription.next_payment_date.isnot(None),
                PhonePeSubscription.app_id.in_(app_id_set),
            )
            .all()
        )
        logger.info(f"Found {len(subs)} ACTIVE subscriptions with next_payment_date set")

        # One existence query for the whole candidate set instead of one per
        # subscription. Chunked so the IN list stays a reasonable size.
        sub_ids = [row.id for row in subs]
        existing: set[tuple[str, int]] = set()
        for i in range(0, len(sub_ids), 1000):
            chunk = sub_ids[i : i + 1000]
            rows = (
                db.query(
                    PhonePeScheduledTransaction.subscription_id,
                    PhonePeScheduledTransaction.payment_date,
                )
                .filter(
                    PhonePeScheduledTransaction.subscription_id.in_(chunk),
                    PhonePeScheduledTransaction.state.not_in(["CANCELLED", "FAILED"]),
                )
                .all()
            )
            existing.update((r.subscription_id, r.payment_date) for r in rows)

        pending = [
            PhonePeScheduledTransaction(
                id=uuid4().hex,
                subscription_id=row.id,
                payment_date=row.next_payment_date,
                amount=row.max_amount,
                state="SCHEDULED",
                attempts=0,
            )
            for row in subs
            if (row.id, row.next_payment_date) not in existing
        ]

        ensured = 0
        for i in range(0, len(pending), 500):
            batch = pending[i : i + 500]
            try:
                db.add_all(batch)
                db.commit()
                ensured += len(batch)
                # Summarised rather than one line per row: a single day's run creates
                # ~48k of these, and that volume is what pushes older worker logs out
                # of the container's retention.
                logger.info(f"  created {ensured}/{len(pending)} ScheduledTransactions")
            except Exception as e:
                db.rollback()
                logger.error(f"batch insert of {len(batch)} ScheduledTransactions failed: {e}")
                # Fall back to one-at-a-time so a single bad row cannot lose the batch.
                for sched in batch:
                    try:
                        db.add(sched)
                        db.commit()
                        ensured += 1
                    except Exception as inner:
                        db.rollback()
                        logger.error(
                            f"{sched.subscription_id}: error ensuring ScheduledTransaction: {inner}"
                        )

        logger.info(f"Created missing ScheduledTransactions for {ensured}/{len(subs)} subscriptions")
    finally:
        db.close()
        logger.info("Completed: _ensure_scheduled_transactions")


def _sync_total_payments():
    """Recount total_payments for every subscription from COMPLETED ScheduledTransactions."""
    logger.info("Starting: _sync_total_payments")
    db = SessionLocal()
    try:
        app_pairs = _get_all_phonepe_apps(db)
        app_id_set = [detail.app_id for _, detail in app_pairs]
        if not app_id_set:
            logger.info("No PhonePe-enabled apps with credentials, nothing to sync")
            return

        # This used to pull every subscription for the app (59,726 rows) into
        # Python and issue one UPDATE + COMMIT per drifted row. Both statements
        # below touch only rows whose stored count is actually wrong, and each is
        # a single round trip.

        # A subscription with no trial is charged its full `amount` during setup, and
        # that payment never becomes a scheduled transaction — so counting only
        # COMPLETED rows under-reports it by one for the life of the subscription.
        # Trial signups are excluded: their setup charge is the trial fee, already
        # surfaced separately as trail_amount/trail_status. The state list is the
        # same "setup actually went through" test used elsewhere.
        setup_payment = (
            "CASE WHEN coalesce(s.trail_days, 0) = 0 "
            "      AND s.state IN ('ACTIVE', 'PAUSED', 'REVOKED') THEN 1 ELSE 0 END"
        )

        # 1. Subscriptions that have COMPLETED scheduled transactions.
        recount = db.execute(
            text(
                f"""
                UPDATE phonepe_subscriptions s
                   SET total_payments = c.cnt + {setup_payment}
                  FROM (
                        SELECT st.subscription_id, count(*) AS cnt
                          FROM phonepe_scheduled_transactions st
                         WHERE st.state = 'COMPLETED'
                         GROUP BY st.subscription_id
                       ) c
                 WHERE s.id = c.subscription_id
                   AND s.app_id = ANY(:app_ids)
                   AND s.total_payments IS DISTINCT FROM c.cnt + {setup_payment}
                """
            ),
            {"app_ids": app_id_set},
        ).rowcount

        # 2. Subscriptions with none — the setup charge alone, so 1 for a completed
        #    non-trial signup and 0 for everything else.
        zeroed = db.execute(
            text(
                f"""
                UPDATE phonepe_subscriptions s
                   SET total_payments = {setup_payment}
                 WHERE s.app_id = ANY(:app_ids)
                   AND s.total_payments IS DISTINCT FROM {setup_payment}
                   AND NOT EXISTS (
                        SELECT 1
                          FROM phonepe_scheduled_transactions st
                         WHERE st.subscription_id = s.id
                           AND st.state = 'COMPLETED'
                       )
                """
            ),
            {"app_ids": app_id_set},
        ).rowcount

        db.commit()
        logger.info(f"Updated total_payments for {recount + zeroed} subscriptions "
                    f"({recount} recounted, {zeroed} baselined)")
    except Exception as e:
        db.rollback()
        logger.error(f"error syncing total_payments: {e}")
    finally:
        db.close()
        logger.info("Completed: _sync_total_payments")


def _archive_failed_subscriptions():
    """
    Move FAILED subscriptions older than ARCHIVE_FAILED_AFTER_HOURS to
    phonepe_subscriptions_archive and delete their scheduled transactions,
    attempt transactions, and the subscription itself.
    """
    logger.info("Starting: _archive_failed_subscriptions")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ARCHIVE_FAILED_AFTER_HOURS)
    db = SessionLocal()
    archived = 0
    try:
        if not _get_all_phonepe_apps(db):
            logger.info("No PhonePe-enabled apps with credentials, nothing to archive")
            return

        # Batched set-based moves. The previous version fetched every matching row
        # (51,391 on 2026-09-04), then did an ORM insert + cascade delete + COMMIT
        # per row — one transaction per subscription, which could not keep up with
        # the inflow. Each batch below is a single transaction and the loop stops
        # when the backlog is drained or ARCHIVE_MAX_ROWS_PER_RUN is reached.
        while archived < ARCHIVE_MAX_ROWS_PER_RUN:
            batch_ids = [
                row[0]
                for row in db.execute(
                    text(
                        """
                        SELECT id
                          FROM phonepe_subscriptions
                         WHERE state = 'FAILED'
                           AND created_at < :cutoff
                         ORDER BY created_at
                         LIMIT :limit
                        """
                    ),
                    {"cutoff": cutoff, "limit": ARCHIVE_BATCH_SIZE},
                )
            ]
            if not batch_ids:
                break

            try:
                # Children first: the FKs have no ON DELETE CASCADE at the database
                # level, the cascade the old code relied on was ORM-side only.
                db.execute(
                    text(
                        "DELETE FROM phonepe_subscription_transactions "
                        "WHERE subscription_id = ANY(:ids)"
                    ),
                    {"ids": batch_ids},
                )
                db.execute(
                    text(
                        "DELETE FROM phonepe_scheduled_transactions "
                        "WHERE subscription_id = ANY(:ids)"
                    ),
                    {"ids": batch_ids},
                )
                db.execute(
                    text(
                        """
                        INSERT INTO phonepe_subscriptions_archive (
                            id, app_id, phone_number, amount, max_amount, amount_type,
                            frequency, auth_workflow_type, product_type, state,
                            phonepe_subscription_id, phonepe_order_id, next_payment_date,
                            last_payment_status, total_payments, trail_days, expire_at,
                            created_at, archived_at
                        )
                        SELECT
                            id, app_id, phone_number, amount, max_amount, amount_type,
                            frequency, auth_workflow_type, product_type, state,
                            phonepe_subscription_id, phonepe_order_id, next_payment_date,
                            last_payment_status, total_payments, trail_days, expire_at,
                            created_at, now()
                          FROM phonepe_subscriptions
                         WHERE id = ANY(:ids)
                        ON CONFLICT (id) DO NOTHING
                        """
                    ),
                    {"ids": batch_ids},
                )
                deleted = db.execute(
                    text("DELETE FROM phonepe_subscriptions WHERE id = ANY(:ids)"),
                    {"ids": batch_ids},
                ).rowcount
                db.commit()
                archived += deleted
                logger.info(f"archived batch of {deleted} (running total {archived})")
            except Exception as e:
                db.rollback()
                logger.error(f"error archiving batch of {len(batch_ids)}: {e}")
                break

        logger.info(
            f"Completed: _archive_failed_subscriptions — {archived} archived "
            f"(FAILED and created before {cutoff.isoformat()})"
        )
    finally:
        db.close()


# ── Outbound webhooks ──────────────────────────────────────────────────────────

def _dispatch_state_webhooks(db: Session, sub_ids: list[str]) -> None:
    """Announce whatever state these subscriptions ended up in.

    Called after the batch commits rather than inside the loop, so the rows are
    durable and the payload reflects what was written — including any
    next_payment_date computed in the same pass. The state is re-read rather
    than taken from the pre-poll snapshot, which is also what makes a
    rolled-back batch harmless: the row still holds the old state, that state
    maps to no event, and nothing is claimed. See webhooks.dispatch_state_changes.

    Never raises: a webhook problem must not fail a state sync. The sweep in
    _webhook_maintenance is the backstop for anything dropped here.
    """
    if not sub_ids:
        return
    try:
        subs = (
            db.query(PhonePeSubscription)
            .filter(PhonePeSubscription.id.in_(sub_ids))
            .all()
        )
        webhooks.dispatch_state_changes(db, subs)
    except Exception as e:
        logger.error(f"[webhook] dispatch of {len(sub_ids)} state changes failed: {e}")


def _dispatch_next_payment_webhooks(db: Session, previous_date: dict[str, int]) -> None:
    """Announce confirmed recurring payments whose next date just moved.

    `previous_date` maps subscription id to the date it was on before this run.
    The rows are re-read because bulk_update_mappings wrote around the ORM, so
    the objects the caller holds still carry the old date — and re-reading is
    also what makes a rolled-back batch harmless, since the date that comes back
    then equals the previous one and is skipped.

    Never raises: a webhook problem must not fail the billing job.
    """
    if not previous_date:
        return
    try:
        db.expire_all()
        subs = (
            db.query(PhonePeSubscription)
            .filter(PhonePeSubscription.id.in_(previous_date.keys()))
            .all()
        )
        pairs = [
            (sub, previous_date[sub.id])
            for sub in subs
            if sub.next_payment_date is not None
            and sub.next_payment_date != previous_date[sub.id]
        ]
        if len(pairs) != len(previous_date):
            logger.warning(
                f"[webhook] {len(previous_date) - len(pairs)} of {len(previous_date)} advances "
                f"did not persist — not announcing those"
            )
        webhooks.dispatch_next_payment_updated(db, pairs)
    except Exception as e:
        logger.error(f"[webhook] dispatch of {len(previous_date)} payment advances failed: {e}")


def _deliver_webhook(task, delivery_id: str) -> None:
    """Send one delivery, and schedule the next attempt if it is worth retrying.

    Retries are driven by the attempt count on the row, not by Celery's own
    counter, so a delivery re-queued by _webhook_maintenance or by the
    dashboard's retry button picks up the same backoff ladder.
    """
    db = SessionLocal()
    try:
        outcome = webhooks.deliver(db, delivery_id)
    finally:
        db.close()

    if outcome.retryable:
        countdown = webhooks.retry_countdown(outcome.attempts)
        logger.info(f"[webhook] {delivery_id}: retrying in {countdown}s (attempt {outcome.attempts} failed)")
        raise task.retry(countdown=countdown, max_retries=webhooks.MAX_ATTEMPTS, exc=None)


# The state events are capped by nature — one delivery per subscription, ever.
# subscription.next_payment_updated is not: it fires every billing cycle for the
# life of every mandate, so this table is the first webhook row that grows
# without bound. Delivered rows are the part nobody reads after the fact; FAILED
# and PENDING are kept indefinitely because they are what a customer debugging a
# missed event actually looks at, and there are few of them.
WEBHOOK_DELIVERED_RETENTION_DAYS = 30


def _retry_stranded_webhooks(db: Session) -> None:
    """Re-enqueue deliveries still PENDING well after they were claimed.

    Claiming and enqueueing cannot be made atomic — the row is committed, then
    the broker is told. A broker outage, or a worker killed mid-task, leaves a
    claimed row that nothing will ever send, and the uniqueness constraint means
    no later observer will claim it again. This is the only thing that gets
    those moving, so it is deliberately simple and idempotent.
    """
    from app.models.webhook import WebhookDelivery

    # The longest gap in the backoff ladder is 6 hours, so anything PENDING
    # beyond that has no attempt in flight and is genuinely stranded.
    cutoff = datetime.now(timezone.utc) - timedelta(hours=7)
    stuck = (
        db.query(WebhookDelivery.id)
        .filter(
            WebhookDelivery.status == "PENDING",
            WebhookDelivery.created_at < cutoff,
        )
        .order_by(WebhookDelivery.created_at.asc())
        .limit(1000)
        .all()
    )
    ids = [row[0] for row in stuck]
    if not ids:
        logger.info("No stranded webhook deliveries")
        return
    logger.info(f"Re-enqueueing {len(ids)} stranded webhook deliveries")
    webhooks.enqueue(ids)


def _prune_delivered_webhooks(db: Session) -> None:
    """Drop DELIVERED rows past the retention window, in capped batches."""
    from app.models.webhook import WebhookDelivery

    cutoff = datetime.now(timezone.utc) - timedelta(days=WEBHOOK_DELIVERED_RETENTION_DAYS)
    deleted = 0
    while True:
        ids = [
            row[0]
            for row in db.query(WebhookDelivery.id)
            .filter(
                WebhookDelivery.status == "DELIVERED",
                WebhookDelivery.created_at < cutoff,
            )
            .limit(ARCHIVE_BATCH_SIZE)
            .all()
        ]
        if not ids:
            break
        try:
            db.query(WebhookDelivery).filter(WebhookDelivery.id.in_(ids)).delete(
                synchronize_session=False
            )
            db.commit()
            deleted += len(ids)
        except Exception as e:
            db.rollback()
            logger.error(f"pruning {len(ids)} delivered webhooks failed: {e}")
            break
    logger.info(
        f"Pruned {deleted} delivered webhook deliveries older than "
        f"{WEBHOOK_DELIVERED_RETENTION_DAYS} days"
    )


def _webhook_maintenance() -> None:
    """Rescue stranded deliveries, then prune the delivered backlog."""
    logger.info("Starting: _webhook_maintenance")
    db = SessionLocal()
    try:
        _retry_stranded_webhooks(db)
        _prune_delivered_webhooks(db)
    finally:
        db.close()
        logger.info("Completed: _webhook_maintenance")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stdout,
    )
    # Uncomment to run tasks manually for testing:
    # _sync_subscription_state()
    # _notify_redemption_for_due_subscriptions()
    # _sync_redemption_txn_state()
    # _sync_scheduled_transactions()
    # _advance_payment_dates()
    # _ensure_scheduled_transactions()
    # _sync_total_payments()
    # _archive_failed_subscriptions()
    # _webhook_maintenance()
