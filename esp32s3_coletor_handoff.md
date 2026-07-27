# Handoff — Coletor ESP32-S3 (PlatformIO, Windows)

> **Para quem é este documento**: sessão do Claude rodando no **Windows** (fora do WSL2), com PlatformIO/ESP-IDF, que vai construir o firmware do coletor ESP32-S3-Touch-LCD-4.3B.
>
> **O que ele faz**: aponta onde está a verdade de cada parte da arquitetura Sentinela. **Não transcreve contratos** — transcrição envelhece, ponteiro não.

---

## 0. Como chegar no repositório

- Repositório (fonte da verdade): `https://github.com/afonsorcarvalho/odoo_sentinela`
- No WSL2: `/home/afonso/docker/odoo_sentinela`
- Do Windows: `\\wsl.localhost\Ubuntu\home\afonso\docker\odoo_sentinela\`

Leia os arquivos direto por esse caminho UNC. Não copie/duplique os arquivos de contrato para o projeto PlatformIO — releia sempre.

---

## 1. AVISO CRÍTICO — documentos desatualizados

`esp32_coletor_spec.md` (raiz) descreve um coletor **ESP32-WROOM-32SE WiFi/Ethernet** especificado em 16/07/2026. **Está desatualizado em relação ao código quanto ao formato de arquivo e ao canal de config.** Use-o só como registro histórico de decisões de produto. Divergências reais medidas:

| `esp32_coletor_spec.md` diz | Código em produção faz |
|---|---|
| `schema_version: 1` | `schema_version: 3` |
| linha `…\|status_leitura\|hash` | `…\|status_leitura\|cert_ver\|cal_ganho\|cal_offset\|hash\|sig` |
| sem assinatura de cabeçalho | linha `# hdr_sig: <b64>` logo após o cabeçalho |
| 1 assinatura ECDSA por dia | **assinatura ECDSA por linha** + assinatura do rodapé |
| sem campos de tenant | `# cliente_id:` e `# site_id:` no cabeçalho, validados na ingestão |
| config via payload MQTT retido | MQTT `config/notify` (só o número da versão) → **download SFTP do YAML** → aplica → `config/applied` + `status` retido |
| RS-485 **não** usa firmware ESP32 (é o Pi) | (ainda é verdade hoje — ver §6) |

Consequência prática mais pesada: **assinar por linha** significa 1 operação ECDSA por leitura, não 1 por dia — muda orçamento de CPU e o regime de acesso à chave privada.

---

## 2. Fonte da verdade — leia estes arquivos, nesta ordem

| O quê | Arquivo | Por quê |
|---|---|---|
| **Formato do arquivo (congelado)** | `contrato/formato.py` | Cabeçalho canônico, colunas, cadeia de hash, rodapé. ~95 linhas. É o contrato byte a byte. |
| **Critério de aceitação** | `ingestao/validador.py` | O que o servidor aceita/rejeita. Se o firmware gerar algo que isso rejeita, o firmware está errado. |
| **Identidade / ECDSA** | `contrato/identidade.py` | Curva, hash, formato de assinatura, cálculo do fingerprint. |
| **Referência de implementação completa** | `hub/` (Python, roda no Pi) | O Hub **já é um coletor RS-485 funcionando** (leitura Modbus → arquivo assinado → MQTT → SFTP). O firmware é a reimplementação disso em C/C++. Leia como spec executável. |
| **Testes do formato** | `contrato/tests/`, `hub/tests/test_arquivo_diario.py`, `ingestao/tests/` | Vetores de teste. Use-os para gerar fixtures e validar o firmware. |

### Mapa de `hub/` (o que reimplementar)

