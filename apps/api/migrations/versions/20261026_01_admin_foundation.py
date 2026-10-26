"""Create administrator sessions, query audit, and administrator audit tables."""

import sqlalchemy as sa
from alembic import op

revision = "20261026_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_login_challenges",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("binding_hash", sa.String(64), nullable=False),
        sa.Column("verifier_ciphertext", sa.Text(), nullable=False),
        sa.Column("nonce", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "admin_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("email_ciphertext", sa.Text()),
        sa.Column("name_ciphertext", sa.Text()),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("csrf_ciphertext", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_sessions_subject", "admin_sessions", ["subject"])
    op.create_table(
        "score_query_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False, unique=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("query_ciphertext", sa.Text()),
        sa.Column("username_ciphertext", sa.Text()),
        sa.Column("username_lookup", sa.String(64)),
        sa.Column("player_id", sa.BigInteger()),
        sa.Column("mode", sa.String(16)),
        sa.Column("requested_limit", sa.Integer()),
        sa.Column("score_count", sa.Integer()),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("cache", sa.String(24)),
        sa.Column("credentials", sa.String(16)),
        sa.Column("api_slot", sa.Integer()),
        sa.Column("upstream_requests", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("result_ciphertext", sa.Text()),
        sa.Column("result_expires_at", sa.DateTime(timezone=True)),
        sa.Column("metadata_expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_score_query_events_username_lookup", "score_query_events", ["username_lookup"]
    )
    op.create_index(
        "ix_score_query_events_completed_at", "score_query_events", [sa.text("completed_at DESC")]
    )
    op.create_table(
        "admin_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject", sa.String(255)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target", sa.String(255)),
        sa.Column("detail_ciphertext", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_audit_events_created_at", "admin_audit_events", ["created_at"])
    op.create_index("ix_admin_audit_events_subject", "admin_audit_events", ["subject"])


def downgrade() -> None:
    op.drop_table("admin_audit_events")
    op.drop_table("score_query_events")
    op.drop_table("admin_sessions")
    op.drop_table("admin_login_challenges")
