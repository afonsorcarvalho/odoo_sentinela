# Coletor ESP32-S3-Touch-LCD-4.3B — design

**Data:** 27/07/2026
**Status:** aprovado, pronto para plano de implementação
**Escopo:** firmware do coletor externo RS-485 com LCD, mais o trabalho correspondente no lado Python (Hub Pi + publicação de config).

> **Contratos são código, não este documento.** Formato de arquivo, cadeia de hash e assinatura vivem em `contrato/formato.py`, `contrato/identidade.py` e `ingestao/validador.py` — repositório público `https://github.com/afonsorcarvalho/odoo_sentinela`, branch `master`. Este design não os transcreve. Handoff para a sessão Windows/PlatformIO: `esp32s3_coletor_handoff.md`.

---

## 1. Contexto e mudança de rumo

A arquitetura congelada (`diretrizes_projeto.md` §5/§6, `esp32_coletor_spec.md`) diz que sensores em RS-485 são lidos pelo **próprio Hub (Raspberry Pi)**, porque não havia dispositivo intermediário capaz de assinar; o coletor ESP32 existia só para WiFi/Ethernet. Este design **reverte esse ponto**: o ESP32-S3-Touch-LCD-4.3B passa a ser um coletor físico dedicado ao barramento RS-485, operando **sob** um Hub Pi.

O que **não** muda: formato de arquivo, cadeia de hash, assinatura na origem, tópicos MQTT, transporte Hub→servidor, modelo de dados no Odoo.

`esp32_coletor_spec.md` continua válido como registro de decisões de produto, mas está **desatualizado quanto ao formato de arquivo e ao canal de config** — ver a tabela de divergências em `esp32s3_coletor_handoff.md` §1.

---

## 2. Topologia

```
[sensores RS-485] --Modbus RTU--> [COLETOR ESP32-S3 + LCD 4.3"]
                                     - lê, escala, calibra
                                     - grava .txt no SD, hash encadeado, sig por linha
                                     - avalia alarme (histerese N=3)
                                     - servidor FTP READ-ONLY sobre o SD
                                     - LCD: dashboard, diagnóstico, alarme, provisionamento
                                          │
                        MQTT (tempo real, config retida)   FTP (Pi PUXA os arquivos)
                                          │
                                          ▼
                                   [HUB — Raspberry Pi]
                                     - Mosquitto local + bridge p/ broker central
                                     - varre N coletores, baixa arquivos, NÃO re-assina
                                     - republica config de cada coletor (MQTT retido)
                                     - SFTP p/ servidor (fluxo já existente)
                                     - segue podendo ler seu próprio RS-485 (papéis coexistem)
                                          │
                                    [OpenVPN] → servidor (ingestão, Timescale, Odoo)
```

Identidade: `hub_id` = do Pi; `coletor_id` = do ESP32; **N coletores por hub**. Cada coletor tem sua própria chave e seu próprio `pubkey_fingerprint` registrado no Odoo (`sensor_monitor.coletor`).

---

## 3. Decisões travadas

