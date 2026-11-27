from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class App(Base):
    __tablename__ = "apps"

    # 16 hex chars (new_app_id); apps made before migration 009 keep their 32-char uuid hex, since
    # the id is in webhook payloads and Razorpay notes that receivers may have stored.
    id = Column(String, primary_key=True)
    # Like AppJs Studio: `slug` is the stable machine name (lower-case, digits, dashes; unique; set
    # at creation and never changed), `name` the display name an owner may edit.
    slug = Column(String(64), nullable=False)
    name = Column(String, nullable=False)

    phonepe_enabled = Column(Boolean, default=False, nullable=False)
    razorpay_enabled = Column(Boolean, default=False, nullable=False)

    api_key = Column(String, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)

    # Outbound webhooks. Gateway-agnostic on purpose — these sit on the app, not
    # on PhonePeApp/RazorpayApp, so a Razorpay-side event can reuse the same
    # endpoint and secret. webhook_events is the subscribed subset of
    # app.webhooks.EVENTS; NULL means every registered event.
    webhook_url = Column(Text, nullable=True)
    webhook_secret = Column(String, nullable=True)
    webhook_enabled = Column(Boolean, default=False, nullable=False)
    webhook_events = Column(JSONB, nullable=True)

    # Optional Authorization header for endpoints behind a bearer token or basic
    # auth. A credential belonging to the customer's system, not ours: it is
    # write-only over the API (masked on read), kept out of logs, and never put
    # in a delivery row — webhook_deliveries is readable from the dashboard.
    # Held separately from the enable flag so turning delivery auth off does not
    # make the customer re-enter the token.
    webhook_auth_header = Column(Text, nullable=True)
    webhook_auth_enabled = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("uq_apps_slug", "slug", unique=True),)
    # No relationships, no user_id — ownership/access lives only in AppUser;
    # PhonePeApp/RazorpayApp/PhonePeSubscription/RazorpaySubscription are always
    # looked up by an explicit query against app_id rather than ORM navigation.


class AppUser(Base):
    """Grants a user access to an app."""
    __tablename__ = "app_users"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    app_id = Column(String, ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # The PK is (user_id, app_id), so filters on app_id alone — every admin
    # "who has access to this app" query, plus the ON DELETE CASCADE from apps —
    # have no usable index without this.
    __table_args__ = (Index("ix_app_users_app_id", "app_id"),)

    user = relationship("User", back_populates="app_accesses")
