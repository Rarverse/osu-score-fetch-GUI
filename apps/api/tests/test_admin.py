import base64
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from test_usage import _scores

from app.admin.logs import LogSearch, LokiClient
from app.admin.oidc import has_required_authentication, has_role
from app.config import Settings
from app.main import create_app


def admin_settings(tmp_path) -> Settings:
    key = base64.urlsafe_b64encode(b"a" * 32).decode()
    lookup = base64.urlsafe_b64encode(b"b" * 32).decode()
    return Settings(
        _env_file=None,
        cache_path=tmp_path / "cache",
        stats_path=tmp_path / "stats.json",
        admin_enabled=True,
        admin_secure_cookies=False,
        database_url="sqlite+pysqlite:///:memory:",
        admin_public_origin="http://localhost:8000",
        oidc_issuer="https://identity.example.test",
        oidc_client_id="admin-client",
        oidc_client_secret="test-client-secret",
        oidc_redirect_uri="http://localhost:8000/api/admin/auth/callback",
        audit_encryption_key=key,
        audit_lookup_key=lookup,
    )


def admin_app(tmp_path):
    app = create_app(admin_settings(tmp_path))
    app.state.admin_store.create_schema()
    return app


def test_admin_is_disabled_and_protected_by_default(tmp_path):
    client = TestClient(create_app(Settings(_env_file=None, cache_path=tmp_path)))
    assert client.get("/api/admin/session").json() == {
        "enabled": False,
        "authenticated": False,
    }
    assert client.get("/api/admin/v1/overview").status_code == 404
    assert client.get("/api/admin/auth/login").status_code == 404


def test_server_side_session_and_csrf_logout(tmp_path):
    app = admin_app(tmp_path)
    token, csrf, _expires = app.state.admin_store.create_session(
        subject="admin-1", email="admin@example.test", name="Admin"
    )
    client = TestClient(app)
    client.cookies.set("raru_admin_session", token)
    status = client.get("/api/admin/session")
    assert status.status_code == 200
    assert status.json()["authenticated"] is True
    assert status.json()["email"] == "admin@example.test"
    assert client.get("/api/admin/v1/overview").status_code == 200
    monitoring = client.get("/api/admin/v1/monitoring")
    assert monitoring.json() == {"configured": False, "targets": []}
    assert monitoring.headers["Cache-Control"] == "no-store"
    assert (
        client.post("/api/admin/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    )
    assert client.post("/api/admin/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/admin/session").json()["authenticated"] is False


def test_query_audit_is_encrypted_and_returns_exact_result(tmp_path):
    app = admin_app(tmp_path)
    app.state.osu.get_user_scores = lambda *_args: _scores("mania", 123, "PrivatePlayer")
    token, _csrf, _expires = app.state.admin_store.create_session(
        subject="admin-1", email="admin@example.test", name="Admin"
    )
    client = TestClient(app)
    response = client.get("/api/v1/players/PrivatePlayer/scores?limit=20")
    assert response.status_code == 200

    client.cookies.set("raru_admin_session", token)
    items = client.get("/api/admin/v1/requests").json()["items"]
    assert len(items) == 1
    assert items[0]["query"] == "PrivatePlayer"
    assert items[0]["username"] == "PrivatePlayer"
    detail = client.get(f"/api/admin/v1/requests/{items[0]['id']}").json()
    assert detail["result"] == response.json()

    with app.state.admin_store.sessions() as session:
        from app.admin.models import ScoreQueryEvent

        stored = session.query(ScoreQueryEvent).one()
        assert "PrivatePlayer" not in stored.query_ciphertext
        assert "PrivatePlayer" not in stored.username_ciphertext
        assert "PrivatePlayer" not in stored.result_ciphertext


def test_query_audit_keeps_the_exact_error_response(tmp_path):
    app = admin_app(tmp_path)
    token, _csrf, _expires = app.state.admin_store.create_session(
        subject="admin-1", email="admin@example.test", name="Admin"
    )
    client = TestClient(app)
    response = client.get("/api/v1/players/PrivatePlayer/scores?mode=invalid")
    assert response.status_code == 422

    client.cookies.set("raru_admin_session", token)
    event_id = client.get("/api/admin/v1/requests").json()["items"][0]["id"]
    detail = client.get(f"/api/admin/v1/requests/{event_id}").json()
    assert detail["query"] == "PrivatePlayer"
    assert detail["result"] == response.json()


def test_oidc_callback_requires_authentik_password_mfa_and_group(tmp_path):
    app = admin_app(tmp_path)

    class FakeOIDC:
        claims = {}

        async def authorization_url(self):
            return "https://identity.example.test/authorize?state=test-state", {
                "state": "test-state",
                "binding": "test-binding",
                "nonce": "test-nonce",
                "verifier": "test-verifier",
            }

        async def exchange(self, code, verifier, nonce):
            assert (code, verifier, nonce) == ("test-code", "test-verifier", "test-nonce")
            return self.claims

    fake = FakeOIDC()
    app.state.oidc = fake
    client = TestClient(app)

    def begin_login():
        response = client.get("/api/admin/auth/login", follow_redirects=False)
        assert response.status_code == 302
        assert parse_qs(urlparse(response.headers["location"]).query)["state"] == ["test-state"]

    fake.claims = {
        "sub": "admin-1",
        "email": "admin@example.test",
        "email_verified": True,
        "name": "Admin",
        "amr": ["pwd"],
        "groups": ["raru-admin"],
    }
    begin_login()
    assert (
        client.get(
            "/api/admin/auth/callback?code=test-code&state=test-state", follow_redirects=False
        ).status_code
        == 403
    )

    fake.claims["amr"] = ["pwd", "mfa"]
    begin_login()
    response = client.get(
        "/api/admin/auth/callback?code=test-code&state=test-state", follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/admin"
    assert client.get("/api/admin/session").json()["authenticated"] is True


def test_authentik_claim_helpers_cover_groups_and_amr():
    assert has_role({"groups": ["raru-admin"]}, "groups", "raru-admin")
    assert not has_role({"groups": ["users"]}, "groups", "raru-admin")
    assert has_required_authentication({"amr": ["pwd", "mfa"]})
    assert not has_required_authentication({"amr": ["pwd"]})


def test_log_query_builder_only_accepts_bounded_structured_filters():
    loki = LokiClient(
        "http://loki:3100",
        tenant_id=None,
        environment="production",
        max_range_days=30,
        max_limit=500,
    )
    query = LogSearch(
        start=datetime.now(UTC) - timedelta(minutes=15),
        end=datetime.now(UTC),
        services=["api"],
        levels=["ERROR"],
        request_id="abc123",
        text='failure" | unwrap secret',
        limit=200,
    )
    rendered = loki._query(query)
    assert rendered.startswith('{environment="production",service_name=~"api"} | json')
    assert 'request_id="abc123"' in rendered
    assert rendered.endswith('|="failure\\" | unwrap secret"')
