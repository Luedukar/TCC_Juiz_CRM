# Frontend CRM

Aplicação React + TypeScript com quadro Kanban responsivo, drag-and-drop nativo, filtros de temperatura, indicadores de próximas ações e painel lateral para criar/editar oportunidades.

## Executar

1. Instale Node.js 20+.
2. Copie `.env.example` para `.env` e ajuste `VITE_API_URL` para o endereço da API.
3. Instale e inicie: `npm install`, depois `npm run dev`.
4. Para autenticar, informe e-mail, senha e ID do workspace existentes na base de dados.

A API deve permitir a origem do frontend em `CORS_ORIGINS` (por padrão `http://localhost:5173`). Veja também a configuração `.env.example` na raiz do backend. Para compilar a distribuição use `npm run build`.

A sessão mantém access/refresh tokens no armazenamento local do navegador; o refresh é renovado automaticamente após resposta 401. Falhas de rede ou uma requisição GET que exceda 15 segundos mostram uma mensagem e permitem repetir o carregamento. Durante a movimentação de cards, a interface atualiza imediatamente e desfaz a alteração caso a API recuse a operação.

