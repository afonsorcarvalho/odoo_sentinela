# Sentinela CME — Dashboard

SPA em React + TypeScript + Vite que exibe um dashboard único e fundido
(rota `/`) com visão geral das áreas/sensores, painel de alarmes, detalhe do
sensor selecionado e cauda ao vivo em gráfico ECharts. As rotas antigas
`/area/:areaCode` e `/sensor/:code` redirecionam para `/` com os mesmos
parâmetros via query string (`?area=` / `?sensor=`).

- `npm run dev` — sobe o servidor de desenvolvimento.
- `npm test` — roda a suíte de testes (Vitest).
- `npm run build` — build de produção.

## Variáveis de ambiente

Copie `.env.example` para `.env.local` e ajuste os valores. Todas as
variáveis abaixo são lidas em tempo de build/dev pelo Vite (`import.meta.env`):

- `VITE_API_MODE` — `mock` (dados simulados, sem backend) ou `real` (usa a API FastAPI). Padrão seguro: `mock`.
- `VITE_API_BASE_URL` — URL base da API FastAPI, usada apenas quando `VITE_API_MODE=real`.
- `VITE_UNIT_NAME` — nome da unidade/hospital exibido no topo do dashboard.
- `VITE_DEMO_MODE` — `true` ativa o banner e os controles de simulação de não conformidade (uso em demos/apresentações).

Ver `.env.example` para valores de exemplo.
