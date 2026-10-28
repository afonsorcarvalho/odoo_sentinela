# Relatório de período (histórico + PDF) — design

Data: 2026-10-28 · Status: aprovado em conversa, aguardando revisão do documento

## Intenção

O cliente (hospital/CME) precisa **consultar o histórico de qualquer data passada** e
**gerar um relatório em PDF** para guardar e apresentar a uma **fiscalização sanitária**.
Hoje o frontend só mostra janelas relativas a "agora" (1h/24h/7d/30d) e não há relatório.

Como o leitor final é um fiscal, o relatório é tratado como **documento de prova**:
números corretos no fuso local, falhas e lacunas visíveis (nunca escondidas na média),
limites e violações explícitos.

## Objetivos

1. Nova tela **Relatórios** no frontend (rota `/relatorios`, atrás do `AuthGuard`, link na navegação).
2. Filtros: **período** (data início e fim, qualquer data passada — ver decisões pós-revisão) e
   **seleção múltipla de sensores** (dos sites que o usuário pode ver).
3. **Granularidade automática** pelo tamanho do período:
   - período ≤ 1 dia (24h) → linhas **por hora**
   - período ≤ 62 dias → linhas **por dia**
   - período maior → linhas **por mês**
4. Para cada sensor selecionado, um bloco com:
   - **gráfico**: linha da média + faixa sombreada mín–máx + linhas horizontais dos limites
     mín/máx cadastrados (quando houver);
   - **tabela**: período (hora/dia/mês) | média | mínimo | máximo | nº de leituras;
     linhas cujo máx > limite máx ou mín < limite mín **destacadas** como fora do limite;
     buckets sem nenhuma leitura válida aparecem como linha **"sem dados"** (não omitidos);
   - **lista de alarmes** do período (início, fim, tipo, valor, status), via `/alarmes?sensor_code&desde&ate`.
5. Botões **Baixar PDF** e **Imprimir**, na mesma tela, com o mesmo período e sensores.
6. **PDF A4** com cabeçalho: cliente, site(s), sensores com unidade, período, granularidade,
   fuso horário, data/hora de emissão e usuário emissor; rodapé com paginação. Mesmo conteúdo
   da tela (gráfico, tabela, alarmes) por sensor.

## Não-objetivos (v1)

- Verificação criptográfica do relatório (hash/QR conferível no portal de autenticidade).
  Evolução natural depois; não bloquear o design para ela, mas não implementar.
- Agendamento/envio automático de relatório por e-mail.
- Exportar Excel/CSV.
- "Voltar no tempo" do dashboard (widgets mostrando data passada). O histórico é visto nesta tela.

## Anti-objetivos (falha mesmo que "funcione")

- Dia/hora calculados em **UTC** em vez de America/Sao_Paulo.
- Leituras de falha de instrumento (`status_leitura` ≠ ok, ex. `falha_sensor` 0 mA) entrando na média/mín/máx.
- Período com dados faltando aparecendo vazio ou omitido silenciosamente.
- Usuário vendo sensores de outro cliente/site (isolamento multi-tenant já existente deve valer aqui).
- PDF diferente do que está na tela.

## Restrições e achados do código

- API: FastAPI em `api/`. Endpoint existente `api/historico.py` (`/sensores/{code}/historico`)
  aceita só `window` relativo; reutilizar padrões de auth (`get_cliente_usuario`, `verificar_token`),
  `obter_sensor`, `obter_sites_permitidos`. Limites via `obter_threshold` (`api/meta.py`).
  Alarmes via `listar_alarmes` (`api/alarmes.py`), já aceita `desde`/`ate`.
- Timescale (`timescale/init.sql`): existem continuous aggregates `sensor_reading_hourly` e
  `sensor_reading_daily`, **mas não servem ao relatório**:
  - bucket diário em UTC (dia errado no Brasil);
  - agregam todas as leituras, inclusive com falha;
  - política de refresh olha só 3h / 3 dias para trás → dados que chegam atrasados
    (hub offline reenviando) nunca são materializados.
  **Decisão:** o relatório consulta a hypertable bruta `sensor_reading` com
  `time_bucket(<1 hour|1 day|1 month>, time, 'America/Sao_Paulo')`, filtrando leituras válidas,
  agrupando por bucket. Não alterar os agregados existentes (usados pelo dashboard).
  O builder deve medir o tempo de consulta para o pior caso (vários sensores × 1 ano) e, se for
  inaceitável (> ~5 s), propor alternativa antes de seguir.
- Buckets vazios: gerar a série completa de buckets do período (ex. `generate_series` no fuso local)
  e fazer left join, para "sem dados" aparecer.
