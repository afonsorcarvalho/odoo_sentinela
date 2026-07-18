# Design — Serviço de Ingestão (Fase 2, fatia fina: validação + TimescaleDB)

> Complementa `esp32_coletor_spec.md` (formato de arquivo) e `coletor_simulado/` (gerador de arquivo assinado, Fase 2 anterior). Cobre só a parte de validação + gravação no TimescaleDB — integração com Odoo (`file.ledger`, `alarm.event`) fica para uma rodada seguinte.

## Escopo desta rodada

Um serviço Python standalone que lê um arquivo de leituras gerado por `coletor_simulado/`, valida a cadeia de hash e a assinatura ECDSA, e grava as leituras válidas no TimescaleDB (`sensor_reading`, schema já existente da Fase 1).

**Fora de escopo**: integração com Odoo (`file.ledger`, `alarm.event` — API XML-RPC decidida como abordagem, mas implementação fica para a próxima rodada), processamento do arquivo de alarmes, SFTP/transporte real (o arquivo já está em disco local), MQTT, proteção contra reingestão duplicada de um mesmo arquivo (isso é o papel do `file.ledger`, que ainda não existe neste fluxo).

## Decisões desta rodada

| Ponto em aberto (roadmap) | Decisão |
|---|---|
| API Odoo↔ingestão | XML-RPC nativo do Odoo (sem código Odoo novo) — **decidido, mas não implementado ainda**: esta rodada não toca Odoo. |
| Origem da chave pública do coletor (sem Odoo) | Registro local (`ingestao/coletores_conhecidos.json`, JSON, gitignored) mapeando `coletor_id → chave pública PEM`, com um helper de provisionamento único que lê a chave privada persistida do coletor simulado (não faz parte do caminho de validação em runtime). |
| `site_id` da leitura (sem Odoo pra resolver `coletor→hub→site`) | Fixo (`SITE-SIM-0001`) nesta rodada — só existe um site no cenário simulado. |

## 1. Estrutura de arquivos

```
ingestao/
├── __init__.py
├── registro_coletores.py   # registro local coletor_id -> chave pública
├── validador.py             # parsing + cadeia de hash + verificação de assinatura
├── timescale.py              # conexão + gravação em lote na sensor_reading
├── ingestor.py                # orquestração (validar -> gravar) + CLI
├── requirements.txt
├── coletores_conhecidos.json  # gitignored — registro local, gerado pelo provisionamento
└── tests/
    ├── __init__.py
    ├── test_registro_coletores.py
    ├── test_validador.py
    ├── test_timescale.py
    └── test_ingestor.py
```

`ingestao/coletores_conhecidos.json` entra no `.gitignore` (é um registro de ambiente local, análogo à chave privada do coletor simulado).

## 2. Registro de coletores conhecidos (`registro_coletores.py`)

- `carregar_registro(caminho) -> dict[str, str]`: lê o JSON (`{coletor_id: chave_publica_pem}`), retorna dicionário vazio se o arquivo não existir ainda.
- `salvar_registro(caminho, registro) -> None`: grava o dicionário de volta como JSON.
- `registrar_coletor(caminho, coletor_id, chave_publica_pem) -> None`: adiciona/atualiza uma entrada e salva.
- `obter_chave_publica(caminho, coletor_id) -> EllipticCurvePublicKey`: lê o PEM da entrada e desserializa via `cryptography`; levanta `KeyError` se o `coletor_id` não estiver registrado.
- `registrar_a_partir_de_chave_privada(caminho_registro, caminho_chave_privada, coletor_id) -> None`: carrega a chave privada do coletor simulado (via `serialization.load_pem_private_key`, sem importar `coletor_simulado`), extrai a chave pública, serializa como PEM e registra. **Único ponto de acoplamento com o layout do simulador — usado uma vez, manualmente, como provisionamento, não faz parte do fluxo de validação.**
- CLI (`argparse`, `if __name__ == '__main__':`): `--registrar <coletor_id> --a-partir-de <caminho_chave_privada>`.

## 3. Validação (`validador.py`)

Reimplementa **de forma independente** (sem importar `coletor_simulado.formato`) a mesma lógica de cadeia de hash do `esp32_coletor_spec.md` §4 — a ingestão real nunca poderia importar o módulo do firmware (que roda em C no ESP32); mantém-se a mesma fronteira arquitetural mesmo o simulador sendo Python por conveniência.

