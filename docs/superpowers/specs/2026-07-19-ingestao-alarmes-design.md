# Design — Arquivo de alarmes + `alarm.event` no serviço de ingestão

> Complementa `docs/superpowers/specs/2026-07-18-ingestao-odoo-ledger-design.md` (resolução de site + `file.ledger`, rodada anterior) e `esp32_coletor_spec.md` §5 (formato do arquivo de alarme). Fecha a Fase 2 do roadmap.

## Escopo desta rodada

O serviço de ingestão passa a processar também o arquivo `tipo_arquivo=alarmes` (já gerado pelo `coletor_simulado`, nunca antes processado): valida a cadeia de hash/assinatura (mesmo mecanismo do arquivo de leituras, reaproveitado), e cria/atualiza `sensor_monitor.alarm.event` no Odoo a partir das transições `entrada_alarme`/`saida_alarme`. `file.ledger` passa a ser gravado também para `tipo_arquivo=alarmes`.

**Fora de escopo**: reconciliação retroativa de lacunas (ex: uma `saida_alarme` cuja `entrada_alarme` está num arquivo nunca ingerido) — tratada como caso órfão, logado e ignorado nesta rodada (ver seção 4).

## Bug corrigido nesta rodada

`ingestao/validador.py::parse_arquivo` separa cabeçalho/corpo/rodapé contando "linhas consecutivas começando com `#`". Isso quebra para um arquivo de alarme **sem eventos** (corpo vazio): não há linha de corpo separando cabeçalho de rodapé, então o loop do cabeçalho consome o rodapé inteiro por engano, e `hash_final`/`assinatura` nunca são encontrados — um arquivo de alarme genuinamente válido com `total_eventos: 0` seria rejeitado incorretamente. Esse bug já tinha sido identificado (não bloqueante) no review final da rodada anterior, já que nada processava arquivos de alarme ainda; agora que processa, precisa ser corrigido.

**Correção**: `parse_arquivo` passa a reconhecer as linhas de cabeçalho por **chave conhecida** (`schema_version`, `tipo_arquivo`, `coletor_id`, `hub_id`, `coletor_pubkey_fingerprint`, `data_referencia`, `timezone_offset`, `firmware_version`, `dia_anterior_hash_final`), não mais por "é uma linha com `#`". O loop do cabeçalho para assim que encontrar uma linha `#` cuja chave não está nesse conjunto (ou uma linha sem `#`) — funciona tanto para corpo vazio quanto não vazio.

## 1. Extensão do `validador.py`

- `parse_arquivo` corrigido conforme acima.
- `parse_linha_alarme(linha) -> dict`: nova função, análoga a `parse_linha_leitura`, para o formato de 11 campos do corpo do arquivo de alarme (`seq|timestamp|sensor_id|area_id|tipo_medida|tipo_evento|tipo_violacao|valor|limite_min_vigente|limite_max_vigente|hash`).
- `ResultadoValidacao` ganha 2 campos novos: `tipo_arquivo: str` (do cabeçalho) e `eventos: list` (paralelo a `leituras`, populado só quando `tipo_arquivo == 'alarmes'`).
- `validar_arquivo` passa a despachar por `metadados_cab['tipo_arquivo']`: usa `parse_linha_leitura`/`leituras`/campo `total_linhas` do rodapé para `leituras`; usa `parse_linha_alarme`/`eventos`/campo `total_eventos` do rodapé para `alarmes`. A cadeia de hash (`_hash_seed`/`_hash_linha`) é agnóstica ao tipo de linha (já opera sobre a string "linha sem hash" genérica) — não precisa duplicar.

## 2. Resolução de sensor (`odoo_cliente.py`)

- `resolver_sensor(cliente, sensor_code) -> dict` (`{'id', 'area_id'}`) — necessário porque `alarm.event` referencia `sensor_id`/`area_id` por id do Odoo, não pelo código usado no arquivo. Levanta `ValueError` se não encontrado (mesmo padrão de `resolver_coletor`).

