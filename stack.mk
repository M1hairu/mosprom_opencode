# Пресет web-fullstack: FastAPI (uv, pytest, ruff, SQLAlchemy 2, Alembic) + React/Vite/TS
# (Vitest, Playwright). make demo поднимает docker compose: db, api, web (docker-compose.yml).
# Контракт целей — Makefile шаблона.
STACK := web-fullstack
UV := cd backend && uv run --frozen
# Коммит сборки для /api/health; -dirty — есть незакоммиченные правки в отслеживаемых файлах.
GIT_SHA := $(shell git rev-parse HEAD 2>/dev/null || echo unknown)$(shell git diff --quiet HEAD 2>/dev/null || echo -dirty)
# Источник — Pydantic в backend/src/api/contracts.py; json2ts пишет web/src/contracts.ts.
# PYTHONUTF8=1: на Windows stdout Python в cp1251 портит «—» в описаниях схемы (#117).
CONTRACTS_GEN := (cd backend && PYTHONUTF8=1 uv run --frozen python -m api.schema_export) \
  | (cd web && node_modules/.bin/json2ts --unreachableDefinitions --no-additionalProperties \
     --unknownAny --bannerComment "// Generated from FastAPI OpenAPI (backend/src/api/contracts.py). Do not edit: make contracts")
HOST_PORT = $$(docker compose port $(1) | sed 's/.*://')

.PHONY: format models seed stack-setup stack-lint stack-check stack-demo stack-eval stack-eval-final stack-e2e contracts deploy

stack-setup:
	cd backend && uv sync --frozen
	cd web && npm ci --no-audit --no-fund

contracts:       ## web/src/contracts.ts из OpenAPI FastAPI — после правки backend/src/api/contracts.py
	@set -o pipefail; tmp=$$(mktemp); trap 'rm -f $$tmp' EXIT; $(CONTRACTS_GEN) > $$tmp \
	  && cat $$tmp > web/src/contracts.ts && echo "web/src/contracts.ts обновлён"

stack-lint:
	$(UV) ruff check src tests migrations
	$(UV) ruff format --check src tests migrations
	@set -o pipefail; tmp=$$(mktemp); trap 'rm -f $$tmp' EXIT; $(CONTRACTS_GEN) > $$tmp \
	  || { echo "генерация контракта упала" >&2; exit 1; }; \
	  diff -u web/src/contracts.ts $$tmp >&2 || { echo "web/src/contracts.ts устарел: make contracts" >&2; exit 1; }; \
	  echo "web/src/contracts.ts совпадает с OpenAPI"
	cd web && npm run -s typecheck && npm run -s build

stack-check: stack-lint
	$(UV) pytest
	cd web && npm run -s test

stack-demo:
	GIT_SHA=$(GIT_SHA) docker compose up -d --build --wait \
	  || { docker compose ps -a; docker compose logs --tail=30; exit 1; }
	@echo "демо: http://localhost:$(call HOST_PORT,web 80)   API: http://localhost:$(call HOST_PORT,api 8000)/api/health"

stack-eval:
	$(UV) python ../scripts/eval_harness.py --checks src/api/checks.py \
	  --cases ../eval/cases.json --baseline ../eval/baseline.json

stack-eval-final:
	@[ -n "$(HOLDOUT_DIR)" ] || { echo "stack-eval-final запускает только make eval-final" >&2; exit 2; }
	$(UV) python ../scripts/eval_harness.py --checks src/api/checks.py \
	  --holdout-dir "$(HOLDOUT_DIR)" --baseline ../eval/baseline.json

# Сквозной сценарий на том же compose, что видит жюри.
# Планшет и админка входят ролями (#36): пароль из .env; пустой — случайный на этот прогон. Стек после
# e2e работает с ним до следующего make demo, а make demo снова берёт пароль из .env.
role_password = $(or $(shell sed -n 's/^$(1)_PASSWORD=//p' .env 2>/dev/null),$(shell od -An -N12 -tx1 /dev/urandom | tr -d ' \n'))
stack-e2e: export MANAGER_PASSWORD := $(call role_password,MANAGER)
stack-e2e: export EDITOR_PASSWORD := $(call role_password,EDITOR)
stack-e2e: export EXPERT_PASSWORD := $(call role_password,EXPERT)
stack-e2e: stack-demo
	docker compose exec -T api alembic check
	# The admin spec edits the published document: the database needs one (repeat writes nothing).
	docker compose exec -T api python -m api.seed --plan plan-219.json
	base=http://localhost:$(call HOST_PORT,web 80); cd web && npx playwright install chromium >/dev/null \
	  && E2E_BASE_URL=$$base E2E_MANAGER_PASSWORD=$$MANAGER_PASSWORD E2E_EDITOR_PASSWORD=$$EDITOR_PASSWORD \
	     E2E_EXPERT_PASSWORD=$$EXPERT_PASSWORD npx playwright test

deploy:          ## выкладка origin/main на сервер команды (README, «Выкладка»); DRY_RUN=1 — только шаги
	@bash scripts/deploy.sh $(if $(DRY_RUN),--dry-run)

format:          ## формат Python в backend/
	$(UV) ruff check --select I --fix src tests migrations
	$(UV) ruff format src tests migrations

seed:            ## импорт content/ в документ hall-219; повтор без изменений ничего не пишет
	docker compose exec -T api python -m api.seed --plan $(or $(PLAN),plan-219.json)

models:          ## 3D-модели экспонатов (*.glb) из релизов GitHub → web/public/models и web/src/planner/models.json (#354)
	@python3 scripts/fetch_models.py