| # | Decisão | Alternativas descartadas e por quê |
|---|---|---|
| D1 | **Coletor sob Hub Pi** (não hub autônomo) | Autônomo exigiria SFTP + VPN + control-plane completo no firmware e invalidaria o `hub/` Python de campo. |
| D2 | **Pull: Pi busca os arquivos**, coletor só serve | Push obrigaria cada coletor a manter fila, retry e estado de envio. No pull, o loop de varredura do Pi já é o retry, e backfill/force-sync é o Pi relendo o SD. |
| D3 | **Servidor FTP no ESP32, read-only** | HTTP (`esp_http_server`) seria nativo do IDF; escolhido FTP por decisão do usuário, porque o Pi usa cliente pronto e o modelo mental é o de "pasta remota". Read-only para que um Pi comprometido não corrompa a prova no SD. |
| D4 | **Selado + parcial**: Pi baixa `.txt` selado e também copia o `.parcial` do dia em curso | Só-selado perderia o dia corrente se o SD morresse. Parcial é verificável (cada linha tem sig própria) e **nunca sobe ao servidor**. |
| D5 | **Marcação de selado por nome**: dia em curso é `.parcial`, vira `.txt` no rename atômico ao selar | Sem isso o Pi não distingue aberto de fechado via `LIST` — FTP não carrega metadado. |
| D6 | **Descoberta por lista vinda do Odoo** (coletor_code, host, porta, credencial) | mDNS quebra em rede hospitalar com multicast bloqueado e transforma "apareceu um coletor" em questão de confiança. |
| D7 | **Chave em NVS + flash encryption + secure boot v2** | A placa **não tem ATECC608A** (a spec original assumia ESP32-WROOM-32SE). ATECC externo custaria componente + provisionamento de fábrica; software puro sem flash encryption seria extraível por dump. |
| D8 | **Config por MQTT retido com payload completo** | Config de coletor é pequena; espelhar notify+download do Hub adicionaria cliente HTTP e parser sem ganho hoje. |
| D9 | **pioarduino + `framework = espidf` + LVGL** | Plataforma oficial `espressif32` do PlatformIO está em IDF 4.4/Arduino 2.x — velha para o painel RGB e para secure boot v2. Arduino puro esconderia sdkconfig, que é justamente onde mora a segurança. |
| D10 | **SD é arquivo permanente**, não buffer | Rotação só acima de ~90% de ocupação, do dia mais antigo **já confirmado como baixado**, com registro do descarte e alarme. Coleta nunca para por SD cheio. |
| D11 | **Tela não edita limiar nem calibração** | Fonte de verdade da config é o Odoo (`diretrizes_projeto.md` §10.1). Edição local criaria drift invisível. |

---

## 4. Firmware — módulos

Cada módulo espelha um equivalente Python já testado em campo. A tabela é o mapa de leitura obrigatório antes de escrever cada um.

| # | Módulo | Responsabilidade | Referência |
|---|---|---|---|
| 1 | `leitor` | Mestre Modbus RTU sobre RS-485: varredura por dispositivo/canal, escala mA→engenharia (`map`), filtro EWMA, gate de plausibilidade, self-healing da porta serial | `hub/leitor.py`, `hub/modbus_backend.py`, `hub/vendor/` |
| 2 | `drivers` | Perfis por modelo de transdutor: `n4aib16`, `rs_ws_n01_2d`, `generico` (função 0x03/0x04, endereço, tipo, escala, offset) | `hub/vendor/`, `docs/discussao-drivers-extensibilidade.md` |
| 3 | `arquivo` | FatFS no SD: arquivo diário de leituras e de alarmes, cabeçalho canônico, `hdr_sig`, hash encadeado, sig por linha, flush por linha, retomada de cadeia após reboot, selagem no rollover, rename `.parcial`→`.txt` | `hub/arquivo_diario.py`, `hub/arquivo_alarmes.py` |
| 4 | `assinador` | ECDSA P-256 sobre o hash hex em ASCII (mbedTLS), chave em NVS, geração no primeiro boot, exportação da pubkey PEM, fingerprint | `hub/assinador.py`, `contrato/identidade.py` |
| 5 | `detector` | Alarme na borda: histerese N=3 na entrada, folga na saída, avalia só leitura `ok`, estado por sensor persistido em NVS | `hub/detector_alarme.py` |
| 6 | `mqtt` | Publica telemetria e alarme, status retido + LWT, assina o tópico de config retida | `hub/publicador_mqtt.py` |
| 7 | `config` | Aplica config retida, valida, persiste em NVS, reporta versão aplicada, fallback regulatório se nunca recebeu | `hub/agente_config.py`, `hub/config.py` |
| 8 | `ftpd` | Servidor FTP read-only sobre o SD: `LIST`, `RETR`, PASV, sessão única, credencial por coletor | novo |
| 9 | `tempo` | SNTP + checagem de sanidade; sem NTP, aceita hora do Pi por MQTT; RTC onboard se existir (verificar) | novo |
| 10 | `ui` | LVGL 800×480: dashboard, detalhe, diagnóstico, alarme, provisionamento | novo |
| 11 | `watchdog` | TWDT por tarefa; reinício em travamento | nativo IDF |