- Período: início/fim interpretados em America/Sao_Paulo; limitar a no máximo 366 dias e
  no máximo, digamos, 20 sensores por relatório (minha escolha; retornar 422 acima disso).
- **Produção é persistente** (stack local e VPS): nada desta feature pode apagar/reescrever dados coletados.
- Frontend: SPA Vite/React em `frontend/`, gráficos em ECharts (atenção: `appendData` não funciona
  com série `line`); seguir design system AFR existente.

## Decisões de "como" (tomadas)

- **Endpoint novo** (nome a critério do builder, ex. `GET /relatorio?sensores=A,B&inicio=&fim=`)
  que devolve JSON com granularidade escolhida, buckets por sensor, limites e alarmes —
  usado pela tela.
- **PDF gerado no servidor (API)** a partir dos mesmos dados (ex. `GET /relatorio.pdf` com os
  mesmos parâmetros), para sair idêntico em qualquer navegador e com nome de arquivo
  descritivo (ex. `relatorio_<site>_<inicio>_<fim>.pdf`). "Imprimir" abre esse PDF para o
  usuário imprimir. (Minha escolha.)
- A regra de granularidade fica em um só lugar no servidor; a tela exibe a que veio.

## Decisões tomadas após revisão (minhas escolhas)

- **Período em dias inteiros:** filtro é data início + data fim (inclusivas), sem hora.
  Mesmo dia → por hora (24 linhas, 23/25 em dia de mudança de horário se houver);
  até 62 dias → por dia; acima → por mês (primeiro/último mês podem ser parciais, rotular o intervalo real).
  Intervalo efetivo = [início 00:00 local, (fim+1) 00:00 local).
- **Leitura válida = `status_leitura = 'ok'`** (lista branca; status novos ficam fora por padrão).
  Tabela ganha coluna **"leituras com falha"** por bucket; bucket só com falhas aparece como
  **"falha de instrumento"**, distinto de "sem dados" (zero leituras).
- **Alarmes:** consulta própria do relatório, **sem limite de 200**, por **sobreposição**
  (alarme que começou antes e seguia aberto, ou terminou dentro, entra). Não alterar `listar_alarmes`.
- **Escopo:** um relatório = um cliente; sensores podem ser de sites diferentes do cliente
  (validar cada sensor com `obter_sites_permitidos`). Nome do arquivo usa o cliente:
  `relatorio_<cliente>_<inicio>_<fim>.pdf`. Cabeçalho lista site de cada sensor.
- **Emissor:** nome do usuário Odoo logado (+ login entre parênteses); builder confirma que está
  disponível via sessão, senão buscar no Odoo.
- **Imprimir/Baixar:** frontend baixa o PDF via fetch autenticado (Bearer) como blob;
  Baixar salva, Imprimir abre o object URL em nova aba. Sem token na query string.

## Limites alterados no período (decisão do usuário)

- Gráfico e destaques "fora do limite" usam o **limite atual** do sensor.
- Se o limite mín/máx foi **alterado dentro do período** (ou depois do início dele), o bloco do
  sensor — na tela e no PDF — mostra um **aviso**: "Limite alterado em DD/MM/AAAA HH:MM
  (de X para Y)", uma linha por alteração. Sem alteração, nenhum aviso.
- Fonte: histórico de tracking do Odoo (`limite_min`/`limite_max` têm `tracking=True` em
  `alarm_threshold`, via `mail.tracking.value`). Builder confirma o caminho de leitura.

## Deixado para o builder

- Biblioteca de PDF e de gráfico no PDF (ex. WeasyPrint + SVG/matplotlib, ou reportlab).
  Considerar o peso da imagem Docker da API e o ambiente da VPS.
- Layout exato da tela e do PDF, dentro do design system.
- Formato preciso do JSON e dos parâmetros.
- Como o mês é rotulado (ex. "out/2026") e formato numérico (vírgula decimal pt-BR).

## Critério de sucesso

- Escolher 1 dia passado + 2 sensores → tela mostra 24 linhas por hora por sensor, com gráfico,
  destaques e alarmes; PDF baixado tem o mesmo conteúdo.
- Período de 10 dias → 10 linhas por dia; 6 meses → linhas por mês.
- Dia com hub offline aparece com "sem dados" nas horas sem leitura.
- Leitura `falha_sensor` não altera média/mín/máx.
- Valores conferem com consulta manual na hypertable no fuso de Brasília.
- Testes cobrindo: granularidade, fuso (borda de meia-noite local), exclusão de falhas,
  buckets vazios, isolamento por cliente.
