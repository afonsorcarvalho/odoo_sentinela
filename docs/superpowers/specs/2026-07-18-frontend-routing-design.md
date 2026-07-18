# Design — Frontend Sentinela CME: Roteamento (Overview ↔ Detalhe do Sensor)

> Spec de implementação. Terceira fatia da Fase 4, conectando as duas telas
> já prontas (`docs/superpowers/specs/2026-07-18-frontend-sensor-detail-design.md`,
> `docs/superpowers/specs/2026-07-18-frontend-overview-design.md`). Sem mudança
> de design visual — só navegação.

## 1. Objetivo e escopo

Conectar `OverviewPage` (`/`) e `SensorDetailPage` (`/sensor/:code`) via
`react-router`. Clicar num `AreaCard` navega pro sensor daquela área (hoje 1
sensor/área — sem ambiguidade). `SensorDetailPage` ganha link "← Voltar" pra
Overview.

Fora de escopo: múltiplos sensores por área (Site→Área, fatia futura),
qualquer mudança de design visual.

## 2. Biblioteca

`react-router` (v7, pacote `react-router` — sucessor unificado do
`react-router-dom`, API idêntica pra este uso). SPA pura, sem SSR — usa
`createBrowserRouter`/`RouterProvider` ou `BrowserRouter`+`Routes`+`Route`
(decisão de detalhe da implementação, ambos válidos; `BrowserRouter` é mais
simples pra 2 rotas e suficiente aqui).

## 3. Rotas

| Path | Componente | Origem do `code` |
|---|---|---|
| `/` | `OverviewPage` | — |
| `/sensor/:code` | `SensorDetailPage` | `useParams().code` |

`SensorDetailPage` já recebe `code` como prop — só muda **quem** fornece o
valor (antes fixo em `App.tsx`, agora do param da URL). Componente em si não
muda.

## 4. Navegação

- `AreaCard` ganha um `Link` (react-router) envolvendo o cartão, apontando
  pro `sensor_code` do (único) sensor da área — `to={`/sensor/${group.sensors[0].sensor_code}`}`.
  Card inteiro clicável (mantém a UX de "cartão como link"), com `:hover`/
  `:focus-visible` sutil pra indicar interatividade (novo — cartão hoje não
  tem estado de hover/foco, pois não era interativo).
- `SensorDetailPage` ganha um link "← Voltar" no topo do header, `to="/"`.

## 5. Wiring

- `App.tsx`: `BrowserRouter` + `Routes`/`Route` envolvendo as duas páginas.
- `main.tsx`: sem mudança (router fica dentro de `App`, não em `main`).

## 6. Testes

1. `AreaCard`: renderiza como link navegável pro `sensor_code` certo (via
   `MemoryRouter` de teste).
2. `App`/roteamento: navegar pra `/sensor/TEMP-EXP-01` renderiza
   `SensorDetailPage` com o código certo; navegar pra `/` renderiza
   `OverviewPage`.
3. Fluxo: clicar num cartão na Overview navega pro Detalhe; clicar "Voltar"
   volta pra Overview (teste de integração com `MemoryRouter` + `userEvent`).

## 7. Entregáveis

- `react-router` instalado.
- `AreaCard` clicável (Link).
- `SensorDetailPage` com link de volta.
- `App.tsx` com as 2 rotas.
- Suite verde; verificação visual real (hover/foco do cartão, navegação de
  fato funcionando no browser).