### Regra de ouro do módulo `arquivo`

O arquivo é a prova. Ordem obrigatória por leitura: **calcula hash → assina → grava → flush**. Só depois publica MQTT. Se o MQTT falhar, o arquivo já está íntegro; o contrário não é recuperável.

**Custo do flush por linha no FatFS** (não existe no Python, existe aqui): cada append reescreve FAT e entrada de diretório. Duas consequências que o firmware precisa tratar e o `hub/` nunca precisou:

- **Desgaste do cartão.** Com D10 (SD é arquivo permanente), vida útil do cartão é requisito, não detalhe. Mitigação: cadência de produção é 1 leitura/min por sensor — algumas centenas de appends por dia, não milhares por minuto. Manter o arquivo **aberto** entre gravações (`fsync` sem `close`) em vez de abrir/fechar por linha como o Python faz. Cartão industrial obrigatório.
- **Queda de energia durante a atualização da FAT** corrompe o *diretório*, não só a última linha — pior que perder uma leitura. Regra de recuperação obrigatória no boot: ao reconstruir a cadeia do `.parcial`, **recalcular o hash de cada linha e conferir com o campo `hash` dela**; a primeira linha que não conferir (ou com contagem de campos errada) e todas as seguintes são **descartadas por truncamento do arquivo** antes de retomar a sequência. Registrar o descarte no diagnóstico e por MQTT.

`hub/arquivo_diario.py::reconstruir_estado` **não** faz essa verificação — ele confia no conteúdo e dobraria uma linha truncada dentro da cadeia, corrompendo tudo em silêncio. No Pi isso nunca apareceu (ext4 + journal); no FatFS aparece. O firmware precisa ser mais estrito que a referência aqui, e este é o único ponto do design em que ele deliberadamente diverge.

---

## 5. Fluxos

### 5.1 Dado (por leitura)

```
lê Modbus → escala/calibra → status_leitura
   → linha no .parcial do dia (hash encadeado + sig ECDSA da linha) + flush
   → MQTT sentinela/telemetria/{hub_id}/{coletor_id}/{sensor_id}
   → detector avalia (só se status == ok)
       → transição: linha no arquivo de alarmes + flush
                  + MQTT sentinela/alarme/{hub_id}/{coletor_id}/{sensor_id}
```

Rollover de meia-noite: sela os dois arquivos (rodapé com total, `hash_final`, assinatura), renomeia `.parcial`→`.txt`, abre os do dia seguinte. Arquivo de alarmes é selado **todo dia, mesmo com zero eventos**.

### 5.2 Coleta pelo Hub (pull)

```
loop do Pi, por coletor da lista:
   conecta FTP → LIST
   *.txt novos      → baixa p/ dados/{coletor_id}/          → entra no envio SFTP existente
   *.parcial        → baixa p/ dados/{coletor_id}/parciais/ → NÃO sobe ao servidor
   registra baixados; falha = retry na próxima varredura
   ao receber o .txt selado de uma data: apaga o .parcial dessa data
   publica sentinela/coletado/{hub_id}/{coletor_id} com o nome baixado
```

**Confirmação de download**: como o FTP do coletor é read-only (D3), o Hub não consegue marcar nada no cartão. Ele publica o nome de cada arquivo baixado em `sentinela/coletado/{hub_id}/{coletor_id}` (não-retido); o coletor guarda esse conjunto no NVS. É o que torna a rotação do D10 decidível — sem isso, "apagar só o que já foi transportado" não teria como ser sabido, e a rotação apagaria prova ainda não coletada.

