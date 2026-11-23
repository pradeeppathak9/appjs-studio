"""Plans, subscriptions and credits of an app's users.

A plan grants `credits_per_month` every month while a subscription is active, whatever its billing
period (a yearly plan grants monthly). Payments aren't collected yet: subscriptions are granted by an
admin (`provider="manual"`). A `PaymentProvider` (Razorpay, ...) will create and renew them later.
"""

from __future__ import annotations

import calendar
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studio.db.tables import AppUser, CreditEntry, Plan, Subscription, User
from studio.endusers.credits import apply_entry, lock_balance
from studio.errors import ConflictError, InsufficientCredits, NotFoundError, ValidationFailed

log = logging.getLogger(__name__)
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


class PlanFields(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    price_minor: int = Field(ge=0, le=100_000_000, description="price in the currency's minor unit (paise)")
    currency: str = Field("INR", pattern="^[A-Z]{3}$")
    billing_period: str = Field("month", pattern="^(month|year)$")
    credits_per_month: int = Field(ge=0, le=1_000_000)
    badge: str | None = Field(None, max_length=60)
    status: str = Field("active", pattern="^(active|archived)$")


class PlanCreate(PlanFields):
    slug: str

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("slug: 1-64 lower-case letters, digits and dashes; no dash at the ends")
        return v


class PaymentProvider(Protocol):
    """To be implemented for Razorpay (or another provider): start a purchase of `plan` for `user`
    and turn the provider's signed webhooks into `BillingService.activate/renew/cancel` calls."""

    name: str

    async def create_checkout(self, plan: Plan, user: AppUser) -> dict: ...
    async def handle_webhook(self, headers: dict[str, str], body: bytes) -> None: ...


def add_months(dt: datetime, n: int) -> datetime:
    month = dt.month - 1 + n
    year, month = dt.year + month // 12, month % 12 + 1
    return dt.replace(year=year, month=month, day=min(dt.day, calendar.monthrange(year, month)[1]))


class BillingService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.db = sessions

    # ---- plans ----------------------------------------------------------------------------------
    async def plans(self, app_id: UUID, *, active_only: bool = False) -> list[Plan]:
        q = select(Plan).where(Plan.app_id == app_id).order_by(Plan.position, Plan.created_at)
        if active_only:
            q = q.where(Plan.status == "active")
        async with self.db() as s:
            return list((await s.scalars(q)).all())

    async def plan(self, app_id: UUID, plan_id: UUID) -> Plan:
        async with self.db() as s:
            p = await s.get(Plan, plan_id)
        if p is None or p.app_id != app_id:
            raise NotFoundError("plan not found")
        return p

    async def create_plan(self, app_id: UUID, body: PlanCreate) -> Plan:
        async with self.db.begin() as s:
            if await s.scalar(select(Plan.id).where(Plan.app_id == app_id, Plan.slug == body.slug)):
                raise ConflictError("this app already has a plan with this slug", "slug")
            position = await s.scalar(
                select(func.coalesce(func.max(Plan.position), -1) + 1).where(Plan.app_id == app_id)
            )
            p = Plan(id=uuid.uuid4(), app_id=app_id, position=position, **body.model_dump())
            s.add(p)
        return await self.plan(app_id, p.id)

    async def update_plan(self, app_id: UUID, plan_id: UUID, body: PlanFields) -> Plan:
        """Changes apply from the next monthly grant; credits already granted stay."""
        await self.plan(app_id, plan_id)
        async with self.db.begin() as s:
            await s.execute(
                update(Plan).where(Plan.id == plan_id).values(**body.model_dump(), updated_at=func.now())
            )
        return await self.plan(app_id, plan_id)

    async def delete_plan(self, app_id: UUID, plan_id: UUID) -> None:
        """Delete a plan nobody ever subscribed to; archive it otherwise."""
        await self.plan(app_id, plan_id)
        async with self.db.begin() as s:
            used = await s.scalar(select(func.count()).where(Subscription.plan_id == plan_id))
            if used:
                await s.execute(
                    update(Plan).where(Plan.id == plan_id).values(status="archived", updated_at=func.now())
                )
            else:
                await s.delete(await s.get(Plan, plan_id))

    async def reorder_plans(self, app_id: UUID, plan_ids: list[UUID]) -> None:
        current = {p.id for p in await self.plans(app_id)}
        if set(plan_ids) != current or len(plan_ids) != len(current):
            raise ValidationFailed("list every plan of the app exactly once", "plan_ids")
        async with self.db.begin() as s:
            for i, pid in enumerate(plan_ids):
                await s.execute(update(Plan).where(Plan.id == pid).values(position=i))

    # ---- subscriptions ------------------------------------------------------------------------------
    async def active_subscriptions(self, user_ids: list[UUID]) -> dict[UUID, tuple[Subscription, Plan]]:
        if not user_ids:
            return {}
        async with self.db() as s:
            rows = await s.execute(
                select(Subscription, Plan)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(Subscription.app_user_id.in_(user_ids), Subscription.status == "active")
            )
            return {sub.app_user_id: (sub, plan) for sub, plan in rows}

    async def subscriptions(self, user_id: UUID) -> list[tuple[Subscription, Plan]]:
        async with self.db() as s:
            rows = await s.execute(
                select(Subscription, Plan)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(Subscription.app_user_id == user_id)
                .order_by(Subscription.created_at.desc())
            )
            return [(a, b) for a, b in rows]

    async def grant_subscription(
        self,
        actor: User | None,
        user: AppUser,
        plan_id: UUID,
        *,
        provider: str = "manual",
        provider_ref: str | None = None,
        now: datetime | None = None,
    ) -> Subscription:
        """Start a subscription now and grant its first month of credits."""
        plan = await self.plan(user.app_id, plan_id)
        if plan.status != "active":
            raise ValidationFailed("this plan is archived", "plan_id")
        now = now or datetime.now(UTC)
        end = add_months(now, 12 if plan.billing_period == "year" else 1)
        second = add_months(now, 1)
        sub = Subscription(
            id=uuid.uuid4(),
            app_user_id=user.id,
            plan_id=plan.id,
            status="active",
            provider=provider,
            provider_ref=provider_ref,
            current_period_start=now,
            current_period_end=end,
            next_credit_grant_at=second if second < end else None,
            created_by=actor.id if actor else None,
        )
        async with self.db.begin() as s:
            locked = await s.scalar(select(AppUser).where(AppUser.id == user.id).with_for_update())
            if locked is None or locked.deleted_at is not None:
                raise NotFoundError("user not found")
            if await s.scalar(
                select(Subscription.id).where(
                    Subscription.app_user_id == user.id, Subscription.status == "active"
                )
            ):
                raise ConflictError("this user already has an active subscription; cancel it first")
            s.add(sub)
            await s.flush()
            if plan.credits_per_month:
                await apply_entry(
                    s,
                    app_id=user.app_id,
                    app_user_id=user.id,
                    delta=plan.credits_per_month,
                    reason="subscription_grant",
                    key=f"grant:{sub.id}:m0",
                    subscription_id=sub.id,
                    note=f"{plan.name}: month 1",
                )
        return sub

    async def cancel_subscription(self, app_id: UUID, user_id: UUID, sub_id: UUID) -> None:
        """Stop it now: no further monthly grants. Credits already granted stay."""
        async with self.db.begin() as s:
            sub = await s.get(Subscription, sub_id, with_for_update=True)
            owner = await s.get(AppUser, user_id)
            if sub is None or owner is None or sub.app_user_id != user_id or owner.app_id != app_id:
                raise NotFoundError("subscription not found")
            if sub.status != "active":
                raise ConflictError("this subscription isn't active")
            sub.status = "cancelled"
            sub.next_credit_grant_at = None
            sub.updated_at = func.now()

    async def link_subscription(
        self, app_id: UUID, user_id: UUID, sub_id: UUID, provider: str, provider_ref: str | None
    ) -> tuple[Subscription, Plan]:
        """Record which payment-gateway subscription (Razorpay `sub_…`, PhonePe subscription id) this
        subscription is paid by, or set it back to `manual`. A gateway id links to one subscription only."""
        async with self.db.begin() as s:
            sub = await s.get(Subscription, sub_id, with_for_update=True)
            owner = await s.get(AppUser, user_id)
            if sub is None or owner is None or sub.app_user_id != user_id or owner.app_id != app_id:
                raise NotFoundError("subscription not found")
            if provider_ref and await s.scalar(
                select(Subscription.id).where(
                    Subscription.provider == provider,
                    Subscription.provider_ref == provider_ref,
                    Subscription.id != sub_id,
                )
            ):
                raise ConflictError(f"this {provider} subscription is already linked to another subscription")
            sub.provider = provider
            sub.provider_ref = provider_ref
            sub.updated_at = func.now()
            await s.flush()
            plan = await s.get(Plan, sub.plan_id)
            return sub, plan

    async def grant_due_credits(self, now: datetime | None = None) -> int:
        """Grant each active subscription's monthly credits that are due, and expire subscriptions
        whose period has ended. Safe to run from every worker at once. Returns grants made."""
        now = now or datetime.now(UTC)
        granted = 0
        for _ in range(240):  # bounded catch-up per call; the next sweep continues
            async with self.db.begin() as s:
                rows = (
                    await s.execute(
                        select(Subscription, Plan, AppUser)
                        .join(Plan, Plan.id == Subscription.plan_id)
                        .join(AppUser, AppUser.id == Subscription.app_user_id)
                        .where(Subscription.status == "active", Subscription.next_credit_grant_at <= now)
                        .order_by(Subscription.next_credit_grant_at)
                        .limit(100)
                        .with_for_update(of=Subscription, skip_locked=True)
                    )
                ).all()
                for sub, plan, user in rows:
                    due = sub.next_credit_grant_at
                    if plan.credits_per_month and user.deleted_at is None:
                        month = 1 + _months_between(sub.current_period_start, due)
                        if await apply_entry(
                            s,
                            app_id=user.app_id,
                            app_user_id=user.id,
                            delta=plan.credits_per_month,
                            reason="subscription_grant",
                            key=f"grant:{sub.id}:m{month - 1}",
                            subscription_id=sub.id,
                            note=f"{plan.name}: month {month}",
                        ):
                            granted += 1
                    nxt = add_months(due, 1)
                    sub.next_credit_grant_at = nxt if nxt < sub.current_period_end else None
                    sub.updated_at = func.now()
            if not rows:  # a subscription several months behind is due again after each pass
                break
        async with self.db.begin() as s:
            await s.execute(
                update(Subscription)
                .where(Subscription.status == "active", Subscription.current_period_end <= now)
                .values(status="expired", next_credit_grant_at=None, updated_at=func.now())
            )
        if granted:
            log.info("granted monthly credits to %d subscriptions", granted)
        return granted

    # ---- credits --------------------------------------------------------------------------------
    async def history(self, user_id: UUID, limit: int = 50) -> list[CreditEntry]:
        async with self.db() as s:
            q = (
                select(CreditEntry)
                .where(CreditEntry.app_user_id == user_id)
                .order_by(CreditEntry.created_at.desc())
                .limit(min(max(limit, 1), 200))
            )
            return list((await s.scalars(q)).all())

    async def history_page(
        self, user_id: UUID, limit: int = 50, offset: int = 0
    ) -> tuple[list[CreditEntry], int]:
        """One page of the user's credit history (every charge, refund, grant and adjustment), newest
        first, and the number of entries in all."""
        where = CreditEntry.app_user_id == user_id
        async with self.db() as s:
            total = await s.scalar(select(func.count()).select_from(CreditEntry).where(where))
            q = (
                select(CreditEntry)
                .where(where)
                .order_by(CreditEntry.created_at.desc(), CreditEntry.id)
                .limit(min(max(limit, 1), 200))
                .offset(max(offset, 0))
            )
            return list((await s.scalars(q)).all()), total or 0

    async def adjust(self, actor: User, user: AppUser, delta: int, note: str) -> int:
        """Add (or, with a negative delta, remove) credits by hand. Returns the new balance."""
        if delta == 0:
            raise ValidationFailed("the change can't be 0", "delta")
        try:
            async with self.db.begin() as s:
                if delta < 0:
                    await lock_balance(s, user.id, -delta)
                await apply_entry(
                    s,
                    app_id=user.app_id,
                    app_user_id=user.id,
                    delta=delta,
                    reason="admin_adjust",
                    key=f"adjust:{uuid.uuid4()}",
                    note=note.strip(),
                    created_by=actor.id,
                )
                return await s.scalar(select(AppUser.credits).where(AppUser.id == user.id))
        except (InsufficientCredits, IntegrityError) as e:
            raise ValidationFailed("the balance can't go below 0", "delta") from e


def _months_between(a: datetime, b: datetime) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)
