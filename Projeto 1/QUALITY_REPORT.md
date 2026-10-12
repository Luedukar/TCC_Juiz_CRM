# Relatório de qualidade

**Projeto:** Orbit CRM  
**Data de execução:** 12 de outubro de 2026

## Resultado resumido

| Verificação | Resultado |
| --- | --- |
| Testes de backend (Pytest) | **12 passaram**, 0 falharam |
| Testes de frontend (Vitest + React Testing Library) | **3 passaram**, 0 falharam |
| Build de produção (TypeScript + Vite) | **Aprovado** |
| Auditoria npm (`npm audit`) | **0 vulnerabilidades** |

## Cobertura automatizada

### Backend — `backend/tests/test_api.py`

Os testes exercitam a API FastAPI com banco SQLite isolado por teste e verificam:

- vendedor autenticado recebe somente as oportunidades da própria carteira;
- chamadas sem autenticação não conseguem consultar o pipeline;
- vendedor não pode ler, editar, mover ou excluir oportunidade de outro vendedor;
- vendedor não pode transferir oportunidade para outro responsável;
- gestor consulta todas as oportunidades e movimenta negócios de qualquer carteira;
- cada movimentação grava a etapa de origem/destino e o usuário responsável no histórico;
- reordenação de etapas permitida ao gestor;
- rotação e rejeição de reuso de refresh token;
- limite de cinco logins por minuto;
- origem local do frontend permitida pela política CORS.

**Última execução:**

```text
12 passed, 2 warnings
```

Os avisos são de depreciação emitidos por `starlette.testclient` (uso de `httpx`) e pelo SlowAPI com a versão de Python instalada. Não falharam testes.

### Frontend — `frontend/src/App.test.tsx`

Os testes React Testing Library verificam:

- exibição dos negócios fornecidos pela API para a carteira autenticada;
- arrastar uma oportunidade para outra coluna envia o `stage_id` correto e atualiza a interface;
- erro de autorização da API restaura o card à etapa original e informa a falha ao usuário.

**Última execução:**

```text
Test Files  1 passed (1)
Tests       3 passed (3)
```

### Build e dependências

O comando `npm --prefix frontend run build` executou a verificação de tipos do TypeScript e gerou os artefatos de produção com Vite sem erros. `npm --prefix frontend audit` terminou com **0 vulnerabilidades** reportadas.

## Limitações da validação

- A suíte de backend usa SQLite para isolamento e velocidade; ela não substitui uma execução de integração contra PostgreSQL. O cliente `psql` não estava disponível neste ambiente para aplicar e validar `schema.sql` no PostgreSQL.
- A suíte de frontend testa a integração por mocks de `fetch`; não executa o navegador contra uma instância PostgreSQL real.
- A contagem de cobertura percentual de linhas não foi medida.
