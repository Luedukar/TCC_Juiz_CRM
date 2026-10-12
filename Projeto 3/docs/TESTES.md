# Testes automatizados (Entregável 4)

## Como executar

**Backend** (pytest; testes de integração usam PostgreSQL real)

```bash
cd backend
pip install -r requirements-dev.txt
docker compose --profile test up -d db-test
export TEST_DATABASE_URL=postgresql+psycopg2://crm:crm@localhost:5433/crm_test
pytest                                   # tudo
pytest tests/unit                        # só unitários (não precisam de banco)
pytest --cov=app --cov-report=term-missing
```

O banco precisa ter nome terminando em `_test`: a suíte recria o schema (`DROP SCHEMA public CASCADE`) e
recusa-se a rodar em qualquer outro banco. Sem `TEST_DATABASE_URL`, os testes de integração são ignorados.

**Frontend** (Vitest + React Testing Library)

```bash
cd frontend
npm install
npm test                 # uma execução
npm run test:coverage    # com cobertura
npm run typecheck
```

**Tudo de uma vez + relatório com os números reais**

```bash
make db-test && make test      # gera docs/RESULTADOS_EXECUCAO.md (veredito, contagens, falhas e cobertura)
```

**CI**: `.github/workflows/ci.yml` roda as duas suítes a cada push e publica JUnit/cobertura como artefatos.

## O que cada suíte cobre

| Arquivo | Foco |
|---|---|
| `backend/tests/unit/test_security.py` | argon2, JWT (expirado, assinatura, `alg=none`, tipo, adulterado), refresh tokens |
| `backend/tests/unit/test_validators.py` | CNPJ, senha forte, PATCH sem null em campo obrigatório, fuso horário em interações |
| `backend/tests/unit/test_ratelimit.py` | janela deslizante, só falhas contam, IP atrás de proxy |
| `backend/tests/unit/test_permissions.py` | filtro de carteira (`scope_owned`) e atribuição de responsável |
| `backend/tests/integration/test_rbac_visibility.py` | **permissões de visualização**: vendedor × gestor em negócios, quadro, empresas, contatos, interações, próximas ações, LGPD; matriz de endpoints exclusivos do gestor e protegidos |
| `backend/tests/integration/test_deal_movement.py` | **movimentação de cards**: etapa, posição entre vizinhos, rebalanceamento, ganho/perda, histórico, auditoria, permissões do movimento |
| `backend/tests/integration/test_auth.py` | login, bloqueio de conta, rate limit, rotação e reuso de refresh token, sessões |
| `backend/tests/integration/test_pipelines.py` | etapas customizáveis, reordenação, integridade |
| `backend/tests/integration/test_error_handling.py` | formato único de erro, mensagens amigáveis, 500/503 sem vazamento |
| `frontend/src/lib/dnd.test.ts`, `boardOps.test.ts` | resolução do ponto de soltura e atualização otimista do Kanban |
| `frontend/src/lib/api.test.ts` | renovação de sessão, falhas de rede, timeout, erros amigáveis |
| `frontend/src/components/*.test.tsx` | card, indicador de próxima ação, banner de conexão, filtros, modal de perda |
| `frontend/src/pages/*.test.tsx` | fallback do Kanban (esqueleto, painel de erro, dados salvos), visão do gestor × vendedor, login |
