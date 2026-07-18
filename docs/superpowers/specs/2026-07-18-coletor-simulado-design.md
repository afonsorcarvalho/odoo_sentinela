# Design — Coletor Simulado (Fase 2, fatia fina)

> Complementa `esp32_coletor_spec.md` (formato de arquivo, seções 4/5) e `diretrizes_projeto.md`/`roadmap_implementacao.md` (Fase 2: "coletor simulado gera arquivos assinados válidos... desacopla software de hardware"). Este documento cobre só o gerador — SFTP, MQTT e o serviço de ingestão ficam para rodadas seguintes.

## Escopo desta rodada

Um script Python standalone que gera, localmente, um par de arquivos diários (`leituras` + `alarmes`) no formato exato especificado em `esp32_coletor_spec.md` §4/5 — assinados com uma chave ECDSA persistida, simulando o secure element do coletor real. Sem MQTT, sem SFTP, sem servidor de ingestão — os arquivos só precisam existir no disco local, prontos para serem consumidos por um serviço de ingestão numa rodada futura.

**Fora de escopo**: MQTT (telemetria em tempo real), transporte SFTP/SFTPGo, serviço de ingestão (parsing/validação/gravação no Timescale), integração com o módulo Odoo (o simulador não lê nem escreve no Odoo — os códigos usados são fixos/hardcoded, compatíveis com os dados de referência RDC15 já cadastrados na Fase 1, mas nenhuma chamada é feita ao Odoo).

## Cenário simulado

Um coletor, dois sensores, ambos na área Expurgo (categoria `EXPURGO`, já cadastrada na Fase 1 com limiares RDC15 18–22°C / pressão negativa mín. 2,5Pa):

| Identificador | Valor |
|---|---|
| `coletor_id` | `COL-SIM-0001` |
| `hub_id` | `HUB-SIM-0001` (informativo, ver esp32 spec §4 — não usado para lookup nesta rodada) |
| `area_id` | `EXPURGO` |
| Sensor 1 | `SNR-SIM-TEMP-01`, `tipo_medida=temperatura`, unidade `C` |
| Sensor 2 | `SNR-SIM-PRES-01`, `tipo_medida=pressao_diferencial`, unidade `Pa` |
| `protocolo_origem` | `4-20mA` para ambos (simplificação — não é RS-485 nesta rodada) |

## 1. Estrutura de arquivos no repo

```
coletor_simulado/
├── __init__.py
├── identidade.py       # geração/carregamento da chave ECDSA persistida
├── formato.py          # construção de linha, cabeçalho, rodapé, cadeia de hash
├── gerador.py           # orquestra a geração de um dia (leituras + alarmes) + CLI
├── identidade/          # gitignored — chave privada persistida aqui
│   └── coletor_privkey.pem
├── output/               # gitignored — arquivos gerados
└── tests/
    ├── __init__.py
    ├── test_identidade.py
    ├── test_formato.py
    └── test_gerador.py
```

`coletor_simulado/identidade/` e `coletor_simulado/output/` entram no `.gitignore` do repo (chave privada e artefatos gerados não são versionados).

## 2. Identidade e assinatura (`identidade.py`)

- Biblioteca `cryptography` (Python), curva `SECP256R1` (P-256) — mesma família do ATECC608A real.
- `carregar_ou_criar_chave(caminho) -> EllipticCurvePrivateKey`: se o arquivo PEM já existe, carrega; senão gera um novo par e persiste a chave privada (sem senha — ambiente de dev/simulação, não é o secure element real). Chamado uma vez por execução; a mesma chave é reaproveitada entre execuções (identidade estável do coletor simulado, como um dispositivo físico real teria).
- `fingerprint_publica(chave_privada) -> str`: retorna o fingerprint (SHA-256 da chave pública serializada em DER, hex, formatado em pares `XX:XX:...` como no exemplo do `esp32_coletor_spec.md` §4) — é o valor que seria cadastrado em `coletor.pubkey_fingerprint` no Odoo quando a integração acontecer (fora de escopo aqui, só exibido no console).
- `assinar(chave_privada, dado_bytes) -> bytes`: assinatura ECDSA (`cryptography.hazmat.primitives.asymmetric.ec`, hash SHA-256) sobre o `hash_final` do arquivo — uma operação por arquivo, não por linha (conforme esp32 spec §4, regra de assinatura).

## 3. Formato e cadeia de hash (`formato.py`)

Implementa exatamente `esp32_coletor_spec.md` §4 (arquivo de leituras) e §5 (arquivo de alarme):

