from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class WebhookDelivery(Base):
    """One outbound webhook call — and the lock that decides who gets to make it.

    A single state transition can be observed by several processes at once: the
    status endpoint an integration polls seconds after setup, the 10-minute
    state sweep, and the daily paused sweep can all see the same subscription
    turn ACTIVE. Rather than coordinate them, the row recording a delivery is
    itself the claim: the unique (app_id, event, object_id) below means an
    INSERT ... ON CONFLICT DO NOTHING RETURNING id hands the event to exactly
    one caller, whichever got there first, and the losers see an empty result.

    Consequence worth knowing: an event fires at most once per object, ever.
    A mandate that activates, pauses and resumes sends one
    subscription.activated — the resume is a different event, not a second
    activation. Re-sending the same event for the same object needs an explicit
    retry of this row (see retry_delivery), never a second insert.
    """

    __tablename__ = "webhook_deliveries"

    id = Column(String, primary_key=True)          # uuid4 hex; sent as X-Autorev-Delivery
    app_id = Column(String, ForeignKey("apps.id", ondelete="CASCADE"), nullable=False)

    event = Column(String, nullable=False)         # see app.webhooks.EVENTS
    object_id = Column(String, nullable=False)     # subscription id, or the delivery's own id for tests

    url = Column(Text, nullable=False)             # snapshotted: the target at claim time
    payload = Column(JSONB, nullable=False)

    status = Column(String, nullable=False, default="PENDING")
    # PENDING → DELIVERED / FAILED. Deliberately not SUCCESS/COMPLETED: those
    # belong to payment state and have been confused for each other here before.
    attempts = Column(Integer, nullable=False, default=0)
    response_code = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)            # truncated response body or exception

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # The claim. Also the "did we already tell them about this?" lookup.
        UniqueConstraint("app_id", "event", "object_id", name="uq_webhook_deliveries_event_object"),
        # Settings shows the newest deliveries for one app.
        Index("ix_webhook_deliveries_app_created", "app_id", created_at.desc()),
        # The stuck-delivery sweep: narrow, because almost nothing stays PENDING.
        Index(
            "ix_webhook_deliveries_pending_created",
            "created_at",
            postgresql_where=(status == "PENDING"),
        ),
    )
