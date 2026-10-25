#!/usr/bin/env bash
# Deploy of origin/main on the team VPS without root and Docker (README, «Выкладка на VPS»).
# A new commit in origin/main → update ~/apps/lassard/repo in place, uv sync, build web into
# releases/<rev12>, restart the API (migrations run in ExecStartPre), wait for /api/health with
# the new SHA, then link www → release. A failed commit goes to failed-rev and is not tried again
# until the next commit or --force; the API goes back to the live release.
# Runs from lassard-update.timer.   ~/apps/lassard/deploy/update.sh [--force]
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

APP="$HOME/apps/lassard"
REPO="$APP/repo"
PORT=8450
ALEMBIC="$REPO/backend/.venv/bin/alembic"

exec 9>"$APP/.update.lock"
if ! flock -n 9; then
  echo "выкладка уже идёт — дождитесь её конца: journalctl --user -u lassard-update" >&2
  exit 0
fi

cd "$REPO"
git fetch --quiet origin main
rev=$(git rev-parse origin/main)
live=$(cat "$APP/live-rev" 2>/dev/null || echo none)
failed=$(cat "$APP/failed-rev" 2>/dev/null || echo none)
if [ "${1:-}" != "--force" ] && { [ "$rev" = "$live" ] || [ "$rev" = "$failed" ]; }; then
  exit 0
fi

set -a
. "$APP/.env"   # DATABASE_URL for alembic
set +a

# Each step ends with `|| return 1`: set -e does not work in a function called from `if`.
checkout() {  # $1 — commit: API code and its Python packages
  # The running API uses this tree too: if it crashes during a build, it restarts on the new code.
  git reset --hard --quiet "$1" || return 1
  (cd backend && uv sync --frozen --no-dev --quiet) || return 1
}

build() {  # $1 — commit; web build into releases/<rev12>
  local out="$APP/releases/${1:0:12}" lock
  lock=$(sha256sum web/package-lock.json | cut -d' ' -f1) || return 1
  if [ "$(cat web/node_modules/.lock-sha 2>/dev/null)" != "$lock" ]; then
    (cd web && npm ci --no-audit --no-fund --loglevel=error) || return 1
    echo "$lock" > web/node_modules/.lock-sha
  fi
  rm -rf web/dist
  (cd web && npm run -s build) || return 1
  rm -rf "$out.new" && cp -a web/dist "$out.new" || return 1
  rm -rf "$out.new/.vite"   # manifest of source modules: only the budget check needs it
  echo "$1" > "$out.new/version.txt"
  # Chunks of the live release younger than 3 h: a tab opened before the deploy still loads them.
  if [ -d "$APP/www/assets" ]; then
    find "$APP/www/assets/" -maxdepth 1 -type f -mmin -180 -print0 |
      while IFS= read -r -d '' f; do
        [ -e "$out.new/assets/${f##*/}" ] || cp -a "$f" "$out.new/assets/"
      done || return 1
  fi
  rm -rf "$out" && mv "$out.new" "$out"
}

start() {  # $1 — commit: restart the API with this SHA; true when /api/health answers it
  printf 'GIT_SHA=%s\n' "$1" > "$APP/sha.env"
  systemctl --user restart lassard.service || return 1
  for _ in $(seq 45); do
    curl -fsS -m 3 "http://127.0.0.1:$PORT/api/health" 2>/dev/null | grep -q "\"sha\":\"$1\"" && return 0
    sleep 2
  done
  return 1
}

db_revision() {
  (cd backend && "$ALEMBIC" current 2>/dev/null | awk 'NR == 1 { print $1 }') || true
}

db_rev=$(db_revision)
echo "сборка ${rev:0:7} (сейчас ${live:0:7})"
if checkout "$rev" && build "$rev" && start "$rev"; then
  ln -sfn "releases/${rev:0:12}" "$APP/www"
  echo "$rev" > "$APP/live-rev"
  rm -f "$APP/failed-rev"
  # Keep the 3 latest releases.
  ls -1t "$APP/releases" | tail -n +4 | while read -r old; do rm -rf "${APP:?}/releases/$old"; done
  echo "работает ${rev:0:7}"
  exit 0
fi

echo "$rev" > "$APP/failed-rev"
echo "сборка или запуск ${rev:0:7} не прошли. Повтор — следующий коммит в main или update.sh --force" >&2
[ "$live" = none ] && exit 1
# The new code may have migrated the database: its own migrations take it back.
if [ -n "$db_rev" ] && [ "$(db_revision)" != "$db_rev" ]; then
  (cd backend && "$ALEMBIC" downgrade "$db_rev") || echo "откат миграций до $db_rev не прошёл" >&2
fi
echo "возврат на ${live:0:7}" >&2
if checkout "$live" && { [ -d "$APP/releases/${live:0:12}" ] || build "$live"; } && start "$live"; then
  ln -sfn "releases/${live:0:12}" "$APP/www"
else
  echo "прошлый коммит тоже не отвечает — journalctl --user -u lassard" >&2
fi
exit 1
