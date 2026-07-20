# Design: Reconexão SSE visível (badge "AO VIVO" → "Reconectando")

## Contexto

Os dados ao vivo chegam por **SSE** (`EventSource`) num único stream `/live`
multiplexado (`frontend/src/lib/api/real/liveApi.ts`, `sharedSource`), alimentado
por `pg_notify`→`asyncpg` no backend. Hoje o `Topbar`
(`frontend/src/components/Topbar.tsx`) mostra um badge **estático** verde "AO VIVO"
com um ponto pulsante — texto e cor fixos no JSX, sem qualquer relação com o estado
real da conexão.

O `EventSource` já reconecta sozinho quando a rede pisca (é o comportamento nativo
do browser em erro *transitório*), mas isso é **invisível**: se o Wi-Fi cai por 30s,
o badge continua dizendo "AO VIVO" enquanto nenhum dado chega. O operador não tem
como distinguir "sensor estável, sem mudança" de "conexão morta". Objetivo desta
melhoria: o badge deve refletir o estado da conexão — virar "Reconectando…" quando
o stream cai e voltar a "AO VIVO" quando reconecta — dando confiança de que o dado
mostrado é de fato ao vivo.

## Decisão de abordagem

**Estender o contrato `LiveApi` com um canal de estado de conexão** (`subscribeConnection`),
mantendo a máquina de estados **no módulo** `real/liveApi.ts` (onde vive o
`EventSource`), e manter o `Topbar` **apresentacional** recebendo o estado por prop
a partir de `DashboardPage`.

Justificativa:
- O projeto já separa mock↔real por trás dos contratos em `api/contracts.ts`. O
  estado de conexão é uma propriedade do transporte, então pertence ao `LiveApi`.
  O mock (`mock/liveApi.ts`, ticks por `setInterval`) não tem conexão de rede —
  reporta `'live'` sempre. A UI fica agnóstica do transporte, igual ao resto.
- A lógica de erro/reconexão precisa do `EventSource` real (`onopen`/`onerror`/
  `readyState`), que só existe em `real/liveApi.ts` e é um **singleton compartilhado**.
  Colocar a máquina de estados no módulo (variável de nível de módulo + 1 timer)
  — e não dentro de um hook — garante **uma** fonte da verdade e **um** timer de
  grace, independente de quantos componentes observam.
- `Topbar` recebe o estado por prop (como já recebe `healthy`/`unitName`), ficando
  puro e testável nos três estados visuais direto por prop, sem montar `EventSource`.

Alternativas descartadas: Context/store global (peso desnecessário — o seam de
contrato já é o ponto de propagação natural do projeto); derivar "desconectado" de
silêncio de dados (ver "Fora de escopo" — seria falso-positivo constante neste backend).

## Comportamento

### Estados de conexão

Três estados, derivados **exclusivamente** de `onopen`/`onerror` + `readyState` do
`EventSource` (nunca de chegada/ausência de dados — ver "Fora de escopo"):

| Estado | Origem | Badge (texto) | Cor | Ponto |
| --- | --- | --- | --- | --- |
| `live` | `onopen` disparou (readyState `OPEN`) | **AO VIVO** | `--color-good` | pulsante (`motion-safe:animate-pulse`) |
| `reconnecting` | `onerror` com `readyState === CONNECTING (0)` **e** grace vencido | **Reconectando…** | `--color-warn` | pulso lento / opaco (sob `motion-safe:`) |
| `offline` | `onerror` com `readyState === CLOSED (2)` | **Sem conexão** | `--color-crit` | estático |

Detalhe crítico — o browser **só** reconecta sozinho em erro *transitório*
(`readyState` volta a `CONNECTING`). Num fechamento *fatal* (servidor responde
não-2xx, ou o `?token=` expira e o backend devolve 401) o `readyState` vai para
`CLOSED (2)` e o browser **não** tenta de novo. Por isso o handler `onerror`
**ramifica em `es.readyState`**: `CONNECTING` → reconexão em andamento; `CLOSED` →
`offline` (terminal nesta fase). Sem essa ramificação, "Reconectando…" viraria uma
mentira permanente após um close fatal.

### Grace period (anti-piscar)

