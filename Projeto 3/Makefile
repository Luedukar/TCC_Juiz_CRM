.PHONY: db db-test test-backend test-frontend test report

export TEST_DATABASE_URL ?= postgresql+psycopg2://crm:crm@localhost:5433/crm_test

db:            ## Sobe o PostgreSQL de desenvolvimento
	cd backend && docker compose up -d db

db-test:       ## Sobe o PostgreSQL descartável dos testes
	cd backend && docker compose --profile test up -d db-test

test-backend:  ## pytest com JUnit e cobertura em backend/reports
	cd backend && mkdir -p reports && pytest --cov=app --cov-report=term-missing --cov-report=xml:reports/coverage.xml --junitxml=reports/junit.xml

test-frontend: ## Vitest com JUnit e cobertura em frontend/reports e frontend/coverage
	cd frontend && npm run test:ci

report:        ## Consolida os relatórios reais em docs/RESULTADOS_EXECUCAO.md
	python3 scripts/quality_report.py

test: test-backend test-frontend report  ## Roda tudo e gera o relatório (backend exige db-test no ar)