| Módulo Python | Papel | Equivalente no firmware |
|---|---|---|
| `hub/leitor.py` | varredura Modbus RTU, escala mA→engenharia, filtro EWMA, gate de plausibilidade, self-healing de porta serial | leitor RS-485 |
| `hub/modbus_backend.py` + `hub/vendor/` | drivers por modelo de transdutor (`n4aib16`, `rs_ws_n01_2d`, `generico`) | drivers |
| `hub/arquivo_diario.py` | escreve `.txt` de leituras, cadeia de hash, retoma após reboot, sela no rollover | gravador SD |
| `hub/arquivo_alarmes.py` | mesmo, para arquivo de alarmes (evento) | gravador SD |
| `hub/detector_alarme.py` | histerese N=3, estado por sensor persistido, só avalia leitura `ok` | avaliador de alarme |
| `hub/assinador.py` | `Protocol` de assinatura (impl software hoje; ATECC608 é ponto de extensão previsto) | assinador |
| `hub/publicador_mqtt.py` | publica leitura e alarme em tempo real | cliente MQTT |
| `hub/enviador_sftp.py` | envia selados, árvore remota, estado `_enviados.json` | cliente de upload (**se** o firmware for hub — ver §6) |
| `hub/agente_config.py` | control-plane: notify → baixa YAML → aplica → reporta versão + heartbeat retido | agente de config |
| `hub/config.py` + `hub/config.example.yaml` | modelo de config operacional | config local |
| `hub/main.py` | loop principal, reload em runtime, selagem no shutdown | `app_main` |

**Comece por `hub/config.example.yaml`** — mostra em 40 linhas o modelo mental inteiro (barramento → dispositivo → canais → sensor_id/área/escala/filtro).

---

## 3. Fluxos que o firmware precisa honrar

### 3.1 Dado (dispositivo → servidor)

```
sensor RS-485 (Modbus RTU)
   → leitura (escala + calibração vigente)
   → linha no .txt local, com hash encadeado + assinatura ECDSA da linha  [durável, é a prova]
   → MQTT sentinela/telemetria/{hub_id}/{coletor_id}/{sensor_id}          [efêmero, tempo real]
   → avalia alarme (histerese) → linha no .txt de alarmes + MQTT sentinela/alarme/...
   → rollover de meia-noite: sela (rodapé com hash_final + assinatura)
   → upload do arquivo selado (SFTP) → ingestão valida → TimescaleDB + Odoo
```

Detalhes exatos: `hub/main.py` (loop), `contrato/formato.py` (bytes), `ingestao/validador.py` (aceitação).

### 3.2 Config (servidor → dispositivo)

Não é payload retido com a config inteira. É: **MQTT anuncia a versão, SFTP entrega o conteúdo.**

- Assina `sentinela/config/notify/hub/{code}` (QoS 1). Payload: `{"version": N}`.
- Se `N > versão_aplicada`: publica `sentinela/config/ack/hub/{code}`, baixa `/config/{code}/config-v{N}.yaml` por SFTP, valida, aplica atomicamente, persiste a versão.
- Reporta `sentinela/config/applied/hub/{code}` (`ok` ou `erro` + detalhe).
- Publica `sentinela/status/hub/{code}` **retido** (heartbeat + `config_version_aplicada`), com LWT `{"estado":"offline"}` retido no mesmo tópico.

Implementação de referência: `hub/agente_config.py` (`processar_notify`). Produtor do YAML: `api/config_publisher.py`.

### 3.3 Árvore remota de upload

`{cliente_id}/AAAA/MM/DD/{site_id}/{hub_id}/{coletor_id}/{nome_arquivo}` — ver `hub/enviador_sftp.py::_caminho_remoto`. `cliente_id`/`site_id` do cabeçalho **precisam casar** com o cadastro no Odoo, senão a ingestão rejeita ("tenant do header diverge").

### 3.4 Identidade e enrollment

- Chave EC P-256; assinatura ECDSA/SHA-256 sobre o **hash hexadecimal em ASCII** (não sobre bytes crus) — confira em `contrato/identidade.py` e `ingestao/validador.py::_verificar_sig`.
- `coletor_pubkey_fingerprint` = SHA-256 do DER SubjectPublicKeyInfo, hex maiúsculo, separado por `:`.
- Registro da chave pública: modelo `sensor_monitor.coletor` no Odoo (`addons/afr_sentinela_sensor_monitor/models/coletor.py`, campos `pubkey_pem` → `pubkey_fingerprint` computado). Caminho de teste sem Odoo: `ingestao/registro_coletores.py` (JSON local).
- O firmware precisa expor um modo "imprimir chave pública PEM" para o provisionamento.

### 3.5 Calibração (`cert_ver`, `cal_ganho`, `cal_offset`)

Três colunas obrigatórias em cada linha de leitura. São o **snapshot da calibração vigente naquela leitura** — descem pela config e são repetidas por linha, para a linha ser auto-descritível. Pipeline: `raw → [map, se usa_map] → nominal → [cal_ganho, cal_offset] → valor gravado`. Spec: `malha_calibracao_lastro_spec.md` (§4.3, §7.5).

