import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "deploy" / "deploy.sh"


@pytest.mark.parametrize("failure", ["pull", "up", "health", "none"])
@pytest.mark.parametrize("has_previous_nginx", [True, False])
def test_deployment_restores_config_and_tag_together(tmp_path, failure, has_previous_nginx):
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
        ".env.deploy": "OTHER=value\nIMAGE_TAG=old\n",
    }
    if has_previous_nginx:
        old["nginx.conf"] = "old-nginx"
    for name, value in old.items():
        (tmp_path / name).write_text(value)
    stage = tmp_path / ".incoming-new"
    stage.mkdir()
    (stage / "compose.yaml").write_text("new-compose")
    (stage / "nginx.conf").write_text("new-nginx")
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
        if not has_previous_nginx:
            assert not (tmp_path / "nginx.conf").exists()
        assert (tmp_path / "calls").read_text().endswith("old-composeOTHER=value\nIMAGE_TAG=old\n")
    else:
        assert (tmp_path / "compose.yaml").read_text() == "new-compose"
        assert (tmp_path / "nginx.conf").read_text() == "new-nginx"
        assert (tmp_path / ".env.deploy").read_text() == "OTHER=value\nIMAGE_TAG=new\n"
    assert not stage.exists()
    assert not list(tmp_path.glob(".rollback.*"))
