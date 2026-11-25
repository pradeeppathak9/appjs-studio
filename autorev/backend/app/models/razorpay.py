from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class RazorpayApp(Base):
    __tablename__ = "razorpay_apps"

    app_id = Column(String, ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True)
    razorpay_key_id = Column(String, nullable=True)
    razorpay_key_secret = Column(String, nullable=True)
    razorpay_webhook_secret = Column(String, nullable=True)
    razorpay_environment = Column(String, default="TEST")  # TEST | LIVE


class RazorpaySubscription(Base):
    __tablename__ = "razorpay_subscriptions"

    id = Column(String, primary_key=True)            # merchant-generated UUID hex
    app_id = Column(String, ForeignKey("apps.id"), nullable=False)
    phone_number = Column(String, nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    # The integration's own reference (e.g. Studio's order), echoed in status and webhooks.
    external_ref = Column(String(200), nullable=True)

    amount = Column(Integer, nullable=False)          # in paise
    max_amount = Column(Integer, nullable=True)
    amount_type = Column(String, default="FIXED")     # FIXED | VARIABLE

    frequency = Column(String, nullable=False)         # DAILY | WEEKLY | MONTHLY | ... | ON_DEMAND
    method = Column(String, default="upi")             # upi | emandate | card

    state = Column(String, default="INITIATED", index=True)
    # INITIATED → AUTHORIZATION_PENDING → ACTIVE → HALTED (collection gave up) / CANCELLED
    #                                   ↘ FAILED (mandate rejected)

    razorpay_customer_id = Column(String, nullable=True)
    razorpay_order_id = Column(String, nullable=True)   # authorization/registration order
    razorpay_token_id = Column(String, nullable=True)   # saved mandate token, set once authorized

    next_payment_date = Column(BigInteger, nullable=True)   # epoch ms
    last_payment_status = Column(String, nullable=True)
    total_payments = Column(Integer, default=0)

    trail_days = Column(Integer, default=0)
    expire_at = Column(BigInteger, nullable=True)            # epoch ms

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_razorpay_subs_app_created", "app_id", created_at.desc()),
        Index("ix_razorpay_subs_app_phone", "app_id", "phone_number"),
        Index(
            "ix_razorpay_subs_app_external_ref",
            "app_id",
            "external_ref",
            postgresql_where=(external_ref.isnot(None)),
        ),
        # webhook: payment.authorized / order.paid resolve the sub by order id
        Index("ix_razorpay_subs_app_order", "app_id", "razorpay_order_id"),
        # worker collect_due: ACTIVE subscriptions coming due
        Index(
            "ix_razorpay_subs_active_next_payment",
            "app_id",
            "next_payment_date",
            postgresql_where=(state == "ACTIVE"),
        ),
    )

    app = relationship("App")
    transactions = relationship(
        "RazorpayTransaction", back_populates="subscription", cascade="all, delete-orphan"
    )


class RazorpayTransaction(Base):
    __tablename__ = "razorpay_transactions"

    id = Column(String, primary_key=True)             # merchant-generated charge order ref
    subscription_id = Column(String, ForeignKey("razorpay_subscriptions.id"), nullable=False)

    amount = Column(Integer, nullable=False)           # in paise
    state = Column(String, default="INITIATED", index=True)
    # NOTIFIED (charge order created) → INITIATED (token charged) → SUCCESS / FAILED

    # The due date (epoch ms, like next_payment_date) this attempt is paying for.
    # Retries are counted per due date; null on rows from before AutoRev collected.
    payment_due_date = Column(BigInteger, nullable=True)

    razorpay_order_id = Column(String, nullable=True)     # the per-charge order
    razorpay_payment_id = Column(String, nullable=True)   # the resulting payment

    request_payload = Column(JSONB, nullable=True)
    response_payload = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # webhook: payment.captured / payment.failed resolve the txn by order id
        Index("ix_razorpay_txn_order", "razorpay_order_id"),
        Index("ix_razorpay_txn_sub_created", "subscription_id", created_at.desc()),
        # attempts per billing cycle
        Index("ix_razorpay_txn_sub_due", "subscription_id", "payment_due_date"),
        # worker reconcile: only unsettled rows are ever selected
        Index(
            "ix_razorpay_txn_unsettled",
            created_at,
            postgresql_where=state.in_(["NOTIFIED", "INITIATED"]),
        ),
    )

    subscription = relationship("RazorpaySubscription", back_populates="transactions")
