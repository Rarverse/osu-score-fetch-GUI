#!/bin/sh
# Root only long enough to create the data directories, then the server runs as osu.
set -eu
cache_path="${CACHE_PATH:-/var/lib/osu-score-api/cache}"
stats_path="${STATS_PATH:-/var/lib/osu-score-api/stats/usage.json}"
stats_dir=$(dirname "$stats_path")
mkdir -p "$cache_path" "$stats_dir"
chown -R osu:osu "$cache_path" "$stats_dir"
exec runuser -u osu -- "$@"
