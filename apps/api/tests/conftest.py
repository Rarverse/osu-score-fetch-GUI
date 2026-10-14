import pytest


@pytest.fixture(autouse=True)
def isolate_credentials_and_stats(monkeypatch, tmp_path):
    """Tests must not depend on the developer machine's osu! credentials or stats file."""
    monkeypatch.delenv("OSU_CLIENT_ID", raising=False)
    monkeypatch.delenv("OSU_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("STATS_PATH", str(tmp_path / "stats" / "usage.json"))
