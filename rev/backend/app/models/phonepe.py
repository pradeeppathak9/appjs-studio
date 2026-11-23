from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class PhonePeApp(Base):
    __tablename__ = "phonepe_apps"

    app_id = Column(String, ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True)
    phonepe_client_id = Column(String, nullable=True)
    phonepe_client_secret = Column(String, nullable=True)
    phonepe_merchant_id = Column(String, nullable=True)
    phonepe_environment = Column(String, default="UAT")

    trial_enabled = Column(Boolean, default=False, nullable=False)
    trial_amount = Column(Integer, nullable=True)
    trial_period_days = Column(Integer, nullable=True)


class PhonePeSubscription(Base):
    __tablename__ = "phonepe_subscriptions"

    id = Column(String, primary_key=True)           # merchant-generated UUID hex
    app_id = Column(String, ForeignKey("apps.id"), nullable=False)
    phone_number = Column(String, nullable=False)

    amount = Column(Integer, nullable=False)         # in paise
    max_amount = Column(Integer, nullable=True)
    amount_type = Column(String, default="FIXED")   # FIXED | VARIABLE

    frequency = Column(String, nullable=False)       # MONTHLY | WEEKLY | DAILY | ON_DEMAND …
    auth_workflow_type = Column(String, default="TRANSACTION")  # TRANSACTION | PENNY_DROP
    product_type = Column(String, default="UPI_INTENT")         # UPI_INTENT | UPI_MANDATE

    state = Column(String, default="INITIATED", index=True)
    # INITIATED → ACTIVATION_IN_PROGRESS → ACTIVE / CANCELLED / REVOKED / FAILED / PAUSED

    phonepe_subscription_id = Column(String, nullable=True)
    phonepe_order_id = Column(String, nullable=True)

    next_payment_date = Column(BigInteger, nullable=True)   # epoch ms
    last_payment_status = Column(String, nullable=True)
    total_payments = Column(Integer, default=0)

    trail_days = Column(Integer, default=0)
    expire_at = Column(BigInteger, nullable=True)           # epoch ms

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Autovacuum storage parameters for this table are set in
    # backend/migrations/001_indexes.sql (they are operational tuning, not schema).
    # app_id on its own is not indexed on purpose: it has ~2 distinct values in
    # practice, so it can only ever be a leading column. See
    # backend/migrations/001_indexes.sql for the measurements behind each index.
    __table_args__ = (
        # dashboard list + created_at range filters
        Index("ix_phonepe_subs_app_created", "app_id", created_at.desc()),
        # public API lookups by phone, always scoped to an app
        Index("ix_phonepe_subs_app_phone", "app_id", "phone_number"),
        # worker _sync_subscription_state, which polls only the newest rows
        Index(
            "ix_phonepe_subs_pending_activation_created",
            "app_id",
            created_at.desc(),
            postgresql_where=state.in_(["INITIATED", "ACTIVATION_IN_PROGRESS"]),
        ),
        # workers _advance_payment_dates / _ensure_scheduled_transactions
        Index(
            "ix_phonepe_subs_active_next_payment",
            "app_id",
            "next_payment_date",
            postgresql_where=(state == "ACTIVE"),
        ),
        # worker _archive_failed_subscriptions — the fastest-growing input
        Index(
            "ix_phonepe_subs_failed_created",
            "created_at",
            postgresql_where=(state == "FAILED"),
        ),
    )

    app = relationship("App")
    scheduled_transactions = relationship(
        "PhonePeScheduledTransaction", back_populates="subscription", cascade="all, delete-orphan"
    )
    transactions = relationship(
        "PhonePeSubscriptionTransaction", back_populates="subscription", cascade="all, delete-orphan"
    )


