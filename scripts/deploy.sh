#!/usr/bin/env bash
# Deploy origin/main to the team server over SSH (README, «Выкладка»).
#   bash scripts/deploy.sh            # make deploy
#   bash scripts/deploy.sh --dry-run  # make deploy DRY_RUN=1: print the steps, no SSH
#
# Steps: git fetch → git archive origin/main | ssh tar → server .env (once, random
# POSTGRES_PASSWORD) → docker compose -f deploy/compose.yml up --build --wait →
# curl https://<domain>/version.txt and /api/health; both must equal origin/main.
# Variables: DEPLOY_* in the local .env (.env.example). A set environment variable wins.
# DEPLOY_ENV_FILE — another env file instead of .env (tests: /dev/null).
set -euo pipefail

dry=0
case "${1:-}" in
  --dry-run) dry=1 ;;
  "") ;;
  *) echo "использование: bash scripts/deploy.sh [--dry-run]" >&2; exit 2 ;;
esac

root="$(git rev-parse --show-toplevel)"
cd "$root"

# Read DEPLOY_* from .env; values already in the environment stay.
env_file="${DEPLOY_ENV_FILE:-.env}"
if [ -r "$env_file" ]; then
  while IFS='=' read -r key value; do
    [[ $key =~ ^DEPLOY_[A-Z_]+$ ]] || continue
    value="${value%\"}"; value="${value#\"}"
    [ -n "${!key:-}" ] || export "$key=$value"
  done < "$env_file"
fi

missing=()
for key in DEPLOY_HOST DEPLOY_USER DEPLOY_SSH_KEY DEPLOY_DOMAIN DEPLOY_ACME_EMAIL; do
  if [ -z "${!key:-}" ]; then
    missing+=("$key")
    printf -v "$key" '<%s>' "$key"
  fi
done
if [ ${#missing[@]} -gt 0 ] && [ $dry -eq 0 ]; then
  echo "нет в .env: ${missing[*]} (образец — .env.example, README «Выкладка»)" >&2
  exit 2
fi
# Caddy gets a Let's Encrypt certificate only for a bare domain name.
if [[ $DEPLOY_DOMAIN == *://* || $DEPLOY_DOMAIN == */* ]]; then
  echo "DEPLOY_DOMAIN=$DEPLOY_DOMAIN: нужен домен без схемы и пути, например shop.example.ru" >&2
  exit 2
fi
if [[ $DEPLOY_DOMAIN =~ ^[0-9.]+$ || $DEPLOY_DOMAIN == *:* ]]; then
  echo "DEPLOY_DOMAIN=$DEPLOY_DOMAIN: это IP-адрес, нужен домен с A-записью на сервер" >&2
  exit 2
fi
port="${DEPLOY_PORT:-22}"
dir="${DEPLOY_DIR:-lassard}"
key_path="${DEPLOY_SSH_KEY/#\~/$HOME}"
site="https://$DEPLOY_DOMAIN"
ssh_cmd=(ssh -i "$key_path" -p "$port" -o BatchMode=yes -o StrictHostKeyChecking=accept-new
  "$DEPLOY_USER@$DEPLOY_HOST")

step() { printf '\n== %s\n' "$*"; }
show() { printf '+ %s\n' "$*"; }

step "1. origin/main"
show git fetch --quiet origin main
if [ $dry -eq 0 ]; then git fetch --quiet origin main; fi
sha="$(git rev-parse origin/main)"
echo "коммит: $sha"

# Runs on the server: swap src/, create .env once, start compose. Args: dir sha domain email.
# shellcheck disable=SC2016  # expands on the server
remote_up='set -euo pipefail
dir=$1 sha=$2 domain=$3 email=$4
cd "$HOME/$dir"
[ -d src.new ]
rm -rf src.old
if [ -d src ]; then mv src src.old; fi
mv src.new src
if [ ! -f .env ]; then
  umask 077
  pw=$(tr -dc a-z0-9 </dev/urandom | head -c 32 || true)
  printf "POSTGRES_USER=lassard\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=lassard\n" "$pw" > .env
  echo "создан $HOME/$dir/.env (пароль PostgreSQL — случайный)"
fi
cd src
export GIT_SHA=$sha SITE_ADDRESS=$domain ACME_EMAIL=$email
dc() { docker compose --env-file ../.env -f deploy/compose.yml "$@"; }
dc up -d --build --wait --remove-orphans || { dc ps -a; dc logs --tail=30; exit 1; }
docker image prune -f >/dev/null'

step "2. код origin/main → $DEPLOY_USER@$DEPLOY_HOST:~/$dir/src"
show "git archive --format=tar $sha | ${ssh_cmd[*]} 'rm -rf ~/$dir/src.new && mkdir -p ~/$dir/src.new && tar -x -C ~/$dir/src.new'"
if [ $dry -eq 0 ]; then
  git archive --format=tar "$sha" \
    | "${ssh_cmd[@]}" "rm -rf ~/$dir/src.new && mkdir -p ~/$dir/src.new && tar -x -C ~/$dir/src.new"
fi

step "3. docker compose на сервере: db, api, web, caddy (HTTPS для $DEPLOY_DOMAIN)"
show "${ssh_cmd[*]} bash -s -- $dir $sha $DEPLOY_DOMAIN $DEPLOY_ACME_EMAIL  # скрипт ниже"
if [ $dry -eq 1 ]; then
  printf '    %s\n' "${remote_up//$'\n'/$'\n'    }"
else
  "${ssh_cmd[@]}" bash -s -- "$dir" "$sha" "$DEPLOY_DOMAIN" "$DEPLOY_ACME_EMAIL" <<< "$remote_up"
fi

step "4. проверка: $site"
show "curl $site/version.txt и $site/api/health — до 5 минут (выпуск сертификата)"
if [ $dry -eq 1 ]; then
  echo "dry-run: SSH и curl не запускал"
  if [ ${#missing[@]} -gt 0 ]; then echo "нет в .env: ${missing[*]}"; fi
  exit 0
fi
# Deadline 300 s; the last curl can add up to 10 s.
site_sha="" deadline=$((SECONDS + 300))
while :; do
  site_sha="$(curl -fsS --max-time 10 "$site/version.txt" 2>/dev/null || true)"
  [ "$site_sha" = "$sha" ] || [ $SECONDS -ge $deadline ] && break
  sleep 5
done
health="$(curl -fsS --max-time 10 "$site/api/health" 2>/dev/null || true)"
api_sha="$(sed -n 's/.*"sha" *: *"\([^"]*\)".*/\1/p' <<< "$health")"
status="$(curl -sS -o /dev/null -w '%{http_version} %{http_code}' --max-time 10 "$site/" || true)"

echo "origin/main:      $sha"
echo "/version.txt:     ${site_sha:-нет ответа}"
echo "/api/health sha:  ${api_sha:-нет ответа}"
echo "/:                HTTP/$status"
if [ "$site_sha" != "$sha" ] || [ "$api_sha" != "$sha" ] || [ "${status#* }" != 200 ]; then
  echo "выкладка не совпала с origin/main — см. вывод выше" >&2
  if [ -z "$site_sha" ]; then
    echo "сайт не ответил. Вероятные причины:" >&2
    echo "  - A-запись $DEPLOY_DOMAIN не указывает на $DEPLOY_HOST (проверка: dig +short $DEPLOY_DOMAIN);" >&2
    echo "  - порты 80 и 443 закрыты файрволом или заняты (системный nginx, apache);" >&2
    echo "  - Caddy не получил сертификат: на сервере docker logs --tail 50 lassard-caddy-1" >&2
  fi
  exit 1
fi
echo "готово: $site"
