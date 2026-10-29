SHELL := /bin/zsh
NODE_BIN := /opt/homebrew/opt/node@22/bin
PYTHON := .venv/bin/python
BACKEND := backend
FRONTEND := frontend
DB_URL_LOCAL := postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres

.PHONY: help db-up db-down db-reset seed backend frontend test unit e2e restore-drill cutover-dry cutover

help:
	@echo "TEI — desarrollo local"
	@echo ""
	@echo "  make db-up           Levanta Colima + Supabase local"
	@echo "  make db-down         Baja Supabase local"
	@echo "  make db-reset        Borra y rehace la base local + seed (destructivo)"
	@echo "  make seed            Carga TEI: maestros, comercial, agenda, viajes, POD, facturas"
	@echo "  make backend         Levanta FastAPI en http://localhost:8000"
	@echo "  make frontend        Levanta Next.js en http://localhost:3000"
	@echo "  make unit            Tests unitarios del núcleo"
	@echo "  make test            Toda la suite del núcleo contra Supabase local"
	@echo "  make e2e             Playwright E2E (frontend en :3000)"
	@echo "  make restore-drill   Backup + restore en base temporal + verificación"
	@echo "  make cutover-dry     Dry-run de migración legacy → núcleo"
	@echo "  make cutover         Migra legacy y congela su escritura"
	@echo ""
	@echo "  Login local: admin@tei.local / TEI2026!"
	@echo "  Roles: gerente, despacho, contador, tesoreria, taller, conductor, auditor"
	@echo "  Supabase Studio: http://127.0.0.1:54323"

db-up:
	@colima status >/dev/null 2>&1 || colima start --cpu 4 --memory 6 --disk 60 --vm-type=vz
	@# `supabase start` imprime las claves locales en stdout; se guardan en un log
	@# temporal para no filtrarlas en la salida de `make test`/`make e2e`.
	@supabase start > "$${TMPDIR:-/tmp}/tei-supabase-start.log" 2>&1 \
		|| { cat "$${TMPDIR:-/tmp}/tei-supabase-start.log"; exit 1; }
	@echo "Supabase local arriba (detalle en $${TMPDIR:-/tmp}/tei-supabase-start.log)"

db-down:
	@supabase stop

db-reset: db-up
	@supabase db reset
	@$(PYTHON) scripts/seed_local.py

seed: db-up
	@$(PYTHON) scripts/seed_local.py

backend:
	@cd $(BACKEND) && ../$(PYTHON) -m uvicorn app.main:app --reload --port 8000

frontend:
	@cd $(FRONTEND) && PATH="$(NODE_BIN):$$PATH" npm run dev

unit:
	@cd $(BACKEND) && ../$(PYTHON) -m pytest \
		tests/test_nucleo_tiempo.py \
		tests/test_nucleo_politicas.py \
		tests/test_nucleo_schemas.py \
		tests/test_nucleo_modelos.py \
		tests/test_nucleo_tarifas.py

test: db-up
	@# Credenciales del seed local (documentadas en `make help`); solo aplican a 127.0.0.1.
	@# Se pueden sobrescribir desde el entorno para CI u otra máquina.
	@cd $(BACKEND) && NUCLEO_TEST_DATABASE_URL="$${NUCLEO_TEST_DATABASE_URL:-$(DB_URL_LOCAL)}" \
		TEST_ADMIN_EMAIL="$${TEST_ADMIN_EMAIL:-admin@tei.local}" \
		TEST_ADMIN_PASSWORD="$${TEST_ADMIN_PASSWORD:-TEI2026!}" \
		TEST_CONTABILIDAD_EMAIL="$${TEST_CONTABILIDAD_EMAIL:-contador@tei.local}" \
		TEST_CONTABILIDAD_PASSWORD="$${TEST_CONTABILIDAD_PASSWORD:-TEI2026!}" \
		../$(PYTHON) -m pytest tests

e2e:
	@cd $(FRONTEND) && PATH="$(NODE_BIN):$$PATH" npm run test:e2e

restore-drill:
	@./scripts/restore_drill.sh

cutover-dry:
	@$(PYTHON) scripts/cutover_legacy.py --dry-run

cutover:
	@$(PYTHON) scripts/cutover_legacy.py --freeze