Esse tópico é o primeiro ponto do sistema em que uma mensagem MQTT leva a **apagar arquivo**, então a propriedade de segurança precisa ser explícita: a confirmação é **advisória**, nunca gatilho. Apagar só acontece quando o cartão está de fato acima do limiar de ocupação; uma confirmação forjada, sozinha, não apaga nada. O canal segue sem assinatura na v1, como o resto do control-plane (`diretrizes_projeto.md` §10.1).

**Expiração do parcial**: assim que o selado de uma data chega, o `.parcial` correspondente vira peso morto e é apagado pelo Pi. Sem essa regra, o problema de disco cheio do D10 reaparece no Pi, onde ninguém está olhando.

**Credencial FTP — quem manda**: a **fonte de verdade é o Odoo** (D6). O provisionamento pela tela (§6) serve só ao primeiro boot e à recuperação em campo; se o Odoo publicar credencial diferente, o coletor adota a do Odoo. Falha de autenticação **não pode** aparecer como "coletor inalcançável": a tela de diagnóstico e o `status` MQTT distinguem `sem rede` de `auth recusada`, porque o segundo é erro de cadastro e o primeiro é erro de campo.

`.parcial` não casa com o glob `*_leituras.txt` de `hub/enviador_sftp.py`, então fica naturalmente fora do envio. O Hub **não re-assina nem reescreve** nada.

### 5.3 Config (Odoo → Pi → coletor)

```
Odoo (config_version_desejada) → api/config_publisher.py serializa por coletor
   → Pi publica sentinela/config/coletor/{coletor_code}  [retido, QoS 1]
        payload: {config_version, sensores[], canais[], limiares[], intervalo_s, ...}
   → coletor aplica, persiste em NVS
   → coletor publica sentinela/status/coletor/{coletor_code} [retido]
        payload: {config_version_aplicada, uptime, sd_livre, rssi, estado}
        LWT: {"estado": "offline"} no mesmo tópico
   → Pi/servidor propaga para o Odoo → drift visível (desejada vs aplicada)
```

Fail-safe: sem config alguma, usa os padrões regulatórios RDC 15 (`diretrizes_projeto.md` §3). Nunca opera sem limiar definido.

---

## 6. Telas (LVGL, 800×480, touch capacitivo)

| Tela | Conteúdo | Notas |
|---|---|---|
| **Dashboard** | Grid de tiles por sensor: valor grande, unidade, faixa vigente, cor de estado. Barra superior: WiFi, MQTT, SD, hora. Rodapé: `coletor_id` | Tela padrão; é o que o técnico vê ao passar na sala |
| **Detalhe do sensor** | Sparkline das últimas N leituras (buffer em RAM), limites vigentes, última atualização, estado do dispositivo Modbus | Toque num tile |
| **Diagnóstico** | Por endereço do barramento: respondendo, erro/CRC, latência. Rede, MQTT, SD livre, último arquivo selado, `config_version` aplicada, fonte da hora | Ferramenta de instalação e de campo |
| **Alarme** | Overlay vermelho: sensor, valor, limite violado, tempo decorrido. Lista se houver vários | Ack local publica evento auditável por MQTT; não apaga arquivo nem silencia o Odoo |
| **Provisionamento** | WiFi, host/credencial do Pi, `coletor_id`, QR + fingerprint da pubkey para enrollment no Odoo | Protegida por PIN. Elimina cabo serial e portal cativo |

Tela não edita limiar nem calibração (D11).

---

## 7. Resiliência

| Falha | Comportamento |
|---|---|
| Rede/WiFi cai | Leitura, gravação e alarme continuam. MQTT reconecta com backoff. FTP só espera o Pi voltar — nada se perde, o SD é o buffer |
| Broker indisponível | Publicação vira no-op resiliente (mesma postura de `hub/publicador_mqtt.py`) |
| SD falha ou enche | Alarme na tela e por MQTT. Continua publicando leitura por MQTT, marcada como sem lastro. Acima de ~90%, rotaciona o dia mais antigo já baixado (D10) |
| Dispositivo Modbus não responde | Retry; persistindo, grava linha com `status_leitura = sensor_offline` (linha existe, com prova) |
| Hora implausível | Não abre arquivo com data suspeita; usa último timestamp + intervalo esperado e marca o status. Registra anomalia no diagnóstico |
| Reboot no meio do dia | Reconstrói a cadeia de hash a partir do `.parcial` existente e continua a sequência — nunca recomeça o arquivo |
| Travamento | TWDT reinicia; boot retoma o dia corrente |

