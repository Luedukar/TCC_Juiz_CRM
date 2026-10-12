# Relatório de Qualidade

**Projeto:** CRM B2B · **Escopo:** backend (FastAPI/PostgreSQL) e frontend (React/TypeScript) · **Versão:** 0.1.0

> **Leia primeiro.** Este relatório descreve os testes criados e o que foi verificado até agora. A suíte completa
> **ainda não foi executada** no ambiente de desenvolvimento (sem PostgreSQL nem acesso para instalar dependências).
> Por isso os resultados da execução completa **não estão neste documento**: são gerados com números reais por
> `make test`, que grava `docs/RESULTADOS_EXECUCAO.md` (veja a seção 5). Nada abaixo é estimativa apresentada como resultado.

## 1. Objetivo e escopo

Garantir, de forma automatizada, os requisitos de maior risco do sistema: **controle de acesso por perfil**, **movimentação
correta dos cards do funil**, **autenticação/sessões**, **tratamento de erros** e **comportamento da interface quando a API
falha ou demora**. Ficam fora do escopo atual: testes de ponta a ponta em navegador, carga e varredura dinâmica de
segurança (ver seção 6).

## 2. Estratégia

| Nível | Ferramenta | O que valida | Banco |
|---|---|---|---|
| Unitário (backend) | pytest | Regras puras: hash/JWT, validações, limitador, escopo de carteira | Não |
| Integração (backend) | pytest + TestClient | API completa contra **PostgreSQL real** (triggers, enums, constraints, FKs compostas) | Sim (`*_test`) |
| Unitário (frontend) | Vitest | Lógica do Kanban (soltura, atualização otimista), formatação, cliente de API | Não |
| Componentes/páginas | Vitest + Testing Library | Cartão, banners, filtros, modal, login, fallback do quadro, visão gestor × vendedor | Não (API simulada) |

Decisões de projeto dos testes:

- **PostgreSQL real nos testes de integração**, e não SQLite: o comportamento crítico está no banco (trigger de histórico,
  restrição de posição deferrável, chave estrangeira composta de etapa/funil, índices parciais).
- **Proteção contra acidente**: a suíte recria o schema, então só roda se `TEST_DATABASE_URL` apontar para um banco
  cujo nome termine em `_test`.
- **Isolamento**: cada teste começa com as tabelas de dados truncadas (o funil padrão do `schema.sql` é preservado).
- Lógica de arrastar e soltar foi extraída em função pura (`resolveDrop`) para ser testável sem simular ponteiro no jsdom.

## 3. Inventário dos testes criados

Contagens de funções de teste por arquivo; o total de **casos esperados** inclui as parametrizações
(matriz de endpoints, CNPJs, senhas, temperaturas).

### Backend (pytest) — 171 funções, **196 casos esperados**

| Arquivo | Funções | Foco |
|---|---:|---|
| `tests/unit/test_security.py` | 13 | argon2; JWT expirado, assinatura inválida, `alg=none`, tipo errado, sem `exp`, payload adulterado; refresh tokens |
| `tests/unit/test_validators.py` | 17 | CNPJ (dígitos verificadores), senha forte, PATCH sem `null` em campo obrigatório, moeda, fuso horário |
| `tests/unit/test_ratelimit.py` | 9 | janela deslizante, só falhas contam, IP atrás de proxy |
| `tests/unit/test_permissions.py` | 9 | filtro de carteira (`scope_owned`), atribuição de responsável |
| `tests/integration/test_rbac_visibility.py` | 37 | **permissões de visualização** (ver 4) |
| `tests/integration/test_deal_movement.py` | 32 | **movimentação de cards** (ver 4) |
| `tests/integration/test_auth.py` | 29 | login, bloqueio, rate limit, rotação/reuso de refresh, sessões, usuários |
| `tests/integration/test_pipelines.py` | 12 | etapas customizáveis, reordenação, integridade |
| `tests/integration/test_error_handling.py` | 13 | formato único de erro, mensagens, 404/405/422/409/500/503 |

### Frontend (Vitest) — 10 arquivos, **90 casos esperados**

