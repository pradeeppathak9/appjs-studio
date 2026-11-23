from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

import logging

from app.api_handler.phonepe import (
    InvalidSubscriptionStateError,
    PhonePeException,
    get_handler,
)
from app import webhooks
from app.auth import get_current_user
from app.database import get_db
from app.redis import redis_client
from app.models import (
    App,
    AppUser,
    RazorpaySubscription,
    RazorpayTransaction,
    PhonePeApp,
    PhonePeScheduledTransaction,
    PhonePeSubscription,
    PhonePeSubscriptionArchive,
    PhonePeSubscriptionTransaction,
    User,
)
from app.schemas import (
    SummaryPeriod,
    SummaryResponse,
    SubscriptionResponse,
    ScheduledTransactionResponse,
    SubscriptionTransactionResponse,
    RazorpaySubscriptionResponse,
    RazorpayTransactionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/apps/{app_id}", tags=["dashboard"])

# /summary runs five aggregates that each have to touch every subscription row for
# the app; there is no filter that narrows them further. They are cheap to repeat
# but not free, and the dashboard polls them, so the result is memoised briefly.
# Counters move continuously anyway, so a few seconds of staleness is invisible.
SUMMARY_CACHE_TTL_SECONDS = 30


def _get_app(app_id: str, user: User, db: Session) -> App:
    """Resolve an app the caller may use, by grant — admins included.

    Mirrors apps._get_accessible_app; the two must agree, or an app would be
    listed on a dashboard whose data then 404s, or vice versa.
    """
    app = (
        db.query(App)
        .join(AppUser, (AppUser.app_id == App.id) & (AppUser.user_id == user.id))
        .filter(App.id == app_id)
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app


# ── Summary ────────────────────────────────────────────────────────────────────

def _summary_counters(
    app_id: str,
    db: Session,
    start: datetime | None = None,
    end: datetime | None = None,
) -> SummaryPeriod:
    """The summary counters for one app over the window [start, end).

    The bounds are applied to each table's own created_at, so a window covers rows
    that came into existence in it rather than rows whose payment happens to fall in it.
    """
    def scoped(q, created_col):
        if start is not None:
            q = q.filter(created_col >= start)
        if end is not None:
            q = q.filter(created_col < end)
        return q

    # Scheduled payments are the exception: they are windowed by when the payment is
    # DUE, not when the row was created. The worker bulk-creates rows days ahead, so
    # created_at would report thousands of "payments today" that are due next week.
    # payment_date (epoch ms) is also what GET /scheduled filters on, so the summary
    # and the transactions page now agree.
    start_ms = int(start.timestamp() * 1000) if start is not None else None
    end_ms = int(end.timestamp() * 1000) if end is not None else None

    def scoped_due(q):
        if start_ms is not None:
            q = q.filter(PhonePeScheduledTransaction.payment_date >= start_ms)
        if end_ms is not None:
            q = q.filter(PhonePeScheduledTransaction.payment_date < end_ms)
        return q

    sub_rows = (
        scoped(
            db.query(PhonePeSubscription.state, func.count(PhonePeSubscription.id))
            .filter(PhonePeSubscription.app_id == app_id),
            PhonePeSubscription.created_at,
        )
        .group_by(PhonePeSubscription.state)
        .all()
    )
    # Count and value come from the same grouped scan — no extra round trip.
    sched_rows = (
        scoped_due(
            db.query(
                PhonePeScheduledTransaction.state,
                func.count(PhonePeScheduledTransaction.id),
                func.coalesce(func.sum(PhonePeScheduledTransaction.amount), 0),
            )
            .join(PhonePeSubscription)
            .filter(PhonePeSubscription.app_id == app_id)
        )
        .group_by(PhonePeScheduledTransaction.state)
        .all()
    )
    txn_rows = (
        scoped(
            db.query(PhonePeSubscriptionTransaction.state, func.count(PhonePeSubscriptionTransaction.id))
            .join(PhonePeSubscription)
            .filter(PhonePeSubscription.app_id == app_id),
            PhonePeSubscriptionTransaction.created_at,
        )
        .group_by(PhonePeSubscriptionTransaction.state)
        .all()
    )
    payment_revenue = scoped(
        db.query(func.coalesce(func.sum(PhonePeSubscriptionTransaction.amount), 0))
        .join(PhonePeSubscription)
        .filter(
            PhonePeSubscription.app_id == app_id,
            # PhonePe redemptions settle as COMPLETED; "SUCCESS" is Razorpay's
            # vocabulary and never appears on a phonepe transaction row.
            PhonePeSubscriptionTransaction.state == "COMPLETED",
        ),
        PhonePeSubscriptionTransaction.created_at,
    ).scalar()
    # Trial amount charged at setup time never gets its own transaction row, so it
    # has to be pulled from the subscription snapshot for subscriptions whose
    # trial actually went through (mirrors the `show_trial` check used elsewhere).
    trial_revenue, trial_setups = scoped(
        db.query(
            func.coalesce(func.sum(PhonePeSubscription.amount), 0),
            func.count(PhonePeSubscription.id),
        ).filter(
            PhonePeSubscription.app_id == app_id,
            PhonePeSubscription.trail_days > 0,
            PhonePeSubscription.state.in_(["ACTIVE", "PAUSED", "REVOKED"]),
        ),
        PhonePeSubscription.created_at,
    ).one()

    # Archived subscriptions (FAILED ones moved out of the live table) still count
    # towards the totals — without them the dashboard silently under-reports FAILED.
    archive_rows = (
        scoped(
            db.query(PhonePeSubscriptionArchive.state, func.count(PhonePeSubscriptionArchive.id))
            .filter(PhonePeSubscriptionArchive.app_id == app_id),
            PhonePeSubscriptionArchive.created_at,
        )
        .group_by(PhonePeSubscriptionArchive.state)
        .all()
    )

    sub_by_state = {row[0]: row[1] for row in sub_rows}
    for state, count in archive_rows:
        sub_by_state[state] = sub_by_state.get(state, 0) + count
    sched_by_state = {row[0]: row[1] for row in sched_rows}
    sched_value_by_state = {row[0]: int(row[2]) for row in sched_rows}
    txn_by_state = {row[0]: row[1] for row in txn_rows}

    return SummaryPeriod(
        subscriptions_total=sum(sub_by_state.values()),
        subscriptions_by_state=sub_by_state,
        scheduled_total=sum(sched_by_state.values()),
        scheduled_by_state=sched_by_state,
        scheduled_value_paise=sum(sched_value_by_state.values()),
        scheduled_value_by_state_paise=sched_value_by_state,
        transactions_total=sum(txn_by_state.values()),
        transactions_by_state=txn_by_state,
        revenue_collected_paise=int(payment_revenue + trial_revenue),
        payment_revenue_collected_paise=int(payment_revenue),
        trial_revenue_collected_paise=int(trial_revenue),
        trial_setups_count=int(trial_setups),
    )


def _ist_midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=IST)


@router.get("/summary", response_model=SummaryResponse)
def get_summary(
    app_id: str,
    start_date: date | None = Query(None, description="Window start (inclusive, IST). Omit for no lower bound."),
    end_date: date | None = Query(None, description="Window end (inclusive, IST). Omit for no upper bound."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Summary counters for a window. Omitting both bounds reports all time.

    The dashboard always sends explicit dates for its dated presets, so an unbounded
    request only comes from the "All" quick-select.
    """
    _get_app(app_id, current_user, db)

    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must not be after end_date")

    # v7: omitted bounds now mean all time rather than today, so a v6 entry keyed
    # None:None holds today's counters — bump rather than serve them.
    cache_key = f"summary:v7:{app_id}:{start_date}:{end_date}"
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return SummaryResponse.model_validate_json(cached)
    except Exception:
        pass  # a Redis hiccup must not take the dashboard down

    # end_date is inclusive, so the exclusive upper bound is the next midnight.
    counters = _summary_counters(
        app_id,
        db,
        _ist_midnight(start_date) if start_date else None,
        _ist_midnight(end_date + timedelta(days=1)) if end_date else None,
    )

    response = SummaryResponse(**counters.model_dump(), window_start=start_date, window_end=end_date)
    try:
        redis_client.setex(cache_key, SUMMARY_CACHE_TTL_SECONDS, response.model_dump_json())
    except Exception:
        pass
    return response


# ── Subscriptions ──────────────────────────────────────────────────────────────

@router.get("/subscriptions", response_model=list[SubscriptionResponse])
def list_subscriptions(
    app_id: str,
    response: Response,
    state: str | None = Query(None),
    phone_number: str | None = Query(None),
    subscription_id: str | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    limit: int = Query(50, le=1000),
    offset: int = Query(0),
    with_count: bool = Query(True, description="Set false when paging to skip the count(*)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_app(app_id, current_user, db)
    q = db.query(PhonePeSubscription).filter(PhonePeSubscription.app_id == app_id)
    if state:
        q = q.filter(PhonePeSubscription.state == state)
    if phone_number:
        q = q.filter(PhonePeSubscription.phone_number == phone_number)
    if subscription_id:
        q = q.filter(PhonePeSubscription.id == subscription_id)
    if start_date:
        q = q.filter(PhonePeSubscription.created_at >= datetime(start_date.year, start_date.month, start_date.day, tzinfo=IST))
    if end_date:
        q = q.filter(PhonePeSubscription.created_at < datetime(end_date.year, end_date.month, end_date.day, tzinfo=IST) + timedelta(days=1))

    # Total for the pager, over the same filters but without limit/offset, so the
    # client can page without ever holding the full result set.
    #
    # Counting dominates the request (~23ms here vs ~0.07ms to fetch the page), and
    # the total cannot change as a user walks pages of one filtered set, so the
    # client asks for it once per filter change and passes with_count=false after.
    # CORS note: X-Total-Count is only readable cross-origin because it is listed
    # in expose_headers on the CORS middleware in app/main.py.
    if with_count:
        response.headers["X-Total-Count"] = str(q.order_by(None).count())

    return q.order_by(PhonePeSubscription.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/subscriptions/state-counts")
def subscription_state_counts(
    app_id: str,
    phone_number: str | None = Query(None),
    subscription_id: str | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    """Per-state row counts for the pill row.

    Mirrors list_subscriptions' filters except `state` itself — otherwise picking one
    pill would zero out every other count. Live table only, no archive, so a pill's
    number always matches what clicking it actually lists.
    """
    _get_app(app_id, current_user, db)
    q = db.query(PhonePeSubscription.state, func.count(PhonePeSubscription.id)).filter(
        PhonePeSubscription.app_id == app_id
    )
    if phone_number:
        q = q.filter(PhonePeSubscription.phone_number == phone_number)
    if subscription_id:
        q = q.filter(PhonePeSubscription.id == subscription_id)
    if start_date:
        q = q.filter(PhonePeSubscription.created_at >= datetime(start_date.year, start_date.month, start_date.day, tzinfo=IST))
    if end_date:
        q = q.filter(PhonePeSubscription.created_at < datetime(end_date.year, end_date.month, end_date.day, tzinfo=IST) + timedelta(days=1))

    return {state: count for state, count in q.group_by(PhonePeSubscription.state).all()}


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
def get_subscription(
    app_id: str,
    subscription_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_app(app_id, current_user, db)
    sub = (
        db.query(PhonePeSubscription)
        .filter(PhonePeSubscription.id == subscription_id, PhonePeSubscription.app_id == app_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


@router.post("/subscriptions/{subscription_id}/revoke", response_model=SubscriptionResponse)
def revoke_subscription(
    app_id: str,
    subscription_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a mandate at PhonePe, then sync the resulting state back onto the row."""
    _get_app(app_id, current_user, db)
    sub = (
        db.query(PhonePeSubscription)
        .filter(PhonePeSubscription.id == subscription_id, PhonePeSubscription.app_id == app_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if sub.state in ("CANCELLED", "REVOKED"):
        raise HTTPException(status_code=409, detail=f"Subscription is already {sub.state}")

    detail = db.query(PhonePeApp).filter(PhonePeApp.app_id == app_id).first()
    handler = get_handler(detail, custom=True)
    db.commit()  # release the DB connection before the blocking PhonePe calls

    try:
        handler.cancel_subscription(subscription_id)
    except InvalidSubscriptionStateError as e:
        raise HTTPException(status_code=409, detail=f"PhonePe rejected the cancellation: {e}")
    except PhonePeException as e:
        logger.error(f"revoke_subscription failed for {subscription_id}: {e}")
        raise HTTPException(status_code=502, detail=f"PhonePe error: {e}")

    # Trust PhonePe for the resulting state rather than assuming REVOKED.
    try:
        sub.state = handler.subscription_status(subscription_id).get("state", "REVOKED")
    except PhonePeException as e:
        logger.warning(f"revoke_subscription: cancel succeeded but status re-fetch failed for {subscription_id}: {e}")
        sub.state = "REVOKED"

    db.add(sub)
    db.commit()
    db.refresh(sub)

    # A dashboard revoke is still a revoke as far as the customer's system is
    # concerned, so it announces itself like any other.
    webhooks.dispatch_state_changes(db, [sub])

    return sub


# ── Scheduled Transactions ─────────────────────────────────────────────────────

@router.get("/scheduled/state-counts")
def scheduled_state_counts(
    app_id: str,
    subscription_id: str | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    """Per-state row counts for the pill row, windowed by due date like list_scheduled."""
    _get_app(app_id, current_user, db)
    q = (
        db.query(PhonePeScheduledTransaction.state, func.count(PhonePeScheduledTransaction.id))
        .join(PhonePeSubscription)
        .filter(PhonePeSubscription.app_id == app_id)
    )
    if subscription_id:
        q = q.filter(PhonePeScheduledTransaction.subscription_id == subscription_id)
    if start_date:
        q = q.filter(PhonePeScheduledTransaction.payment_date >= int(datetime(start_date.year, start_date.month, start_date.day, tzinfo=IST).timestamp() * 1000))
    if end_date:
        q = q.filter(PhonePeScheduledTransaction.payment_date < int((datetime(end_date.year, end_date.month, end_date.day, tzinfo=IST) + timedelta(days=1)).timestamp() * 1000))

    return {state: count for state, count in q.group_by(PhonePeScheduledTransaction.state).all()}


@router.get("/scheduled", response_model=list[ScheduledTransactionResponse])
def list_scheduled(
    app_id: str,
    response: Response,
    state: str | None = Query(None),
    subscription_id: str | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    limit: int = Query(50, le=1000),
    offset: int = Query(0),
    with_count: bool = Query(True, description="Set false when paging to skip the count(*)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_app(app_id, current_user, db)
    q = (
        db.query(PhonePeScheduledTransaction)
        .join(PhonePeSubscription)
        .filter(PhonePeSubscription.app_id == app_id)
    )
    if state:
        q = q.filter(PhonePeScheduledTransaction.state == state)
    if subscription_id:
        q = q.filter(PhonePeScheduledTransaction.subscription_id == subscription_id)
    if start_date:
        q = q.filter(PhonePeScheduledTransaction.payment_date >= int(datetime(start_date.year, start_date.month, start_date.day, tzinfo=IST).timestamp() * 1000))
    if end_date:
        q = q.filter(PhonePeScheduledTransaction.payment_date < int((datetime(end_date.year, end_date.month, end_date.day, tzinfo=IST) + timedelta(days=1)).timestamp() * 1000))
    # See list_subscriptions: the join makes this count even more expensive (~56ms).
    if with_count:
        response.headers["X-Total-Count"] = str(q.order_by(None).count())

    sched_rows = q.order_by(PhonePeScheduledTransaction.payment_date.desc()).offset(offset).limit(limit).all()

    sched_ids = [s.id for s in sched_rows]
    latest_txn_by_sched = {}
    if sched_ids:
        latest_created_subq = (
            db.query(
                PhonePeSubscriptionTransaction.scheduled_transaction_id.label("sched_id"),
                func.max(PhonePeSubscriptionTransaction.created_at).label("max_created"),
            )
            .filter(PhonePeSubscriptionTransaction.scheduled_transaction_id.in_(sched_ids))
            .group_by(PhonePeSubscriptionTransaction.scheduled_transaction_id)
            .subquery()
        )
        latest_txns = (
            db.query(PhonePeSubscriptionTransaction)
            .join(
                latest_created_subq,
                (PhonePeSubscriptionTransaction.scheduled_transaction_id == latest_created_subq.c.sched_id)
                & (PhonePeSubscriptionTransaction.created_at == latest_created_subq.c.max_created),
            )
            .all()
        )
        latest_txn_by_sched = {t.scheduled_transaction_id: t for t in latest_txns}

    return [
        ScheduledTransactionResponse(
            id=s.id,
            subscription_id=s.subscription_id,
            payment_date=s.payment_date,
            amount=s.amount,
            state=s.state,
            attempts=s.attempts,
            created_at=s.created_at,
            transaction_id=(latest_txn_by_sched[s.id].transaction_id if s.id in latest_txn_by_sched else None),
            merchant_order_id=(latest_txn_by_sched[s.id].id if s.id in latest_txn_by_sched else None),
        )
        for s in sched_rows
    ]


# ── Subscription Transactions ──────────────────────────────────────────────────

@router.get("/transactions", response_model=list[SubscriptionTransactionResponse])
def list_transactions(
    app_id: str,
    state: str | None = Query(None),
    subscription_id: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_app(app_id, current_user, db)
    q = (
        db.query(PhonePeSubscriptionTransaction)
        .join(PhonePeSubscription)
        .filter(PhonePeSubscription.app_id == app_id)
    )
    if state:
        q = q.filter(PhonePeSubscriptionTransaction.state == state)
    if subscription_id:
        q = q.filter(PhonePeSubscriptionTransaction.subscription_id == subscription_id)
    return (
        q.order_by(PhonePeSubscriptionTransaction.created_at.desc()).offset(offset).limit(limit).all()
    )


@router.get(
    "/subscriptions/{subscription_id}/transactions",
    response_model=list[SubscriptionTransactionResponse],
)
def list_subscription_transactions(
    app_id: str,
    subscription_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_app(app_id, current_user, db)
    return (
        db.query(PhonePeSubscriptionTransaction)
        .filter(PhonePeSubscriptionTransaction.subscription_id == subscription_id)
        .order_by(PhonePeSubscriptionTransaction.created_at.desc())
        .all()
    )


@router.get(
    "/scheduled/{scheduled_transaction_id}/attempts",
    response_model=list[SubscriptionTransactionResponse],
)
def list_scheduled_attempts(
    app_id: str,
    scheduled_transaction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_app(app_id, current_user, db)
    return (
        db.query(PhonePeSubscriptionTransaction)
        .filter(PhonePeSubscriptionTransaction.scheduled_transaction_id == scheduled_transaction_id)
        .order_by(PhonePeSubscriptionTransaction.created_at.desc())
        .all()
    )


# ── Razorpay Subscriptions ──────────────────────────────────────────────────────

@router.get("/razorpay-subscriptions", response_model=list[RazorpaySubscriptionResponse])
def list_razorpay_subscriptions(
    app_id: str,
    state: str | None = Query(None),
    phone_number: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_app(app_id, current_user, db)
    q = db.query(RazorpaySubscription).filter(RazorpaySubscription.app_id == app_id)
    if state:
        q = q.filter(RazorpaySubscription.state == state)
    if phone_number:
        q = q.filter(RazorpaySubscription.phone_number == phone_number)
    return q.order_by(RazorpaySubscription.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/razorpay-subscriptions/{subscription_id}", response_model=RazorpaySubscriptionResponse)
def get_razorpay_subscription(
    app_id: str,
    subscription_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_app(app_id, current_user, db)
    sub = (
        db.query(RazorpaySubscription)
        .filter(RazorpaySubscription.id == subscription_id, RazorpaySubscription.app_id == app_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


# ── Razorpay Transactions ────────────────────────────────────────────────────────

@router.get("/razorpay-transactions", response_model=list[RazorpayTransactionResponse])
def list_razorpay_transactions(
    app_id: str,
    state: str | None = Query(None),
    subscription_id: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_app(app_id, current_user, db)
    q = (
        db.query(RazorpayTransaction)
        .join(RazorpaySubscription)
        .filter(RazorpaySubscription.app_id == app_id)
    )
    if state:
        q = q.filter(RazorpayTransaction.state == state)
    if subscription_id:
        q = q.filter(RazorpayTransaction.subscription_id == subscription_id)
    return (
        q.order_by(RazorpayTransaction.created_at.desc()).offset(offset).limit(limit).all()
    )


@router.get(
    "/razorpay-subscriptions/{subscription_id}/transactions",
    response_model=list[RazorpayTransactionResponse],
)
def list_razorpay_subscription_transactions(
    app_id: str,
    subscription_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_app(app_id, current_user, db)
    return (
        db.query(RazorpayTransaction)
        .filter(RazorpayTransaction.subscription_id == subscription_id)
        .order_by(RazorpayTransaction.created_at.desc())
        .all()
    )
