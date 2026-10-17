#!/usr/bin/env bash
set -euo pipefail
dir=$1
sha=$2
mode=$3
url=$4
service=$5
cd "$dir"
stage=".incoming-$sha"
backup=$(mktemp -d .rollback.XXXXXX)
for file in compose.yaml Caddyfile .env.deploy; do
  if [ -f "$file" ]; then cp -p "$file" "$backup/$file"; fi
done
rollback() {
  status=$?
  trap - EXIT
  if [ "$status" -ne 0 ] && { [ ! -f "$backup/compose.yaml" ] || [ ! -f "$backup/.env.deploy" ]; }; then
    echo "No complete previous deployment exists; keeping failed deployment files for recovery"
  elif [ "$status" -ne 0 ]; then
    echo "Deployment failed; restoring previous configuration and image tag"
    for file in compose.yaml Caddyfile .env.deploy; do
      if [ -f "$backup/$file" ]; then
        cp -p "$backup/$file" "$file"
      else
        rm -f "$file"
      fi
    done
    if [ -f compose.yaml ] && [ -f .env.deploy ]; then
      if ! docker compose --env-file .env.deploy -f compose.yaml up -d --wait --wait-timeout 120; then
        echo "Rollback startup failed; previous files remain restored"
      fi
    else
      echo "No complete previous deployment exists to restart"
    fi
  fi
  rm -rf "$backup" "$stage"
  exit "$status"
}
trap rollback EXIT
cp "$stage/compose.yaml" compose.yaml
cp "$stage/Caddyfile" Caddyfile
# Preserve all deployment variables, replacing only the image tag.
touch .env.deploy
grep -v -E '^IMAGE_TAG=' .env.deploy > "$stage/env" || true
printf 'IMAGE_TAG=%s\n' "$sha" >> "$stage/env"
mv "$stage/env" .env.deploy
if ! docker compose --env-file .env.deploy -f compose.yaml pull \
  || ! docker compose --env-file .env.deploy -f compose.yaml up -d --wait --wait-timeout 120; then
  exit 1
fi
ok=0
for _ in $(seq 1 30); do
  code="000"
  if [ "$mode" = "exec" ]; then
    # The api image is python slim and has no curl. Same urllib probe as its HEALTHCHECK.
    # A non-2xx response or a connection error exits before print, so code stays empty.
    code=$(docker compose --env-file .env.deploy -f compose.yaml exec -T "$service" \
      python -c 'import sys,urllib.request; print(urllib.request.urlopen(sys.argv[1], timeout=5).status)' \
      "$url" || true)
  else
    code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$url" || true)
  fi
  if [ "$code" = "200" ]; then
    ok=1
    break
  fi
  sleep 2
done
if [ "$ok" != "1" ]; then
  echo "Health check did not return 200"
  exit 1
fi
echo "Health check returned 200"
