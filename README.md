# Шоурум ЛАССАРД

Концепция шоурума в зале 219 и продукт: гид по маршруту, экраны зон, планировщик зала.

## Запуск демо

Нужны: `make`, `docker` (compose), `uv`, `node` 22+.

```bash
make setup      # .env из .env.example, зависимости backend и web
make demo       # docker compose: db, api, web; ждёт healthcheck
make seed       # импорт content/ в hall-219; повтор не создаёт версию
make models     # 3D-модели экспонатов (*.glb) из релизов GitHub → web/public/models; нужен gh
```

| Что | Адрес | Порт из `.env` |
|---|---|---|
| SPA: `/guide`, `/screen/<zone>`, `/planner` | http://localhost:8080 (все интерфейсы: телефон в той же сети) | `WEB_PORT` |
| API | http://127.0.0.1:8000/api/health | `API_PORT` |
| PostgreSQL | 127.0.0.1:5432 | `DB_PORT` |

`make demo` печатает фактические адреса.

Гид и экран зоны показывают опубликованную версию документа площадки, без сети —
последнюю полученную. Публикации нет — данные `content/` этой сборки. `make seed` публикует
`content/` в пустую базу. После первой публикации правки `content/` приходят черновиком:
их проверяет и публикует редактор через API (`/api/sites/hall-219`, роль `editor`). Правка `backend/src/api/contracts.py` — затем
`make contracts`: он обновляет `web/src/contracts.ts`. `make lint` падает на устаревшем файле.

3D-план `/planner` показывает экспонаты моделями GLB
(`web/public/models/`). Нет модели или файл не загрузился — коробка по размеру из плана.
Модель — в релиз GitHub файлом `<id объекта или типа>.glb` (например, `ot_smart_base.glb`),
без сжатия Draco. Затем `make models` и PR: репозиторий приватный, сайт берёт файлы из `main`.

## Документ площадки и роли

API хранит версии плана, зон, маршрутов, фактов и каталога. Редактор сохраняет черновик
и публикует его после проверки контента и норм. Откат создаёт новую проверенную версию.
`GET /api/sites/hall-219/document` открыт без входа; до первой публикации возвращает 404.

В `.env` задайте `EDITOR_PASSWORD`, `MANAGER_PASSWORD`, `EXPERT_PASSWORD` для логинов
`editor`, `manager`, `expert` (HTTP Basic). Пустое значение отключает роль. Пароли
передаются API в локальном и серверном compose. Менеджер управляет визитами, редактор —
документом.
На публичном сервере используйте HTTPS.

Ограничение MVP: `POST /api/sites/{site}/leads` (заявка гостя) без входа и без лимита запросов.

`make seed` выбирает `plan-219.json` и добавляет в него типы объектов всех планов `content/`.
Первый корректный импорт публикуется. Импорт не публикует ошибочные данные
и не заменяет правки редактора. Подробнее: [контракт, роли и импорт](backend/src/api/README.md).

## Выкладка

