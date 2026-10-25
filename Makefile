# Единый интерфейс сборки. Агенты, jury и submission-checklist вызывают только эти цели.
# Цели наполняет стек: stack.mk в корне (его копирует `make setup PRESET=<имя>`; стек с нуля —
# свой stack.mk по тому же контракту, README, «Стек с нуля»).
#
# Контракт stack.mk: STACK := <имя>; цели stack-setup, stack-lint, stack-check, stack-demo,
# stack-eval, stack-eval-final (получает HOLDOUT_DIR — распакованный holdout), stack-e2e.
SHELL := bash
PRESET ?=
empty :=
space := $(empty) $(empty)
PRESETS := $(subst $(space),|,$(notdir $(wildcard presets/*)))

-include stack.mk

define need_stack
	@[ -f stack.mk ] || { echo "стек не выбран: make setup PRESET=<$(PRESETS)> или свой stack.mk (README)" >&2; exit 2; }
endef

.PHONY: help setup lint check demo eval e2e root-tests

help:            ## список целей
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:[^#]*## /\t/' | sort

setup:           ## окружение; первый раз: make setup PRESET=<python-ml|web-fullstack|ros2>
	@git config core.hooksPath .githooks 2>/dev/null || true
	@[ -f .env ] || cp .env.example .env
ifneq ($(PRESET),)
	@bash scripts/setup-preset.sh $(PRESET)
	@$(MAKE) --no-print-directory stack-setup
else
	@if [ -f stack.mk ]; then $(MAKE) --no-print-directory stack-setup; \
	 else echo "хуки подключены; стек не выбран: make setup PRESET=<$(PRESETS)>"; fi
endif

# content/ по схемам (G1, G4, G5, G14) + тест валидатора на сломанном примере
CONTENT_CHECK := python3 scripts/check-content.py content && python3 tests/test_check_content.py -q

lint:            ## сборка и lint без тестов (finish.sh в режиме «финал»); без стека — синтаксис скриптов шаблона; всегда — content/ и формулировки
	@python3 scripts/check-wording.py && python3 tests/test_check_wording.py -q
	@if [ -f stack.mk ]; then $(CONTENT_CHECK) && $(MAKE) --no-print-directory stack-lint; else \
	  $(CONTENT_CHECK) || exit 1; \
	  echo "стек не выбран — lint скриптов шаблона"; \
	  for f in scripts/*.sh .claude/hooks/*.sh .githooks/*; do bash -n "$$f" || exit 1; done; \
	  python3 -m py_compile .claude/skills/hackathon-kickoff/kickoff.py scripts/codex-sync.py; fi

check:           ## lint + тесты + тест на каждую ловушку (режим «сборка»: перед PR, finish.sh); без стека — template-test
	@python3 scripts/check-wording.py && python3 tests/test_check_wording.py -q
	@if [ -f stack.mk ]; then bash scripts/check-traps.sh && $(MAKE) --no-print-directory root-tests && $(MAKE) --no-print-directory stack-check; else \
	  echo "стек не выбран — проверяю сам шаблон (make template-test)"; $(MAKE) --no-print-directory template-test; fi

demo:            ## поднять демо-путь (то, что увидит жюри)
	$(need_stack)
	@$(MAKE) --no-print-directory stack-demo

eval:            ## видимые eval-кейсы + baseline (тривиальный ответ из probe)
	$(need_stack)
	@$(MAKE) --no-print-directory stack-eval

e2e:             ## сквозной сценарий демо в роли пользователя
	$(need_stack)
	@$(MAKE) --no-print-directory stack-e2e

root-tests:      ## unittest из tests/: смета, план 219 (stdlib)
	python3 -m unittest discover -s tests -p 'test_*.py'

