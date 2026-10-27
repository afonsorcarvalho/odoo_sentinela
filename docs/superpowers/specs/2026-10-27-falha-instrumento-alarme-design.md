# Falha de instrumento vira alarme — e o dashboard para de mentir

Data: 2026-10-27 · Origem: P0 do `/impeccable critique` em produção (`.impeccable/critique/2026-10-27T18-00-11Z__frontend-src.md`).

## Por quê

Em produção (OXIMED, `SNR-OXIMED-ETO-01`, 4–20 mA → 0–100 ppm) o laço está aberto: 0 mA → **-25 ppm**.
O dashboard mostrou isso como **"OK" verde** no drawer, e o painel dizia **"Nenhum alarme ativo"**.
Falsa tranquilidade no pior cenário de conformidade: a CME fica cega sem saber.
Princípio 1 do PRODUCT.md — "estado de alarme nunca é ambíguo" — violado.

Decisão do Afonso: **instrumento quebrado tem que alarmar, e na hora** (primeira leitura que perceber).

## Objetivos

1. **Laço 4–20 mA fora do envelope NAMUR NE43** (corrente < 3,6 mA ou > 21,0 mA) → leitura com
   `status_leitura = "falha_sensor"` e **alarme imediato** (1ª leitura, sem histerese de entrada).
2. **Módulo de aquisição sem resposta** (o `sensor_offline` que o leitor já produz: N4B sem
   resposta, porta serial ausente, driver em cooldown) → alarme após **3 leituras `sensor_offline`
   seguidas (~18 s)** — um timeout isolado de RS-485 não alarma (Afonso, 2026-10-27).
