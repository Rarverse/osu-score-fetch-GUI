import pytest


@pytest.fixture(autouse=True)
def isolate_credentials_and_stats(monkeypatch, tmp_path):
    """Tests must not depend on the developer machine's osu! credentials or stats file."""
    for suffix in ("", "_2", "_3"):
        monkeypatch.delenv(f"OSU_CLIENT_ID{suffix}", raising=False)
        monkeypatch.delenv(f"OSU_CLIENT_SECRET{suffix}", raising=False)
    monkeypatch.setenv("STATS_PATH", str(tmp_path / "stats" / "usage.json"))