- `parse_cabecalho(linhas) -> dict`: extrai os campos `# chave: valor` do cabeçalho (schema_version, tipo_arquivo, coletor_id, hub_id, coletor_pubkey_fingerprint, data_referencia, timezone_offset, firmware_version), retorna também o texto canônico do cabeçalho (para recalcular o `hash_seed`).
- `parse_linha_leitura(linha) -> dict`: separa por `|`, retorna os 9 campos + hash da linha, e a string "sem hash" usada para recalcular o encadeamento.
- `parse_rodape(linhas) -> dict`: extrai `total_linhas`, `hash_final`, `assinatura`.
- `validar_arquivo(caminho, registro_path) -> ResultadoValidacao`: lê o arquivo inteiro, recalcula a cadeia de hash linha a linha (mesmo algoritmo do `formato.py` do simulador, reimplementado aqui), compara com o `hash_final` do rodapé, verifica a assinatura (via `obter_chave_publica` do registro) sobre esse hash. Retorna um objeto/dict com os mesmos nomes de campo de `sensor_monitor.file.ledger` (seção 4.10 da spec de dados): `status_validacao` (`'valido'`/`'invalido'`), `motivo_rejeicao` (`None` quando válido), `total_linhas`, `coletor_id`, mais a lista de leituras parseadas (só quando válido).

## 4. Gravação no TimescaleDB (`timescale.py`)

- `conectar(dsn) -> connection`: `psycopg2.connect(dsn)` (ou `psycopg` v3 — decisão de implementação, qualquer uma serve).
- `inserir_leituras(conn, site_id, coletor_id, leituras) -> int`: `executemany`/`execute_values` inserindo cada leitura parseada na tabela `sensor_reading` (colunas: `time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura`), retorna quantidade de linhas gravadas. `time` vem do `timestamp` de cada leitura; `coletor_id` é um campo do arquivo (cabeçalho), não de cada linha do corpo, por isso entra como parâmetro à parte — os demais campos por leitura vêm direto do parsing de `validador.py`.

## 5. Orquestração + CLI (`ingestor.py`)

- `ingerir_arquivo(caminho, registro_path, dsn, site_id) -> ResultadoIngestao`: chama `validar_arquivo`; se `status_validacao == 'valido'`, chama `inserir_leituras`; retorna resultado combinado (status, motivo, total_linhas, total_gravado).
- CLI: `python -m ingestao.ingestor --arquivo <path> --registro ingestao/coletores_conhecidos.json --site-id SITE-SIM-0001 --dsn postgresql://sentinela:sentinela@localhost:5433/sentinela`.

## 6. Testes

- `test_registro_coletores.py`: registrar/carregar/obter chave; `registrar_a_partir_de_chave_privada` extrai a pública corretamente de uma chave gerada em teste; `obter_chave_publica` levanta erro para coletor não registrado.
- `test_validador.py`: usa `coletor_simulado.gerador` **só como fixture de teste** (gera um arquivo real assinado) para validar o caminho feliz; corrompe uma linha do corpo (edita um valor) e confirma que a cadeia de hash não bate mais (`status_validacao='invalido'`); registra uma chave pública diferente da que assinou e confirma que a verificação de assinatura falha.
- `test_timescale.py`: conecta no TimescaleDB já rodando (container da Fase 1, `localhost:5433`), insere leituras de teste, confirma que foram gravadas com uma consulta, limpa as linhas de teste ao final (teste de integração real, não mock).
- `test_ingestor.py`: fluxo completo — gera arquivo com `coletor_simulado`, registra a chave, roda `ingerir_arquivo`, confirma leituras no Timescale; roda de novo com um arquivo corrompido e confirma que nada é gravado.

## Pontos que seguem em aberto (não bloqueiam esta rodada)

- Integração real com Odoo via XML-RPC (`file.ledger`, `alarm.event`) — próxima rodada.
- Processamento do arquivo de alarmes (`tipo_arquivo=alarmes`) — acompanha a integração Odoo, já que `alarm.event` vive no Odoo.
- Proteção contra reingestão duplicada de um arquivo já processado — depende do `file.ledger`.
- Resolução real de `site_id` a partir de `coletor_id` (hoje fixo) — depende da consulta ao Odoo.