| Arquivo | Casos | Foco |
|---|---:|---|
| `lib/dnd.test.ts` | 13 | ponto de soltura: mesma coluna, outra coluna, coluna vazia, filtros ativos, entradas inválidas |
| `lib/boardOps.test.ts` | 14 | atualização otimista: ordem, totais, status ganho/perda, reabertura, imutabilidade |
| `lib/format.test.ts` | 9 | moeda, tempo relativo, `datetime-local` com fuso |
| `lib/api.test.ts` | 14 | Bearer, renovação de sessão (única e simultânea), conflito entre abas, falha de rede, timeout, 429, 502 |
| `components/DealCard.test.tsx` | 11 | temperatura, indicador de próxima ação, iniciais do responsável |
| `components/ConnectionBanner.test.tsx` | 6 | offline, API lenta, erro com dados salvos |
| `components/LostReasonModal.test.tsx` | 5 | motivo obrigatório, Esc/cancelar |
| `components/BoardToolbar.test.tsx` | 6 | resumo do funil, filtro de vendedor só para gestor, temperatura |
| `pages/BoardPage.test.tsx` | 7 | quadro, gestor × vendedor, termos LGPD, esqueleto, painel de erro, quadro salvo somente leitura |
| `pages/LoginPage.test.tsx` | 5 | credenciais inválidas, contagem regressiva do 429 |

## 4. Rastreabilidade: requisito → testes

| Requisito | Onde é verificado |
|---|---|
| **RBAC**: gestor vê tudo; vendedor só a própria carteira | `test_rbac_visibility` (visibilidade de negócios, quadro com totais, empresas, contatos, interações, próximas ações; escrita limitada; matriz de 10 endpoints exclusivos do gestor); `test_permissions`; `test_auth::test_role_claim_is_not_trusted_for_authorization`; `BoardToolbar`/`BoardPage` (interface) |
| Registro de outro vendedor não vaza existência | `test_rbac_visibility::test_rep_gets_404_for_someone_elses_deal_same_as_nonexistent` |
| **Movimentação** de cards (etapa e posição) | `test_deal_movement` (entre vizinhos, topo, fim, coluna vazia, rebalanceamento, 35 inserções seguidas), `dnd.test`, `boardOps.test` |
| Ganho/perda, motivo obrigatório, reabertura | `test_deal_movement::TestWonAndLost`; `LostReasonModal.test` |
| Histórico de movimentação e auditoria | `test_deal_movement` (trigger com `moved_by`, log `move`) |
| Permissão ao mover (card de outro, vizinho de outro) | `test_deal_movement::TestMovePermissions` |
| **JWT + refresh tokens** | `test_security`; `test_auth::TestAccessTokenValidation`, `TestRefreshTokens`; `api.test` |
| **Rate limiting** no login | `test_ratelimit`; `test_auth::TestLoginRateLimit`; `LoginPage.test` (429) |
| Bloqueio de conta | `test_auth::TestAccountLockout` |
| **Interceptadores globais de erro** | `test_error_handling`; `api.test` (erros amigáveis) |
| **Fallback do Kanban** (API lenta/fora do ar) | `BoardPage.test` (esqueleto, painel de erro, dados salvos), `ConnectionBanner.test`, `api.test` (timeout) |
| **LGPD**: consentimento, aceite de termos, anonimização, auditoria | `test_rbac_visibility::TestCompaniesAndContacts`; `test_auth::test_accept_terms_records_timestamp`; `BoardPage.test` (modal de termos) |
| Funil de etapas customizáveis | `test_pipelines` |
| Histórico de interações com data/hora | `test_rbac_visibility::TestInteractions` |
| Temperatura e próxima ação | `DealCard.test`; `test_rbac_visibility::TestNextActions`; `test_deal_movement::test_quick_edit_*` |
| Empresas e contatos (CNPJ, contato principal) | `test_validators`; `test_error_handling` |

## 5. Resultados das execuções

### 5.1 Evidências já obtidas durante o desenvolvimento

| Verificação | Resultado |
|---|---|
| 36 testes de lógica pura do frontend (`dnd`, `boardOps`, `format`) executados no Node com um shim mínimo do Vitest | **36 de 36 aprovados**, 0 falhas |
| Compilação de sintaxe de todos os módulos Python (`app`, `tests`, `scripts`) | Sem erros |
| Algoritmo de dígitos verificadores do CNPJ de teste, conferido de forma independente | Confere (válido e inválidos) |
| Gerador de relatório (`quality_report.py`) validado com relatórios sintéticos nos formatos pytest e Vitest | Funciona; sinaliza falha, ignorados e suíte ausente |