## 3. Processamento de evento (`odoo_cliente.py`)

- `processar_entrada_alarme(cliente, evento, sensor_odoo_id, area_odoo_id, coletor_odoo_id, hash_arquivo) -> int`: cria um `sensor_monitor.alarm.event` (`status='aberto'`, `timestamp_deteccao` = timestamp do evento, `valor_lido`, `tipo_violacao`, `limite_configurado_snapshot` = `limite_max_vigente` se `tipo_violacao == 'acima_limite'` senão `limite_min_vigente`, `origem_arquivo_hash` = `hash_arquivo`). Retorna o id criado.
- `processar_saida_alarme(cliente, evento, sensor_odoo_id) -> int | None`: busca o `alarm.event` mais recente daquele sensor com `status != 'resolvido'`... na verdade filtra por `timestamp_resolucao_sensor = False` (ainda não resolvido pelo sensor) e `sensor_id = sensor_odoo_id`, ordenado por `timestamp_deteccao` desc, pega o primeiro. Se achar: `write()` só o `timestamp_resolucao_sensor`, retorna o id. Se não achar (órfã): não cria nada, retorna `None` (o chamador decide o que logar).

## 4. Orquestração (`ingestor.py`)

`ingerir_arquivo` passa a despachar por `resultado_validacao.tipo_arquivo`:
- `'leituras'`: fluxo já existente (Timescale via `site_code` resolvido).
- `'alarmes'`: para cada `evento` em `resultado_validacao.eventos`, resolve o sensor (`resolver_sensor`) e despacha para `processar_entrada_alarme` ou `processar_saida_alarme` conforme `evento['tipo_evento']`. Uma `saida_alarme` órfã (retorno `None`) é contabilizada mas não interrompe o processamento dos demais eventos do arquivo — só é registrada como uma contagem em `ResultadoIngestao` (`eventos_orfaos: int`, novo campo).
- Em ambos os casos: `escrever_ledger` é chamado com o `tipo_arquivo` correto e o total certo (`len(leituras)` ou `len(eventos)`).

`ResultadoIngestao` ganha o campo `eventos_orfaos` (default `0`, só relevante para `alarmes`).

CLI: nenhuma mudança de interface — o mesmo `--arquivo` aceita tanto um arquivo de leituras quanto de alarme, já que o tipo é detectado a partir do próprio conteúdo do arquivo.

## 5. Testes

- `test_validador.py`: regressão da suíte de leituras já existente (não pode quebrar); novos casos — arquivo de alarme com `total_eventos: 0` valida corretamente (prova o fix do bug); arquivo de alarme com um par entrada/saída valida e popula `eventos` com 2 itens.
- `test_odoo_cliente.py`: `resolver_sensor` contra os sensores já provisionados (`SNR-SIM-TEMP-01`/`SNR-SIM-PRES-01`); `processar_entrada_alarme` cria um registro com os campos certos; `processar_saida_alarme` encontra e atualiza o registro criado pela entrada (mesmo sensor); `processar_saida_alarme` retorna `None` quando não há entrada aberta correspondente (limpa qualquer registro criado durante o teste).
- `test_ingestor.py`: fluxo real ponta a ponta com `coletor_simulado --injetar-alarme` — confirma `alarm.event` criado com `timestamp_resolucao_sensor` preenchido após ingerir o arquivo de alarme, e `file.ledger` com `tipo_arquivo=alarmes`.

## Pontos que seguem em aberto (não bloqueiam esta rodada)

- Reconciliação de `saida_alarme` órfã quando a `entrada_alarme` correspondente estiver num arquivo ainda não ingerido (ex: lacuna detectada pelo cron da Fase 1) — fica para quando esse cron virar um processo real de reprocessamento.
- Fecha a Fase 2 do roadmap (`roadmap_implementacao.md`) — próximo é Fase 3 (APIs: auth/JWT, leitura sobre Timescale, tempo real via SSE).