- Vale **só na entrada** em `reconnecting`. Em `onerror` transitório, se o estado
  atual é `live`, arma um timer `RECONNECT_GRACE_MS` (const no módulo, **3000ms**
  nesta fase). Se `onopen` disparar antes do timer vencer → cancela o timer, fica em
  `live` (o blip foi engolido). Se o timer vencer ainda sem reabrir → transita para
  `reconnecting`.
- **Não** há grace na saída: em `onopen`, snap imediato para `live` — recuperação é
  boa notícia, mostra na hora. O debounce guarda apenas `live → reconnecting`.
- `offline` (close fatal) **ignora o grace** — é definitivo e imediato, não um blip.

### Estado inicial

Otimista: começa em `live`. A abertura da conexão passa por `CONNECTING` antes do
primeiro `onopen`, mas mostrar `live` de cara evita um flash de "Reconectando…" no
boot. Se a conexão inicial falhar de fato, o fluxo normal (`onerror` → grace →
`reconnecting`/`offline`) corrige em 3s.

### Propagação até o badge

1. `real/liveApi.ts`: variável de módulo `connectionState` + `Set` de listeners.
   `ensureSharedSource()` fixa `es.onopen`/`es.onerror` que atualizam o estado
   (com a lógica de grace acima) e notificam os listeners.
2. Novo método no contrato `LiveApi`:
   `subscribeConnection(cb: (s: LiveConnectionState) => void): () => void`. Emite o
   estado atual na inscrição e a cada transição. Mock devolve `'live'` uma vez e
   nunca muda.
3. Novo hook `useLiveConnection(): LiveConnectionState` (análogo a `useLiveTail`/
   `useLiveStatuses`): inscreve no mount, limpa no unmount, retorna o estado atual.
4. `DashboardPage` chama `useLiveConnection()` e passa `liveState` como prop pro
   `Topbar`. `Topbar` só mapeia estado→(texto, cor, animação do ponto).

### Acessibilidade

- Badge com `role="status"` + `aria-live="polite"` para anunciar a mudança de estado
  a leitores de tela sem interromper.
- Toda animação de pulso sob `motion-safe:` (padrão já usado no badge atual).

## Estado/lógica

- `type LiveConnectionState = 'live' | 'reconnecting' | 'offline'` em `lib/types.ts`.
- Máquina de estados e timer de grace: nível de módulo em `real/liveApi.ts` — **um**
  timer global, não um por observador.
- `Topbar` permanece sem estado próprio para isto; recebe `liveState` por prop.
- Sem contexto/store novo.

## Fora de escopo (fase 1)

- **Detecção por silêncio de dados / heartbeat.** `pg_notify` só emite em mudança;
  gaps longos sem `LivePoint` são **normais**. Marcar "reconectando" por timeout de
  ausência de dado daria falso-positivo constante. Ficaria correto só com keepalive
  (comentários SSE) do backend — trabalho de backend, fase futura.
- **Recuperação de close fatal (renovar token e reabrir o `EventSource`).** Nesta
  fase `offline` é terminal e só sinaliza; refazer o stream com token novo vem depois.
- **Reconexão manual (botão "tentar de novo") no estado `offline`.**
- **Grace configurável via Odoo** — fixo em 3000ms no código nesta fase.
- **Toast/notificação** na queda — apenas o badge muda; sem toast.

## Testes a cobrir

Presentacional (`Topbar`, via prop — sem `EventSource`):
- `liveState='live'` → "AO VIVO", cor `--color-good`, ponto pulsante.
- `liveState='reconnecting'` → "Reconectando…", cor `--color-warn`.
- `liveState='offline'` → "Sem conexão", cor `--color-crit`.
- Badge expõe `role="status"`/`aria-live`.

Máquina de estados (`real/liveApi.ts`, com o `MockEventSource` já existente em
`liveApi.test.ts` + fake timers):
- `onerror` transitório (`readyState=CONNECTING`) **antes** de 3s: sem transição,
  segue `live`.
- `onerror` transitório que persiste **além** de 3s: transita para `reconnecting`.
- `onopen` **durante** o grace: cancela o timer, permanece `live` (não pisca).
- `onopen` a partir de `reconnecting`: snap imediato para `live`, sem esperar grace.
- `onerror` com `readyState=CLOSED (2)`: vai direto para `offline`, ignorando o grace.
- `subscribeConnection` emite o estado atual na inscrição e recebe cada transição;
  unsubscribe para de receber.
- Mock: `subscribeConnection` emite `'live'` e nunca mais muda.
