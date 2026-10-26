from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class LoginChallenge(Base):
    __tablename__ = "admin_login_challenges"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    binding_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    verifier_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    nonce: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email_ciphertext: Mapped[str | None] = mapped_column(Text)
    name_ciphertext: Mapped[str | None] = mapped_column(Text)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ScoreQueryEvent(Base):
    __tablename__ = "score_query_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    query_ciphertext: Mapped[str | None] = mapped_column(Text)
    username_ciphertext: Mapped[str | None] = mapped_column(Text)
    username_lookup: Mapped[str | None] = mapped_column(String(64), index=True)
    player_id: Mapped[int | None] = mapped_column(BigInteger)
    mode: Mapped[str | None] = mapped_column(String(16))
    requested_limit: Mapped[int | None] = mapped_column(Integer)
    score_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    cache: Mapped[str | None] = mapped_column(String(24))
    credentials: Mapped[str | None] = mapped_column(String(16))
    api_slot: Mapped[int | None] = mapped_column(Integer)
    upstream_requests: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    result_ciphertext: Mapped[str | None] = mapped_column(Text)
    result_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


Index("ix_score_query_events_completed_at", ScoreQueryEvent.completed_at.desc())


class AdminAuditEvent(Base):
    __tablename__ = "admin_audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    subject: Mapped[str | None] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str | None] = mapped_column(String(255))
    detail_ciphertext: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