3. **Dashboard**:
   - sensor em falha: estado crítico, rótulo textual claro ("Sensor desconectado" / "Sem
     comunicação com o módulo"), **não exibe o número** como leitura (o -25 não significa nada);
   - sensor sem limite cadastrado: estado neutro **"Não avaliado"**, nunca verde, nunca "OK";
   - o estado de qualquer leitura vem de `status_leitura` primeiro, limite depois.
4. **Botão "Editar" do dashboard só para admin** (`is_admin` do JWT, que já existe).

## Não-objetivos

- Hub inteiro fora do ar / sem rede (detecção por heartbeat no servidor) — outra frente.
- Redesenho visual do card para leitura à distância (P1 do critique) — fica para depois; aqui só
  o estado correto e o rótulo.
- Outros P1/P2 do critique (mobile, contraste, bundle).
- Notificação fora do dashboard (e-mail/WhatsApp).

## Anti-objetivos (falharia mesmo "funcionando")

- Qualquer caminho em que uma leitura `falha_sensor`/`sensor_offline` apareça verde ou "OK".
- Falha de instrumento misturada com "fora de faixa": são problemas diferentes (equipamento vs
  processo), precisam de tipo de violação próprio.
- Alarme que dispara e some a cada leitura num cabo com mau contato (enxurrada de toasts).

## O que existe (a construir em cima)

- `hub/leitor.py`: produz `status_leitura` ∈ `ok | suspeito | erro_leitura | sensor_offline`;
  já tem gate `faixa_min/faixa_max` → `suspeito` (não configurado no OXIMED, por isso -25 passou ok).
- `hub/detector_alarme.py`: alarme na borda com histerese N=3, **só avalia leitura `ok`** — por
  isso falha de instrumento nunca vira alarme hoje. Emite `entrada_alarme`/`saida_alarme` com
  `tipo_violacao`; segue para `alarmes.txt` assinado + MQTT + bridge → Timescale/Odoo + SSE/toast.
- Odoo `alarm_event.tipo_violacao` já tem `sensor_offline` e `erro_leitura` (nunca emitidos).
  Frontend `AlarmTipoViolacao` idem.
- JWT já carrega `is_admin` (grupo `base.group_system`); `useAuth` expõe `isAdmin`.
- `status_leitura` é texto livre no contrato/ingestão/Timescale (nenhum enum a migrar).
- O frontend hoje **não consome `status_leitura`** — o estado vem só de `computeStatus(valor, limite)`.

## Decisões tomadas

- **Onde fica o gate:** no hub, na borda (é onde a corrente bruta é conhecida e o alarme já nasce
  assinado). Não no servidor.
- **Limiar:** NAMUR NE43 — < 3,6 mA ou > 21,0 mA = falha. Vale automaticamente para todo canal cujo
  `map.in` seja (4, 20); dispensa configurar faixa por sensor.
- **Entrada do alarme de falha:** imediata, 1ª leitura (Afonso).
- **Módulo sem resposta também alarma, após 3 leituras offline seguidas** (Afonso: imediato daria
  alarme falso a cada glitch de barramento).
- **Novo tipo de violação `falha_sensor`** (laço fora do NE43). Comunicação perdida com o módulo
  reusa o já existente **`sensor_offline`**.
- **Editar:** visível só com `isAdmin`.

## Decisões minhas (o Afonso pode vetar)

- **Saída do alarme de falha** exige **3 leituras boas seguidas** (mesmo N da histerese atual) —
  evita flapping de cabo com mau contato; entrada imediata, saída confirmada.
- **Corrente bruta** = inversão do `map` do canal (`map_out` → `map_in`) aplicada sobre o valor
  **antes** da calibração (ganho/offset). Se o backend já expõe o bruto, usar o bruto.
- **Precedência de status na leitura:** `sensor_offline` > `falha_sensor` > `erro_leitura` >
  `suspeito` > `ok`.
- Durante falha ativa, o detector de **faixa** não avalia aquele sensor (já é assim: só lê `ok`);
  ao recuperar, o alarme de faixa, se houver, volta a valer normalmente.
- Leitura em falha continua sendo gravada (arquivo diário + Timescale) com seu `status_leitura` —
  é registro de auditoria; só a **exibição** esconde o número.
- **Falha alarma independente de limite**: o detector passa a acompanhar TODOS os canais
  (hoje `montar_limites` só inclui quem tem limite e o detector descarta `limite is None`). Via de
  falha separada da via de faixa.
- **Um estado de alarme por sensor; falha prevalece sobre faixa**: se há alarme de faixa aberto e
  entra falha, emite `saida_alarme` da faixa e `entrada_alarme` da falha (o valor medido deixou de
  ser confiável). Após recuperar (3 boas), a faixa é reavaliada do zero com a histerese N=3 normal.
  Compatível com a dedup por sensor que o Odoo já faz (`processar_entrada/saida_alarme`).
- **Troca `falha_sensor` ↔ `sensor_offline` com alarme aberto não gera novo alarme**: continua o
  mesmo alarme de falha de instrumento (um toast só); o `tipo_violacao` registrado é o da entrada.
- **`erro_leitura` e `suspeito` não alarmam**: viram estado visual não verde ("Leitura inválida"),
  sem número como leitura.
- **NE43 só para canal com `map.in` = (4, 20)**; outros mapeamentos (ex. 0–20) ficam sem gate.
  Fora do NE43 prevalece sobre `faixa_min/max` (precedência acima).
- Rótulos: `falha_sensor` → "Sensor desconectado"; `sensor_offline` → "Sem comunicação";
  sem limite → "Não avaliado"; tooltip/linha de ajuda "Sem limite configurado — defina no Odoo".

## Deixado para quem implementa

- Forma exata de levar `status_leitura` até o frontend (payload do SSE `/live`, histórico
  `/historico`, último valor do card) e onde fica a precedência status→limite no `lib/status.ts`.
- Investigar por que o drawer mostrou "OK" com -25 (prop `state` externa vs `computeStatus`) e
  garantir que o caminho morre.
- Ícone/forma do estado de falha dentro do sistema de formas existente (`statusVisuals.tsx`:
  círculo/triângulo/quadrado/tracejado) — falha deve ser distinguível sem cor.
- Contrato do arquivo de alarmes: `tipo_violacao` é texto; confirmar que `falha_sensor` passa na
  validação de assinatura/parse sem mudança de formato.
- Odoo: adicionar `('falha_sensor', 'Falha do sensor')` à selection (precisa upgrade + restart do
  Odoo — ver memória `odoo-addon-dev-gotchas`). Frontend: estender `AlarmTipoViolacao`.
- Deploy: hub no Pi OXIMED (rsync `hub contrato`), addon no Odoo da VPS (upgrade), frontend
  (build + rsync `~/www`), API/bridge se mudarem (código montado; restart do container).
- Testes: TDD em cada camada (hub leitor/detector, ingestão do alarme, frontend status/rótulo,
  Editar oculto sem admin).

## Critério de pronto (verificável em produção)

Com o sensor do OXIMED ainda sem ligar (0 mA):
1. hub emite `entrada_alarme` `falha_sensor` na primeira leitura após o deploy;
2. toast aparece no dashboard e o painel lista o alarme aberto;
3. card e drawer mostram "Sensor desconectado" em estado crítico, sem "-25.0" como leitura;
4. desligando o cabo RS-485 do N4B → `sensor_offline` alarma em ~18 s (3 leituras); religando → sai após 3 leituras boas;
5. usuário não-admin não vê "Editar".