class PhonePeScheduledTransaction(Base):
    __tablename__ = "phonepe_scheduled_transactions"

    id = Column(String, primary_key=True)
    subscription_id = Column(String, ForeignKey("phonepe_subscriptions.id"), nullable=False)

    payment_date = Column(BigInteger, nullable=False)   # epoch ms
    amount = Column(Integer, nullable=False)             # in paise
    state = Column(String, default="SCHEDULED")
    # SCHEDULED → IN_PROGRESS → COMPLETED / FAILED / CANCELLED
    attempts = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # worker _notify_redemption_for_due_subscriptions
        Index("ix_phonepe_sched_state_payment_date", "state", "payment_date"),
        # _ensure_scheduled_transactions existence check and the
        # "last COMPLETED payment" lookup behind subscription validity
        Index("ix_phonepe_sched_sub_payment_date", "subscription_id", payment_date.desc()),
    )

    subscription = relationship("PhonePeSubscription", back_populates="scheduled_transactions")
    transactions = relationship(
        "PhonePeSubscriptionTransaction", back_populates="scheduled_transaction"
    )


class PhonePeSubscriptionArchive(Base):
    __tablename__ = "phonepe_subscriptions_archive"

    id = Column(String, primary_key=True)
    app_id = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)

    amount = Column(Integer, nullable=False)
    max_amount = Column(Integer, nullable=True)
    amount_type = Column(String)
    frequency = Column(String, nullable=False)
    auth_workflow_type = Column(String)
    product_type = Column(String)
    state = Column(String)

    phonepe_subscription_id = Column(String, nullable=True)
    phonepe_order_id = Column(String, nullable=True)

    next_payment_date = Column(BigInteger, nullable=True)
    last_payment_status = Column(String, nullable=True)
    total_payments = Column(Integer, default=0)

    trail_days = Column(Integer, default=0)
    expire_at = Column(BigInteger, nullable=True)

    created_at = Column(DateTime(timezone=True))
    archived_at = Column(DateTime(timezone=True), server_default=func.now())

    # Write-mostly and growing by ~50k rows/day: carries only what is read back.
    # state is not indexed — every row in here is FAILED.
    __table_args__ = (
        Index("ix_phonepe_subs_archive_app_phone", "app_id", "phone_number"),
        Index("ix_phonepe_subs_archive_archived_at", "archived_at"),
    )


class PhonePeSubscriptionTransaction(Base):
    __tablename__ = "phonepe_subscription_transactions"

    id = Column(String, primary_key=True)               # merchant order ID
    subscription_id = Column(String, ForeignKey("phonepe_subscriptions.id"), nullable=False)
    scheduled_transaction_id = Column(
        String, ForeignKey("phonepe_scheduled_transactions.id"), nullable=True
    )

    amount = Column(Integer, nullable=False)             # in paise
    state = Column(String, default="INITIATED", index=True)
    # INITIATED → SUCCESS / FAILED / PENDING / COMPLETED / REVOKED / CANCELLED

    payment_due_date = Column(BigInteger, nullable=True)
    transaction_id = Column(String, nullable=True)       # PhonePe txn ID

    request_payload = Column(JSONB, nullable=True)
    response_payload = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # When _sync_redemption_txn_state last asked PhonePe about this row. NULL
    # means never, which sorts first so a new transaction is always picked up on
    # the next run.
    #
    # This exists because selecting the backlog by created_at starves. Polling
    # oldest-first re-reads the same never-resolving rows every run, so once the
    # backlog outgrew the per-run cap the middle became unreachable: 10,775 rows
    # on 22 Oct 2026, 7,401 of them already days stale while PhonePe had long
    # since failed them. Ordering by this column instead rotates through the
    # whole backlog no matter how big it gets.
    last_polled_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # "latest attempt for this scheduled transaction"
        Index("ix_phonepe_txn_sched_created", "scheduled_transaction_id", created_at.desc()),
        Index("ix_phonepe_txn_sub_created", "subscription_id", created_at.desc()),
        # The poll queue: only non-terminal rows are ever selected, so the index
        # stays small even as the table grows.
        Index(
            "ix_phonepe_txn_poll_queue",
            last_polled_at.asc().nullsfirst(),
            postgresql_where=state.notin_(["FAILED", "COMPLETED", "REVOKED", "CANCELLED"]),
        ),
    )

    subscription = relationship("PhonePeSubscription", back_populates="transactions")
    scheduled_transaction = relationship("PhonePeScheduledTransaction", back_populates="transactions")
