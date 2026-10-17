import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "deploy" / "deploy.sh"


@pytest.mark.parametrize("failure", ["pull", "up", "health", "none"])
def test_deployment_restores_config_and_tag_together(tmp_path, failure):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text("""#!/bin/bash
cat compose.yaml .env.deploy >> calls
if [[ "$*" == *" exec "* ]]; then
  if [ "$FAILURE" = health ]; then echo 500; else echo 200; fi
  exit 0
fi
if grep -q new compose.yaml && [[ " $* " == *" $FAILURE "* ]]; then exit 1; fi
""")
    docker.chmod(0o755)
    sleep = binaries / "sleep"
    sleep.write_text("#!/bin/bash\nexit 0\n")
    sleep.chmod(0o755)
    old = {
        "compose.yaml": "old-compose",
        "Caddyfile": "old-caddy",
        ".env.deploy": "OTHER=value\nIMAGE_TAG=old\n",
    }
    for name, value in old.items():
        (tmp_path / name).write_text(value)
    stage = tmp_path / ".incoming-new"
    stage.mkdir()
    (stage / "compose.yaml").write_text("new-compose")
    (stage / "Caddyfile").write_text("new-caddy")
    result = subprocess.run(
        ["bash", str(SCRIPT), str(tmp_path), "new", "exec", "http://localhost/health", "api"],
        env={**os.environ, "PATH": f"{binaries}:{os.environ['PATH']}", "FAILURE": failure},
        capture_output=True,
        text=True,
    )
    assert result.returncode == (0 if failure == "none" else 1), result.stderr
    if failure != "none":
        for name, value in old.items():
            assert (tmp_path / name).read_text() == value
        assert (tmp_path / "calls").read_text().endswith("old-composeOTHER=value\nIMAGE_TAG=old\n")
    else:
        assert (tmp_path / "compose.yaml").read_text() == "new-compose"
        assert (tmp_path / ".env.deploy").read_text() == "OTHER=value\nIMAGE_TAG=new\n"
    assert not stage.exists()
    assert not list(tmp_path.glob(".rollback.*"))
