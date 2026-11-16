"""Bounded daily plan. Offline policy only, never uploads or generates content."""
from dataclasses import dataclass
from datetime import date, datetime, time
import hashlib
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


class PlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class DailyGrant:
    youtube_account: str
    tiktok_account: str
    starts_on: date
    expires_on: date
    youtube_enabled: bool = False
    tiktok_enabled: bool = False
    costs_confirmed: bool = False

    def check(self, now):
        if now.tzinfo is None:
            raise PlanError("Heure avec fuseau requise")
        day = now.astimezone(PARIS).date()
        if not self.starts_on <= day <= self.expires_on:
            raise PlanError("Accord quotidien absent ou expiré")
        if not self.costs_confirmed:
            raise PlanError("Conditions de coût non confirmées")
        if self.youtube_enabled and not self.youtube_account:
            raise PlanError("Chaîne YouTube requise")
        if self.tiktok_enabled and not self.tiktok_account:
            raise PlanError("Compte TikTok requis")
        return day


def operation_key(day, platform, account):
    """One video/day/account, NOT one upload per file hash."""
    if platform not in {"youtube", "tiktok"} or not account:
        raise PlanError("Plateforme et compte requis")
    return hashlib.sha256(f"{day.isoformat()}:{platform}:{account}".encode()).hexdigest()


def daily_plan(grant, now, operations, video_sha256, observed_youtube, observed_tiktok):
    """Return intents without side effects. Existing intent is never replayed.

    Caller must validate grant provenance, preview/content scope, persist each
    intent through CAS, then re-check live identity immediately before upload.
    A plan returned here is NOT owner authority and must not create a grant.
    """
    day = grant.check(now)
    if len(video_sha256) != 64 or any(c not in "0123456789abcdef" for c in video_sha256):
        raise PlanError("Empreinte MP4 SHA256 requise")
    if grant.youtube_enabled and observed_youtube != grant.youtube_account:
        raise PlanError("Chaîne YouTube différente")
    if grant.tiktok_enabled and observed_tiktok != grant.tiktok_account:
        raise PlanError("Compte TikTok différent")
    planned = []
    for platform, account, enabled in (
        ("youtube", grant.youtube_account, grant.youtube_enabled),
        ("tiktok", grant.tiktok_account, grant.tiktok_enabled),
    ):
        if not enabled:
            continue
        key = operation_key(day, platform, account)
        existing = operations.get(key)
        if existing:
            expected = {"date": day.isoformat(), "platform": platform,
                        "account": account, "sha256": video_sha256}
            if existing.get("binding") != expected:
                raise PlanError("Média ou liaison différent de l'intention durable")
            # Complete is skipped; every other state requires status/reconciliation.
            action = "skip" if existing.get("status") == "complete" else "status-only"
        elif platform == "youtube" and now >= datetime.combine(day, time(7), PARIS):
            action = "missed-deadline"
        else:
            action = "schedule-0700" if platform == "youtube" else "send-inbox"
        planned.append({"key": key, "platform": platform, "action": action,
                        "binding": {"date": day.isoformat(), "platform": platform,
                                    "account": account, "sha256": video_sha256}})
    return planned