Публичная ссылка: **https://lassard.nedovost.org** (VPS M1hairu, #8). Запасной адрес без
DNS — https://lassard.5-129-231-165.sslip.io.
Рендеры концепции (39 кадров, Blender Cycles) — https://lassard.nedovost.org/renders/index.html
(статика `web/public/renders/`, #223).

### Выкладка на VPS (работает сейчас)

На VPS нет root и Docker, порты 80 и 443 держит общий Caddy. Схема: Caddy (HTTPS) →
статика `web/dist` и `/api/*` → uvicorn `127.0.0.1:8450` → PostgreSQL 16 (роль и база
`lassard`). Файлы — `deploy/vps/`.

Влили в `main` — обычно через 1–3 минуты это на сайте. Таймер `lassard-update.timer` раз в
минуту сверяет `origin/main` и запускает `update.sh`: `uv sync`, `npm run build`, выпуск в
`releases/<sha>`, перезапуск API (миграции — до старта). Ссылка `www` переходит на новый
выпуск только после ответа `/api/health` с новым SHA (ожидание — до 4 минут). Сборка или
API не прошли — скрипт возвращает API на прошлый выпуск, откатывает миграции нового кода и
пишет коммит в `failed-rev`. Этот коммит больше не пробуем: выложится следующий коммит в
`main` или `update.sh --force`. Проверка:

```bash
curl -s https://lassard.nedovost.org/version.txt   # = git rev-parse origin/main
curl -s https://lassard.nedovost.org/api/health    # тот же SHA
```

На сервере: журнал — `journalctl --user -u lassard-update`; выложить сразу —
`~/apps/lassard/deploy/update.sh --force` (идёт выкладка таймера — скрипт скажет и выйдет).

Разреженный клон на сервере (`~/apps/lassard/repo`) не содержит `deploy/`. Правка
`deploy/vps/*` в `main` на сервер сама не попадает: скопируйте файл по таблице ниже.

Установка на сервере (один раз; `~/etc/Caddyfile` — общий файл сайтов):

| Файл в репозитории | Куда на сервере |
|---|---|
| `deploy/vps/update.sh` | `~/apps/lassard/deploy/update.sh` |
| `deploy/vps/lassard*.service`, `lassard-update.timer` | `~/.config/systemd/user/` |
| `deploy/vps/lassard.caddy` | `~/etc/lassard.caddy`, строка `import` в `~/etc/Caddyfile` |

```bash
git clone --filter=blob:none --no-checkout git@github.com:IR630/mosprom.git ~/apps/lassard/repo
git -C ~/apps/lassard/repo sparse-checkout set --no-cone /backend/ /web/ /content/
git -C ~/apps/lassard/repo checkout main
mkdir -p ~/apps/lassard/releases ~/logs/caddy
# ~/apps/lassard/.env: одна строка DATABASE_URL=postgresql+psycopg://…, chmod 600
systemctl --user daemon-reload && systemctl --user enable lassard.service
~/apps/lassard/deploy/update.sh --force
systemctl --user enable --now lassard-update.timer
~/bin/caddy validate --config ~/etc/Caddyfile && systemctl --user reload caddy
```

### Сервер с Docker: `make deploy`

Схема: Caddy (HTTPS, Let's Encrypt) → nginx (SPA,
`/api` → api) → FastAPI → PostgreSQL. Файлы — `deploy/compose.yml`, `deploy/caddy/Caddyfile`.

Сервер:

- Docker Engine 25 или новее (`start_interval` в healthcheck), `docker compose` v2 с `--wait`, `tar`.
- Пользователь `DEPLOY_USER` запускает `docker` без `sudo`.
- Порты 80 и 443 (TCP и UDP) открыты и свободны: системный nginx или apache остановите.
- A-запись домена указывает на сервер. IP-адрес вместо домена скрипт не принимает.
- Сервер сам собирает образы. Нужен доступ к Docker Hub (`postgres`, `node`, `nginx`,
  `caddy`), ghcr.io (`uv`), npm и PyPI.
- Память: `npm ci` и сборка Vite прошли в контейнере с пределом 1 ГБ, пик — 730 МиБ
  (замер: `docker run -m 1g node:22-slim`, `memory.peak` cgroup). Старый стек в это время
  работает. Оценка — не меньше 2 ГБ или 1 ГБ и swap.

Docker Hub из РФ может ответить 403. Заранее выполните на сервере:

```bash
docker pull caddy:2.11-alpine postgres:18-alpine
```

Ответ 403 — укажите зеркало в `registry-mirrors` файла `/etc/docker/daemon.json` и
перезапустите `docker`.

Команду запускайте из основного клона: в worktree нет `.env`. В `.env` заполните строки
`DEPLOY_*` (образец — `.env.example`):

| Переменная | Что |
|---|---|
| `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_PORT` | адрес сервера, пользователь SSH, порт SSH |
| `DEPLOY_SSH_KEY` | путь к закрытому ключу SSH |
| `DEPLOY_DIR` | каталог на сервере от `$HOME` (по умолчанию `lassard`) |
| `DEPLOY_DOMAIN`, `DEPLOY_ACME_EMAIL` | домен сайта, e-mail для Let's Encrypt |

```bash
make deploy DRY_RUN=1   # шаги без SSH: проверьте адрес и домен
make deploy             # origin/main → сервер → проверка SHA
```

`make deploy` выкладывает `origin/main`, а не локальную ветку. Домен пишите без схемы:
`shop.example.ru`, а не `https://shop.example.ru`. Первая выкладка создаёт на сервере
`~/$DEPLOY_DIR/.env` со случайным паролем PostgreSQL. Скрипт ждёт ответа сайта до 5 минут.
Затем он печатает SHA `origin/main`, `/version.txt`, `/api/health` и код ответа `/`. SHA не
совпал — код выхода 1. Сайт не ответил — скрипт печатает вероятные причины. Проверка вручную:

```bash
curl -sI https://<домен>/              # HTTP/2 200
curl -s https://<домен>/version.txt    # = git rev-parse origin/main
```