---

## 4. Documentos de arquitetura (contexto, não contrato)

| Arquivo | Conteúdo |
|---|---|
| `diretrizes_projeto.md` | **Leia primeiro.** Arquitetura geral, decisões e porquês. RDC 15, multi-tenant, retenção, transporte, control-plane. |
| `odoo_modelo_dados_spec.md` | Modelo de dados (hub, coletor, sensor, área, perfil Modbus, limiares, calibração). |
| `malha_calibracao_lastro_spec.md` | Calibração, certificados, lastro criptográfico. |
| `esp32_coletor_spec.md` | Histórico do coletor WiFi/Ethernet. **Desatualizado no formato** (§1). |
| `frontend_spec.md` | SPA React de monitoramento (referência de UX/telemetria). |
| `docs/runbooks/` | Deploy real no Pi, transporte SFTP, servidor de teste. |
| `docs/discussao-drivers-extensibilidade.md` | Como drivers de transdutor são adicionados sem tocar código. |

---

## 5. Regras invioláveis do formato

1. `|`, `\n`, `\r` **proibidos** em qualquer identificador (`sensor_id`, `area_id`, `coletor_id`, `hub_id`, `cliente_id`, `site_id`). Sem escaping — proibição na origem.
2. Cadeia de hash **não atravessa dias**. Semente = `SHA256(cabeçalho canônico)`; cada linha = `SHA256(hash_anterior + linha_sem_hash_e_sem_sig)`.
3. `hdr_sig` assina a semente; cada linha carrega sua assinatura; o rodapé assina `hash_final`.
4. Flush por linha. Reboot no meio do dia **retoma** a cadeia reconstruindo o estado do arquivo existente (`hub/arquivo_diario.py::reconstruir_estado`), nunca recomeça.
5. Arquivo de alarmes é gerado e selado **todo dia, mesmo com zero eventos** — é prova positiva de monitoramento.
6. Timestamps ISO-8601 com offset (`-03:00`), segundos, sem microssegundos.

---

## 6. Design aprovado

O brainstorm foi feito em 27/07/2026 e o desenho está aprovado em
**`docs/superpowers/specs/2026-07-27-coletor-esp32s3-design.md`** — leia antes de escrever qualquer linha de firmware. Resumo das decisões travadas:

- ESP32-S3 é **coletor sob um Hub Pi** (não hub autônomo). `hub_id` do Pi, `coletor_id` próprio, N coletores por hub.
- **Pi puxa** os arquivos: coletor roda **servidor FTP read-only** sobre o SD. Dia em curso é `.parcial`, vira `.txt` no rename atômico ao selar. Pi baixa selados (sobem ao servidor) e parciais (redundância, não sobem).
- SD é **arquivo permanente**, não buffer. Rotação só acima de ~90%, do mais antigo já baixado.
- Descoberta de coletores por **lista vinda do Odoo** (host, porta, credencial), não mDNS.
- Chave privada em **NVS + flash encryption + secure boot v2** (a placa não tem ATECC608A).
- Config por **MQTT retido com payload completo**, com versão aplicada reportada de volta.
- Stack: **pioarduino + `framework = espidf` + LVGL**.
- LCD faz dashboard, detalhe do sensor, diagnóstico, alarme e provisionamento — mas **não edita limiar nem calibração**.
- Fora da v1: OTA, buzzer/LED, multi-barramento.

Itens de hardware a confirmar na wiki/esquemático da Waveshare estão listados na §12 do design.

---

## 7. Como validar o firmware sem hardware

O pipeline de validação é Python e roda no WSL2. Fluxo sugerido:

1. Firmware gera um `.txt` de um dia (pode ser em bancada).
2. Copia para o WSL2.
3. Registra a pubkey: `python -m ingestao.registro_coletores --registrar COL-XXX --a-partir-de <pem>`
4. Valida: usar `ingestao/validador.py` (ver testes em `ingestao/tests/` para a chamada exata).
5. Verde no validador = o firmware está falando o contrato certo. Vermelho = o firmware está errado, não o validador.

Comparar byte a byte contra um arquivo gerado pelo `hub/` Python com os mesmos dados é o teste mais direto de conformidade.