- `montar_cabecalho(tipo_arquivo, coletor_id, hub_id, pubkey_fingerprint, data_referencia, timezone_offset, firmware_version) -> str`: monta o bloco de cabeçalho `# chave: valor` linha a linha, na ordem do spec.
- `hash_linha(hash_anterior, linha_sem_hash) -> str`: `SHA256(hash_anterior + linha_sem_hash)`, hex.
- `hash_seed(cabecalho_canonico) -> str`: `SHA256(cabecalho_canonico)` — primeiro elo da cadeia.
- `montar_linha_leitura(seq, timestamp, sensor_id, area_id, tipo_medida, valor, unidade, protocolo_origem, status_leitura, hash) -> str`: monta a linha `|`-delimitada do corpo de leituras.
- `montar_linha_alarme(seq, timestamp, sensor_id, area_id, tipo_medida, tipo_evento, tipo_violacao, valor, limite_min_vigente, limite_max_vigente, hash) -> str`: idem para o corpo de alarme (`limite_*_vigente` usa `—` quando não aplicável, conforme exemplo do spec).
- `montar_rodape(total, hash_final, assinatura, campo_total) -> str`: rodapé com `total_linhas`/`total_eventos` (conforme `tipo_arquivo`), `hash_final`, `assinatura` (base64).
- Validação de identificadores: reutiliza a mesma regra de `odoo_sentinela` (proibir `|`, `\n`, `\r`) — função `validar_identificador(valor)` levantando `ValueError` se violar, aplicada a todo identificador usado na montagem das linhas.

## 4. Gerador (`gerador.py`)

- `gerar_leituras_do_dia(data, sensores, intervalo_segundos=60) -> list[linha]`: para cada minuto do dia (00:00 a 23:59), para cada sensor, gera um valor plausível (temperatura: ruído gaussiano leve em torno de 20°C, dentro de 18–22°C; pressão: ruído leve em torno de −3,5Pa, dentro do limite negativo). Monta a linha, encadeia o hash, acumula.
- `gerar_alarmes_do_dia(leituras_geradas, sensor_pressao, injetar_alarme: bool) -> list[linha]`: por padrão, nenhuma leitura sai da faixa → arquivo de alarme com 0 eventos (ainda assim gerado e assinado, conforme regra do spec). Com `--injetar-alarme`, força os valores do sensor de pressão entre 02:00 e 02:07 para +1,0Pa (viola o limite negativo) — produz uma linha `entrada_alarme` (02:00) e uma `saida_alarme` (02:07), com `limite_min_vigente=—`/`limite_max_vigente=-2.5` (snapshot do limiar RDC15 do Expurgo).
- `gerar_dia(data, output_dir, injetar_alarme=False)`: orquestra — monta cabeçalhos, gera corpo de leituras e de alarme, calcula hash final de cada um, assina (chamando `identidade.py`), monta rodapés, escreve os dois arquivos em `output_dir` (nome de arquivo: `<coletor_id>_<tipo_arquivo>_<data>.txt`).
- CLI (`if __name__ == '__main__':` com `argparse`): `--data YYYY-MM-DD` (default: hoje), `--output-dir` (default `./output`), `--injetar-alarme` (flag, default False).

## 5. Testes (`tests/`)

- `test_identidade.py`: chave persiste entre chamadas (mesmo arquivo → mesma chave); fingerprint determinístico para a mesma chave; assinatura verificável com a chave pública correspondente (e falha com uma chave pública diferente).
- `test_formato.py`: cadeia de hash recalculada bate com a gerada; `validar_identificador` rejeita `|`, `\n`, `\r` e aceita identificadores normais; linha de leitura e de alarme montam nos formatos exatos do spec (comparação de string).
- `test_gerador.py`: arquivo de leituras tem 1440 linhas por sensor (2880 total) + cabeçalho + rodapé com `total_linhas` correto; arquivo de alarme sem `--injetar-alarme` tem `total_eventos: 0`; com a flag, tem exatamente 2 linhas (par entrada/saída) com os valores/timestamps esperados; hash final e assinatura do rodapé verificam corretamente contra o conteúdo gerado.

## Pontos que seguem em aberto (não bloqueiam esta rodada)

- Formato exato de payload MQTT (delegado à Fase 3, junto com o Mosquitto central).
- Transporte real via SFTPGo (delegado a quando o serviço de ingestão for construído).
- De onde o simulador saberia, numa integração real, os limiares vigentes de cada sensor (hoje hardcoded no gerador, refletindo o cadastro RDC15 já existente na Fase 1) — a sincronização de config real é o control plane da Fase 5.