---

## 8. Trabalho no lado Python (fora do firmware)

| Item | Onde | O quê |
|---|---|---|
| Varredura de coletores externos | novo `hub/coletores_externos.py` | Lê lista do config, FTP `LIST`/`RETR`, baixa `.txt` e `.parcial`, mantém estado de baixados, retry natural por varredura, apaga o `.parcial` quando o selado da data chega, e publica cada nome baixado em `sentinela/coletado/{hub_id}/{coletor_id}` |
| Envio por coletor | `hub/enviador_sftp.py` | Instanciar por `coletor_id` (a estrutura de diretório já é por coletor) |
| Config dos coletores | `api/config_publisher.py` | Serializar coletores externos (endereço, credencial, canais, limiares) e publicar retido por coletor |
| Cadastro | `addons/afr_sentinela_sensor_monitor` | Campos de endereço/porta/credencial FTP no `sensor_monitor.coletor`; `config_version_desejada`/`aplicada` já existem |
| Verificação na chegada | `ingestao/validador.py` | Reuso direto: o Pi pode validar o arquivo baixado antes de repassar (opcional, mas barato) |

---

## 9. Testes

**Nível 1 — host, sem hardware** (`env:native` do PlatformIO): formato/hash/linha, detector de alarme, escala e filtro, parser de config. Comparação contra **golden files gerados pelo `contrato/` Python** — mesma entrada tem de produzir byte idêntico.

**Nível 2 — bancada**: um dia acelerado com sensor real ou simulador Modbus; verificar retomada após reboot, rollover, selagem e rename.

**Nível 3 — contrato**: arquivo gerado pelo firmware validado por `ingestao/validador.py` no WSL2. Verde lá é o critério de aceitação; vermelho significa firmware errado, não validador errado.

**Nível 4 — E2E**: coletor → Pi (pull FTP) → SFTP → ingestão → Timescale → dashboard, com MQTT em paralelo.

---

## 10. Ponto em aberto — parcial órfão

Se o SD do coletor morrer antes do rollover, o `.parcial` copiado pelo Pi tem assinatura por linha mas **não tem rodapé assinado** — e o Pi não pode selá-lo, porque não tem a chave do coletor. Duas saídas possíveis, a decidir **depois** do firmware existir (não bloqueia a implementação):

- a ingestão passa a aceitar "parcial órfão" como classe própria de evidência (linhas verificáveis, dia declaradamente incompleto); ou
- o dia fica só no Timescale via MQTT, sem lastro criptográfico, marcado como tal.

## 11. Fora da v1

OTA, buzzer/LED, múltiplos barramentos RS-485, assinatura da config pelo servidor (endurecimento previsto em `diretrizes_projeto.md` §10.1), ack de alarme com assinatura eletrônica humana (trilha "tier regulado").

---

## 12. A verificar na wiki/esquemático da Waveshare antes de codificar

Não assumir nenhum destes — confirmar no material oficial da placa e anotar no plano:

1. RTC onboard (e qual chip).
2. Slot microSD e em qual barramento (SPI/SDMMC) — e se compartilha pinos com o painel.
3. RS-485 isolado? Qual transceptor, e se o controle de direção (DE/RE) é automático ou por GPIO.
4. Quantas UARTs sobram expostas depois do painel RGB.
5. PSRAM livre com o framebuffer RGB + LVGL — define o tamanho do buffer de sparkline e o número de tiles.
6. Tamanho de flash e esquema de partição viável com secure boot v2 + (futuro) OTA A/B.
