# Spec técnica — Frontend (Dashboard de Monitoramento)

> Documento de especificação para implementação. Complementa `diretrizes_projeto.md` (seção 12) e `odoo_modelo_dados_spec.md`. Escrito para ser entregue a uma sessão de implementação (Claude no WSL2).

---

## 1. Arquitetura escolhida: híbrido (decidido)

O frontend é dividido em duas superfícies, cada uma na ferramenta onde é mais barata/adequada:

- **Telas administrativas e de configuração → Odoo nativo (OWL)**: cadastro de clientes, sites, áreas, hubs, coletores, sensores; configuração de limiares de alarme (`alarm.threshold`); e o *ciclo de vida operacional* do alarme (reconhecer, resolver). Isso já vem quase pronto dos modelos especificados em `odoo_modelo_dados_spec.md` — não faz sentido reconstruir em outra stack.
- **Dashboard de monitoramento voltado ao cliente → SPA React dedicada**: gauges ao vivo, gráficos de série temporal, painel de alarmes. É a vitrine do produto ("melhor usabilidade possível"), onde o paradigma do OWL atrapalharia. Superfície independente, com controle total de UX.

Ambas compartilham a **mesma identidade** (Odoo como provedor de identidade — seção 5), então "quem vê o quê" tem fonte de verdade única (`ir.rule` / `partner_id` do Odoo).

## 2. Alvo: web responsivo (decidido)

Uma base de código React, responsiva, cobrindo desktop e mobile via navegador. **Sem app nativo na v1.** Notificação push nativa de alarme (relevante em ambiente hospitalar) fica registrada como candidato a v2 (ver seção 11).

## 3. Mapa de dados — qual dado vem de onde

Este é o ponto central do frontend: ele conversa com **três** origens, cada uma para um tipo de dado.

| Tipo de dado | Origem | Transporte |
|---|---|---|
| **Valores ao vivo** (última leitura de cada sensor, estado de alarme corrente) | Broker MQTT interno, via nossa API de tempo real | Push: **SSE** (Server-Sent Events) ou WebSocket, do servidor para o browser |
| **Séries temporais históricas** (gráficos) | **TimescaleDB**, via nova API de leitura | HTTP (fetch sob demanda, com downsampling) |
| **Lista e ciclo de alarme** (reconhecer/resolver, histórico) | **Odoo** (`sensor_monitor.alarm.event`) | HTTP (API do Odoo) |
| **Metadados** (árvore de sites/áreas/sensores, limiares para desenhar linhas de limite, unidades) | **Odoo** | HTTP (API do Odoo) |

## 4. Caminho de tempo real (consequência da decisão de segurança já tomada)

O broker MQTT central **não é exposto publicamente** (decisão da diretriz — só acessível via OpenVPN). Os navegadores dos clientes acessam pela internet aberta e **não** estão na VPN. Portanto:

```
[Browser do cliente] --WSS/SSE (internet, autenticado)--> [Nossa API de tempo real]
                                                                  │ (rede interna)
                                                                  ▼
                                                    [Broker MQTT central interno]
```

- A API de tempo real assina o broker interno (server-side) e **retransmite para cada browser apenas os tópicos do tenant daquele usuário** — o isolamento multi-tenant é aplicado na API, não confiado ao browser.
- **Recomendação: SSE** para o feed ao vivo (não WebSocket). O fluxo é unidirecional (servidor → browser); o browser nunca precisa publicar nada. SSE é mais simples, roda sobre HTTP/2, reconecta automaticamente. WebSocket fica como alternativa se surgir necessidade bidirecional.
- **Consequência positiva para o item em aberto do broker**: como o browser nunca fala direto com o broker, o broker central pode seguir sendo **Mosquitto** (simples) — não há necessidade do EMQX (cuja vantagem seria auth/ACL por tenant para conexões diretas de browser, cenário que não ocorre aqui). O broker-local do Hub também segue Mosquitto, como já estava.

## 5. Autenticação e identidade

- **Odoo é o provedor de identidade.** O usuário faz login (credenciais do Odoo); um endpoint de auth valida contra o Odoo e emite um **token (JWT)** com o `partner_id` (e papel) embutido.
- Tanto a **API de leitura do Timescale** quanto a **API de tempo real** validam esse mesmo JWT e derivam dele o filtro de tenant — nenhuma das duas confia em parâmetro vindo do browser para decidir escopo.
- A SPA também usa o token para chamar a API do Odoo (config/alarmes/metadados), respeitando as `ir.rule`.
- Isso mantém a regra multi-tenant com fonte de verdade única no Odoo, evitando duplicar lógica de permissão em cada serviço.

## 6. Nova peça de backend: API de leitura do Timescale

Componente que ainda não existia na arquitetura — irmão do serviço de ingestão (um escreve, este lê).

- **Stack sugerida**: FastAPI (Python) — leve, async, fácil de colocar validação de JWT e de conversar com Postgres/Timescale.
- **Responsabilidades**:
  - Servir séries temporais por sensor/área/período, **já reduzidas (downsampled)** — nunca devolver milhões de pontos brutos ao browser.
  - Escolher a granularidade conforme a janela pedida: janelas longas (ex. "últimos 30 dias") vêm dos **continuous aggregates** do Timescale (média/mín/máx por hora ou dia); janelas curtas ("última 1h") podem vir do dado bruto. Regra de seleção de resolução a definir na implementação, mas o princípio (nunca varrer bilhões de linhas para pintar um gráfico) é fixo.
  - Aplicar o filtro de tenant (do JWT) em toda query — um cliente jamais consulta série de outro.