Essas execuções **não substituem** a suíte completa: os 36 testes cobrem apenas a lógica pura, e o shim não é o Vitest.

### 5.2 Execução completa (pendente)

Ainda não executados: os 196 casos do backend (unitários e de integração) e os 90 do frontend, além da checagem de tipos
(`tsc`) e do build. Para gerar os resultados reais:

```bash
make db-test        # PostgreSQL descartável dos testes
make test           # pytest + Vitest + docs/RESULTADOS_EXECUCAO.md
```

`docs/RESULTADOS_EXECUCAO.md` traz, por suíte e por arquivo: veredito, testes aprovados/falhos/ignorados, tempo, lista
de falhas com a mensagem e a cobertura (com os arquivos menos cobertos). No CI o mesmo relatório é anexado ao resumo
do job. Suíte ausente ou com testes ignorados aparece sinalizada, nunca como aprovada.

### 5.3 Onde esperar ajustes na primeira execução

Como os testes ainda não rodaram, estes são os pontos mais prováveis de precisar de correção:

- Detalhes de ambiente: versões de dependências, ordem de importação dos pacotes de teste, stubs do jsdom para o dnd-kit.
- Testes de `BoardPage` dependem da espera real das novas tentativas do `useBoard` (~3 s) e têm limite de 15 s.
- Mensagens e formatos exatos de erro do PostgreSQL/SQLAlchemy usados no tratamento de conflitos.
- Tipos do TypeScript (`npm run typecheck`) nos arquivos de teste e nos componentes.

## 6. Lacunas e riscos conhecidos

**Sem cobertura automatizada (hoje):**

- Formulário lateral (`DealDrawer`), painel de interações, `AuthContext` e a integração real do drag-and-drop no navegador.
- Ponta a ponta (Playwright/Cypress), acessibilidade automatizada (axe) e compatibilidade entre navegadores.
- Concorrência: dois usuários movendo o mesmo card, ou dois refresh simultâneos no servidor.
- Carga/desempenho do quadro com muitos negócios (o backend limita cards por etapa, mas não há medição).
- Varredura dinâmica de segurança (OWASP ZAP). Auditoria de dependências roda no CI de forma **não bloqueante**.
- Migrações de banco (hoje só o `schema.sql` baseline).

**Riscos de produto que os testes não eliminam:** refresh token em `localStorage`; limitador de taxa em memória;
LGPD sem retenção/exportação automáticas; mensagens dos termos sem revisão jurídica.

**Problemas identificados por revisão de código e já corrigidos** (não por falha de teste):

| Problema | Correção |
|---|---|
| Limite de login contava logins válidos: equipe atrás do mesmo IP seria bloqueada | Só falhas contam |
| Duas abas renovando a sessão juntas derrubavam tudo (parecia roubo de token) | Janela de tolerância no servidor e nova tentativa no cliente |
| IP inválido (ex.: host de teste) quebraria a gravação na coluna `INET` | Valida o IP antes de gravar |
| Excluir etapa com histórico/negócios removidos falhava com erro genérico | Mensagem clara (`stage_in_use`) |
| Filtros de listagem montados com colunas ORM como chave de dicionário | Lista de pares |
| Lógica de soltura embutida no componente, difícil de testar | Função pura com testes |

## 7. Critérios de qualidade propostos (a calibrar após a primeira medição)

| Critério | Meta |
|---|---|
| Falhas nas suítes | 0 |
| Testes de integração ignorados no CI | 0 (o job define `TEST_DATABASE_URL`) |
| Checagem de tipos e build do frontend | Sem erros |
| Cobertura de linhas (backend / frontend) | ≥ 80% / ≥ 70% — metas iniciais; ajustar após a primeira medição real e então exigir no CI |
| Vulnerabilidades altas em dependências | 0 (hoje apenas informativo) |

## 8. Como manter

- Todo defeito encontrado ganha um teste que o reproduz antes da correção.
- Mudança em regra de permissão exige atualizar `test_rbac_visibility` e a matriz de endpoints.
- Novo endpoint protegido entra em `PROTECTED` (e em `MANAGER_ONLY`, se exclusivo do gestor).
- Rode `make test` antes de abrir PR; o CI repete a execução e publica `RESULTADOS_EXECUCAO.md`.
