import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.admin.crypto import AuditCipher, token_hash
from app.admin.models import AdminAuditEvent, AdminSession, Base, LoginChallenge, ScoreQueryEvent


def now_utc() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@dataclass(frozen=True)
class SessionIdentity:
    subject: str
    email: str | None
    name: str | None
    csrf_token: str
    absolute_expires_at: datetime


class AdminStore:
    def __init__(
        self,
        engine: Engine,
        cipher: AuditCipher,
        *,
        session_idle_seconds: int,
        session_absolute_seconds: int,
        result_retention_days: int,
        metadata_retention_days: int,
        admin_audit_retention_days: int,
    ):
        self.engine = engine
        self.sessions = sessionmaker(engine, expire_on_commit=False)
        self.cipher = cipher
        self.session_idle_seconds = session_idle_seconds
        self.session_absolute_seconds = session_absolute_seconds
        self.result_retention_days = result_retention_days
        self.metadata_retention_days = metadata_retention_days
        self.admin_audit_retention_days = admin_audit_retention_days

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def check(self) -> None:
        with self.sessions() as session:
            session.execute(select(1))

    def cleanup(self) -> None:
        now = now_utc()
        with self.sessions.begin() as session:
            session.execute(delete(LoginChallenge).where(LoginChallenge.expires_at <= now))
            session.execute(
                delete(AdminSession).where(
                    (AdminSession.expires_at <= now) | (AdminSession.absolute_expires_at <= now)
                )
            )
            session.execute(
                update(ScoreQueryEvent)
                .where(ScoreQueryEvent.result_expires_at <= now)
                .values(result_ciphertext=None, result_expires_at=None)
            )
            session.execute(
                delete(ScoreQueryEvent).where(ScoreQueryEvent.metadata_expires_at <= now)
            )
            session.execute(delete(AdminAuditEvent).where(AdminAuditEvent.expires_at <= now))

    def create_login_challenge(self, state: str, binding: str, verifier: str, nonce: str) -> None:
        state_digest = token_hash(state)
        with self.sessions.begin() as session:
            session.add(
                LoginChallenge(
                    state_hash=state_digest,
                    binding_hash=token_hash(binding),
                    verifier_ciphertext=self.cipher.encrypt_text(
                        verifier, context=f"login:{state_digest}"
                    ),
                    nonce=nonce,
                    expires_at=now_utc() + timedelta(minutes=5),
                )
            )

    def consume_login_challenge(self, state: str, binding: str) -> tuple[str, str] | None:
        digest = token_hash(state)
        now = now_utc()
        with self.sessions.begin() as session:
            challenge = session.get(LoginChallenge, digest)
            if challenge is None:
                return None
            session.delete(challenge)
            if as_utc(challenge.expires_at) <= now or not secrets.compare_digest(
                challenge.binding_hash, token_hash(binding)
            ):
                return None
            verifier = self.cipher.decrypt_text(
                challenge.verifier_ciphertext, context=f"login:{digest}"
            )
            return verifier or "", challenge.nonce

    def create_session(
        self, *, subject: str, email: str | None, name: str | None
    ) -> tuple[str, str, datetime]:
        token = secrets.token_urlsafe(48)
        csrf = secrets.token_urlsafe(32)
        digest = token_hash(token)
        now = now_utc()
        absolute = now + timedelta(seconds=self.session_absolute_seconds)
        with self.sessions.begin() as session:
            session.add(
                AdminSession(
                    token_hash=digest,
                    subject=subject,
                    email_ciphertext=self.cipher.encrypt_text(
                        email, context=f"session-email:{digest}"
                    ),
                    name_ciphertext=self.cipher.encrypt_text(
                        name, context=f"session-name:{digest}"
                    ),
                    csrf_hash=token_hash(csrf),
                    csrf_ciphertext=self.cipher.encrypt_text(
                        csrf, context=f"session-csrf:{digest}"
                    ),
                    created_at=now,
                    last_seen_at=now,
                    expires_at=min(absolute, now + timedelta(seconds=self.session_idle_seconds)),
                    absolute_expires_at=absolute,
                )
            )
        self.record_admin_event(subject, "login_succeeded")
        return token, csrf, absolute

    def get_session(self, token: str) -> SessionIdentity | None:
        digest = token_hash(token)
        now = now_utc()
        with self.sessions.begin() as session:
            stored = session.get(AdminSession, digest)
            if stored is None:
                return None
            absolute_expires_at = as_utc(stored.absolute_expires_at)
            if as_utc(stored.expires_at) <= now or absolute_expires_at <= now:
                session.delete(stored)
                return None
            stored.last_seen_at = now
            stored.expires_at = min(
                absolute_expires_at,
                now + timedelta(seconds=self.session_idle_seconds),
            )
            return SessionIdentity(
                subject=stored.subject,
                email=self.cipher.decrypt_text(
                    stored.email_ciphertext, context=f"session-email:{digest}"
                ),
                name=self.cipher.decrypt_text(
                    stored.name_ciphertext, context=f"session-name:{digest}"
                ),
                csrf_token=self.cipher.decrypt_text(
                    stored.csrf_ciphertext, context=f"session-csrf:{digest}"
                )
                or "",
                absolute_expires_at=absolute_expires_at,
            )

    def delete_session(self, token: str, csrf: str) -> str | None:
        digest = token_hash(token)
        with self.sessions.begin() as session:
            stored = session.get(AdminSession, digest)
            if stored is None or not secrets.compare_digest(stored.csrf_hash, token_hash(csrf)):
                return None
            subject = stored.subject
            session.delete(stored)
        self.record_admin_event(subject, "logout")
        return subject

    def record_query(
        self,
        *,
        request_id: str,
        started_at: datetime,
        completed_at: datetime,
        fields: dict[str, Any],
        status: int,
        duration_ms: float,
        credentials: str,
        result: dict | None,
    ) -> None:
        row_id = str(uuid.uuid4())
        query = fields.get("query")
        username = fields.get("username")
        with self.sessions.begin() as session:
            session.add(
                ScoreQueryEvent(
                    id=row_id,
                    request_id=request_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    query_ciphertext=self.cipher.encrypt_text(
                        str(query) if query is not None else None,
                        context=f"query-input:{row_id}",
                    ),
                    username_ciphertext=self.cipher.encrypt_text(
                        str(username) if username is not None else None,
                        context=f"query-username:{row_id}",
                    ),
                    username_lookup=self.cipher.lookup(str(username)) if username else None,
                    player_id=fields.get("user_id"),
                    mode=fields.get("mode"),
                    requested_limit=fields.get("limit"),
                    score_count=fields.get("score_count"),
                    status=status,
                    error_code=fields.get("error_code"),
                    cache=fields.get("cache"),
                    credentials=credentials,
                    api_slot=fields.get("api_slot"),
                    upstream_requests=int(fields.get("upstream_requests") or 0),
                    duration_ms=duration_ms,
                    result_ciphertext=self.cipher.encrypt_json(
                        result, context=f"query-result:{row_id}"
                    ),
                    result_expires_at=(
                        completed_at + timedelta(days=self.result_retention_days)
                        if result is not None
                        else None
                    ),
                    metadata_expires_at=completed_at + timedelta(days=self.metadata_retention_days),
                )
            )

    def overview(self) -> dict:
        since = now_utc() - timedelta(hours=24)
        with self.sessions() as session:
            total = session.scalar(
                select(func.count())
                .select_from(ScoreQueryEvent)
                .where(ScoreQueryEvent.completed_at >= since)
            )
            successful = session.scalar(
                select(func.count())
                .select_from(ScoreQueryEvent)
                .where(
                    ScoreQueryEvent.completed_at >= since,
                    ScoreQueryEvent.status < 400,
                )
            )
            errors = session.scalar(
                select(func.count())
                .select_from(ScoreQueryEvent)
                .where(
                    ScoreQueryEvent.completed_at >= since,
                    ScoreQueryEvent.status >= 500,
                )
            )
            average_ms = session.scalar(
                select(func.avg(ScoreQueryEvent.duration_ms)).where(
                    ScoreQueryEvent.completed_at >= since
                )
            )
        return {
            "period_hours": 24,
            "requests": total or 0,
            "successful": successful or 0,
            "server_errors": errors or 0,
            "average_duration_ms": round(float(average_ms or 0), 1),
        }

    def list_queries(self, *, limit: int, before: datetime | None = None) -> list[dict]:
        statement = (
            select(ScoreQueryEvent).order_by(ScoreQueryEvent.completed_at.desc()).limit(limit)
        )
        if before is not None:
            statement = statement.where(ScoreQueryEvent.completed_at < before)
        with self.sessions() as session:
            rows = session.scalars(statement).all()
        return [self._query_summary(row) for row in rows]

    def get_query(self, event_id: str) -> dict | None:
        with self.sessions.begin() as session:
            row = session.get(ScoreQueryEvent, event_id)
            if row is None:
                return None
            if row.result_expires_at and as_utc(row.result_expires_at) <= now_utc():
                row.result_ciphertext = None
                row.result_expires_at = None
            result = self._query_summary(row)
            result["result"] = self.cipher.decrypt_json(
                row.result_ciphertext, context=f"query-result:{row.id}"
            )
            return result

    def _query_summary(self, row: ScoreQueryEvent) -> dict:
        return {
            "id": row.id,
            "request_id": row.request_id,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "query": self.cipher.decrypt_text(
                row.query_ciphertext, context=f"query-input:{row.id}"
            ),
            "username": self.cipher.decrypt_text(
                row.username_ciphertext, context=f"query-username:{row.id}"
            ),
            "player_id": row.player_id,
            "mode": row.mode,
            "requested_limit": row.requested_limit,
            "score_count": row.score_count,
            "status": row.status,
            "error_code": row.error_code,
            "cache": row.cache,
            "credentials": row.credentials,
            "api_slot": row.api_slot,
            "upstream_requests": row.upstream_requests,
            "duration_ms": row.duration_ms,
            "result_available": row.result_ciphertext is not None
            and (row.result_expires_at is None or as_utc(row.result_expires_at) > now_utc()),
        }

    def record_admin_event(
        self,
        subject: str | None,
        action: str,
        target: str | None = None,
        detail: dict | None = None,
    ) -> None:
        event_id = str(uuid.uuid4())
        now = now_utc()
        with self.sessions.begin() as session:
            session.add(
                AdminAuditEvent(
                    id=event_id,
                    created_at=now,
                    subject=subject,
                    action=action,
                    target=target,
                    detail_ciphertext=self.cipher.encrypt_json(
                        detail, context=f"admin-audit:{event_id}"
                    ),
                    expires_at=now + timedelta(days=self.admin_audit_retention_days),
                )
            )
