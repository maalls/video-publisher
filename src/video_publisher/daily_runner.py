"""Proposed bounded production runner. No implicit grants or bootstrap.

Only this module's run() performs generation/platform work. Dependencies are
injected for tests. Existing uncertain intents require reconciliation, never
an automatic repeat of a paid call or an upload.
"""
from datetime import date, datetime
import hashlib
from pathlib import Path
from .daily_plan import DailyGrant, PARIS, PlanError, daily_plan, operation_key
from .durable_state import StateError


def parse_grant(raw):
    try:
        if raw.get("version") != 1 or raw.get("content") != "daily-french-horoscope":
            raise ValueError()
        for key in ("youtube_enabled", "tiktok_enabled", "costs_confirmed"):
            if type(raw[key]) is not bool:
                raise ValueError()
        return DailyGrant(raw["youtube_account"], raw["tiktok_account"],
                          date.fromisoformat(raw["starts_on"]), date.fromisoformat(raw["expires_on"]),
                          raw["youtube_enabled"], raw["tiktok_enabled"], raw["costs_confirmed"])
    except (ValueError, KeyError, TypeError, AttributeError):
        raise PlanError("Accord quotidien incomplet; aucune génération ni publication") from None


def run(session, now, generate, identities, send_youtube, send_tiktok):
    grant = parse_grant(session.state.get("grant"))
    day = grant.check(now)
    # Reconcile existing attempts without even refreshing platform credentials.
    # Operators use the separate status path; daily jobs never replay an intent.
    enabled = [("youtube", grant.youtube_account, grant.youtube_enabled),
               ("tiktok", grant.tiktok_account, grant.tiktok_enabled)]
    pending = []
    for platform, account, enabled_flag in enabled:
        if not enabled_flag:
            continue
        key = operation_key(day, platform, account)
        op = session.state["operations"].get(key)
        if op and op.get("status") != "complete":
            raise StateError("Envoi antérieur à réconcilier; aucune relance automatique")
        if not op:
            pending.append(platform)
    if not pending:
        return {"status": "already-complete"}
    youtube_account, tiktok_account = identities(grant)
    if grant.youtube_enabled and youtube_account != grant.youtube_account:
        raise PlanError("Chaîne YouTube différente")
    if grant.tiktok_enabled and tiktok_account != grant.tiktok_account:
        raise PlanError("Compte TikTok différent")
    # Reserve all generation costs before Gemini/TTS. A killed run blocks retry.
    generation_key = hashlib.sha256((day.isoformat() + ":generation").encode()).hexdigest()
    prior = session.state["operations"].get(generation_key)
    if prior:
        # We cannot prove the identical MP4 survived the runner. Do not regenerate
        # or trust a mutable cache as the source of truth.
        raise StateError("Génération antérieure; reprise média explicite requise")
    session.claim(generation_key, {"date": day.isoformat(), "platform": "generation",
                                   "account": "daily-french-horoscope", "sha256": "not-generated"})
    video = Path(generate(day))
    if not video.is_file():
        raise StateError("MP4 absent; aucun transfert")
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    session.record(generation_key, "complete", {"sha256": digest})
    plan = daily_plan(grant, now, session.state["operations"], digest,
                      youtube_account, tiktok_account)
    results = {}
    for item in plan:
        if item["action"] in {"skip", "missed-deadline"}:
            results[item["platform"]] = item["action"]
            continue
        if item["action"] == "status-only":
            raise StateError("Envoi antérieur à réconcilier")
        session.claim(item["key"], item["binding"])
        def persist(receipt, key=item["key"]):
            # Every intermediate provider receipt remains durable + encrypted.
            session.record(key, "accepted", receipt)
        sender = send_youtube if item["platform"] == "youtube" else send_tiktok
        try:
            receipt = sender(video, day, grant, persist)
        except StateError:
            raise
        except Exception:
            # Keep any previously captured ID for later status reconciliation.
            previous = session.state["operations"][item["key"]].get("receipt", {})
            session.record(item["key"], "uncertain", previous)
            results[item["platform"]] = "uncertain"
            continue
        session.record(item["key"], "complete", receipt)
        results[item["platform"]] = "complete"
    return results