- **Não** é a mesma API que serve os alarmes (esses vêm do Odoo) nem os metadados (Odoo) — só série temporal.

## 7. Stack do frontend (React — decidido; libs recomendadas)

- **Vite + React (SPA)**, não Next.js — o dashboard é autenticado e atrás de login, sem necessidade de SSR/SEO; uma SPA pura é mais simples de deployar e operar.
- **TanStack Query (React Query)** para estado de servidor — cache, refetch e invalidação das chamadas ao Odoo e à API de leitura, com pouco boilerplate.
- **Gráfico de série temporal: uPlot** (via wrapper `uplot-react`) — minúsculo (~50KB) e altíssima performance com muitos pontos e atualização ao vivo, que é exatamente o caso. Trade-off: é de baixo nível (mais trabalho de estilização). Se a prioridade for "pronto e vistoso" ao custo de peso, ECharts é o meio-termo aceitável — decisão de detalhe delegada à implementação.
- **UI/componentes: Tailwind CSS + shadcn/ui** — base moderna, responsiva, sem lock-in pesado; bom para chegar rápido a uma UX limpa.
- **Tempo real**: cliente SSE nativo do browser (`EventSource`) consumindo a API de tempo real. (Se optarem por WebSocket, `mqtt.js` seria usado **apenas** se decidirem, contra a recomendação da seção 4, conectar o browser direto ao broker — não é o caminho recomendado.)

## 8. Estrutura de telas do dashboard (SPA)

Proposta inicial, a refinar com design/UX:

1. **Visão geral (overview)**: para o usuário do cliente, cartões por site/área com estado atual (verde/alarme) e contagem de alarmes ativos. Para o operador interno do SaaS, visão consolidada multi-cliente.
2. **Site → Área**: layout das áreas (expurgo, preparo, esterilização, arsenal) com os sensores de cada uma, valor ao vivo e indicação visual de dentro/fora de faixa.
3. **Detalhe do sensor**: gráfico de série temporal (histórico + cauda ao vivo), com as **linhas de limite** (min/max vigente, vindas do `alarm.threshold` do Odoo) desenhadas sobre o gráfico; seletor de janela temporal (1h / 24h / 7d / 30d / custom).
4. **Painel de alarmes**: alarmes ativos (do feed ao vivo) + histórico e ações de ciclo de vida (reconhecer/resolver — que gravam via API do Odoo em `alarm.event`).
5. **Relatórios de conformidade** (provável v1.x): exportação/visualização orientada à RDC 15 — ex. "% do tempo dentro de faixa por área/período", ocorrências de violação. Alimentado pelos continuous aggregates + `alarm.event`. Escopo exato a definir.

## 9. Downsampling e desempenho (amarração com o Timescale)

- O gráfico nunca recebe dado bruto de janelas longas — a API de leitura devolve o nível de agregação adequado à janela e à densidade de pixels do gráfico.
- A "cauda ao vivo" do gráfico (últimos minutos) é alimentada pelo feed SSE e anexada localmente, sem refetch — mantém o gráfico fluido em tempo real sem pressionar o banco.

## 10. Pontos delegados à sessão de implementação

1. Regra exata de seleção de resolução na API de leitura (quais janelas caem em qual continuous aggregate).
2. uPlot vs ECharts (decisão de detalhe entre performance pura e "pronto e vistoso").
3. SSE vs WebSocket para o feed ao vivo (recomendação: SSE).
4. Estrutura exata dos endpoints da API de leitura e da API de tempo real (contratos REST/SSE).
5. Mecanismo de emissão/renovação do JWT a partir do login Odoo (endpoint de auth dedicado vs. reaproveitar sessão do Odoo).
6. Design visual / biblioteca de componentes final (shadcn/ui é sugestão).

## 11. Pontos que ainda precisam de decisão de produto (não delegados)

1. **Notificação push nativa de alarme** (app mobile) — fora da v1 (só web responsivo decidido); reavaliar para v2, relevante em ambiente hospitalar onde o responsável precisa ser alertado longe da tela.
2. **Escopo dos relatórios de conformidade RDC 15** (tela 5) — o que exatamente precisa ser exportável/auditável para inspeção. Depende de conversa com quem conhece a rotina de auditoria da CME.
3. **Login do cliente final**: se o cliente acessa via portal Odoo (usuário Odoo) ou só pela SPA (que autentica contra o Odoo por trás) — conecta com o ponto em aberto equivalente na spec do Odoo (seção 10.3 de lá).

## 12. Componentes novos que esta decisão adiciona à arquitetura geral

Para atualizar a visão de sistema da diretriz:
- **API de leitura do Timescale** (FastAPI) — serve séries temporais downsampled ao frontend.
- **API de tempo real** (SSE/WSS) — assina o broker interno e retransmite por tenant ao browser. (Pode ser o mesmo serviço da API de leitura ou separado — decisão de implementação.)
- **Endpoint de autenticação/JWT** — emite token a partir da identidade Odoo, validado pelas duas APIs acima.
- **SPA React** — hospedada como aplicação estática servida sobre HTTPS.
