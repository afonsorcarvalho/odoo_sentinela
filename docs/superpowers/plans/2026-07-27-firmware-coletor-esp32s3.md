# Firmware do Coletor ESP32-S3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Firmware de um coletor ESP32-S3-Touch-LCD-4.3B que lê sensores Modbus RTU em RS-485, grava um arquivo diário assinado no cartão SD, publica leituras e alarmes por MQTT, serve os arquivos ao Hub por FTP read-only e mostra tudo num LCD de 4.3".

**Architecture:** O firmware é a reimplementação em C do coletor Python que já roda no Raspberry Pi (`hub/`). O contrato de arquivo (cabeçalho canônico, cadeia de hash, assinatura por linha, rodapé selado) é definido por `contrato/formato.py` e cobrado por `ingestao/validador.py` — o firmware está certo quando o validador aceita o arquivo que ele gerou. Módulos puros (formato, hash, detector de alarme, escala, Modbus) são testados no host (`env:native`); módulos com hardware (cripto+NVS, SD, rede, UI) são testados no próprio ESP32 (`env:coletor`).

**Tech Stack:** PlatformIO com a plataforma `pioarduino` (ESP-IDF 5.x), `framework = espidf`, LVGL 9, mbedTLS (ECDSA P-256), FatFS sobre SDMMC/SPI, `esp-mqtt`, Unity para testes.

---

## Global Constraints

Valores copiados verbatim do design (`docs/superpowers/specs/2026-07-27-coletor-esp32s3-design.md`) e do código de contrato. Valem para **todas** as tasks.

- **Repositório de referência**: `https://github.com/afonsorcarvalho/odoo_sentinela`, branch `master`, **público** — ler por `https://raw.githubusercontent.com/afonsorcarvalho/odoo_sentinela/master/<caminho>`, sem autenticação. Fallback offline: `\\wsl.localhost\Ubuntu\home\afonso\docker\odoo_sentinela\`. Este é o repositório do sistema Sentinela — **não** é o projeto do firmware. Nunca commitar firmware nele.
- **Projeto do firmware**: repositório próprio, na raiz de trabalho da sessão Windows. Todos os caminhos deste plano são relativos a essa raiz.
- **Fonte da verdade do formato**: `contrato/formato.py`, `contrato/identidade.py`, `ingestao/validador.py` no repositório de referência. `esp32_coletor_spec.md` está **desatualizado** — não usar como contrato.
- `schema_version: 3`. Delimitador `|`. Caracteres `|`, `\n`, `\r` **proibidos** em qualquer identificador.
- Colunas de leituras: `seq|timestamp|sensor_id|area_id|tipo_medida|valor|unidade|protocolo_origem|status_leitura|cert_ver|cal_ganho|cal_offset|hash|sig`
- Colunas de alarmes: `seq|timestamp|sensor_id|area_id|tipo_medida|tipo_evento|tipo_violacao|valor|limite_min_vigente|limite_max_vigente|hash|sig`
- Cadeia de hash: `hash_0 = SHA256(cabeçalho_canônico)`; `hash_n = SHA256(hash_{n-1} + linha_sem_hash_e_sem_sig)`. Hex minúsculo, 64 chars. A cadeia **reinicia a cada dia**.
- Assinatura: ECDSA P-256 (secp256r1) com SHA-256, **sobre os 64 bytes ASCII do hash hexadecimal**, não sobre bytes crus. Serializada em DER e codificada em base64.
- `cal_ganho` e `cal_offset` formatados com `%.4f` sempre. `cert_ver` é inteiro.
- Timestamps ISO-8601 com offset, segundos, sem fração: `2026-07-27T08:00:00-03:00`.
- Limite ausente em linha de alarme escreve o travessão `—` (U+2014, 3 bytes UTF-8: `\xE2\x80\x94`).
- Nome do arquivo: `{data}_{hub_id}-{coletor_id}_leituras.txt` e `..._alarmes.txt`. Dia em curso usa a extensão `.parcial` no lugar de `.txt`.
- Tópicos MQTT: `sentinela/telemetria/{hub_id}/{coletor_id}/{sensor_id}`, `sentinela/alarme/{hub_id}/{coletor_id}/{sensor_id}`, `sentinela/config/coletor/{coletor_id}` (retido, servidor→coletor), `sentinela/status/coletor/{coletor_id}` (retido, coletor→servidor, também o LWT), `sentinela/coletado/{hub_id}/{coletor_id}` (não-retido, Hub→coletor, nome de arquivo já baixado — ver Task 18).
- Histerese de alarme: `N = 3` leituras consecutivas fora para entrar; saída exige estar dentro **com margem** (`alarme_margem`, default `0.0`). Só avalia leitura com `status_leitura == "ok"`.
- Ordem obrigatória por leitura: **calcula hash → assina → grava → fsync → só então publica MQTT**.
- Idioma: identificadores e comentários de código em português, como no resto do projeto. Mensagens de commit em inglês.
- Cada task termina com commit. Nunca `--no-verify`.

---

## Estrutura de arquivos

```
platformio.ini
docs/HARDWARE.md                  # fatos verificados da placa (T0)
src/
  crypto/sha256.c|.h              # SHA-256 vendored (host + target)
  crypto/base64.c|.h              # encode base64 (host + target)
  contrato/fmt_num.c|.h           # formatação determinística de números
  contrato/formato.c|.h           # cabeçalho, cadeia de hash, linhas, rodapé
  alarme/detector.c|.h            # histerese por sensor
  medicao/escala.c|.h             # map linear + calibração + faixa/status
  medicao/filtro.c|.h             # EWMA
  modbus/rtu.c|.h                 # CRC16 + montagem/parse de frame
  modbus/n4aib16.c|.h             # decode dos canais do N4AIB16
  crypto/assinador.c|.h           # ECDSA P-256 + chave no NVS   (target)
  armazenamento/arquivo.c|.h      # FatFS: .parcial, append, reparo, selagem (target)
  rede/mqtt_cliente.c|.h          # telemetria, alarme, status/LWT  (target)
  rede/config_agente.c|.h         # config retida → NVS            (target)
  rede/ftpd.c|.h                  # servidor FTP read-only         (target)
  ui/ui.c|.h  ui_dashboard.c  ui_diag.c  ui_alarme.c  ui_provisionamento.c
  app/main.c                      # loop principal, rollover, watchdog
test/
  test_formato/       test_detector/     test_escala/     test_modbus/    # native
  test_target_cripto/ test_target_arquivo/                                 # ESP32
```

---

### Task 0: Bootstrap do projeto e levantamento da placa

**Files:**
- Create: `platformio.ini`
- Create: `docs/HARDWARE.md`
- Create: `src/app/main.c`
- Create: `test/test_bootstrap/test_bootstrap.c`

**Interfaces:**
- Consumes: nada.
- Produces: dois ambientes PlatformIO funcionando — `native` (testes de host) e `coletor` (build/flash no ESP32). Todas as tasks seguintes dependem de `pio test -e native` e `pio run -e coletor` funcionarem.

- [ ] **Step 1: Levantar os fatos da placa e escrever `docs/HARDWARE.md`**

Consultar a wiki oficial da Waveshare do **ESP32-S3-Touch-LCD-4.3B** e o esquemático. Registrar em `docs/HARDWARE.md`, com link da fonte ao lado de cada fato:

1. Pinos do painel RGB (DE, VSYNC, HSYNC, PCLK, R/G/B), resolução e clock.
2. Controlador de touch (GT911?) e pinos I2C.
3. Slot microSD: existe? SPI ou SDMMC? quais pinos? compartilha algum com o painel?
4. RS-485: transceptor, se é isolado, qual UART, e se DE/RE é automático ou por GPIO.
5. RTC onboard: existe? qual chip? em qual barramento?
6. UARTs livres depois do painel.
7. Tamanho de flash, tipo e tamanho de PSRAM.

Se algum item não for confirmável na documentação, escrever `NÃO CONFIRMADO — verificar por medição` e abrir um teste de bancada; **não** chutar.

**Condição de parada**: se o item 3 apurar que a placa **não tem slot microSD**, ou que os pinos do SD conflitam com o painel RGB a ponto de não dar para usar os dois juntos, **parar o plano aqui e reportar**. As decisões D2, D3 e D10 do design todas pressupõem um cartão SD funcionando, e as Tasks 8, 12, 17 e 18 ficam inconstruíveis. A saída (módulo SD externo? SPI em pinos livres? flash interna com retenção menor?) é decisão de arquitetura com o Afonso, não improviso de quem executa a task.

- [ ] **Step 2: Escrever `platformio.ini`**

```ini
[env]
build_flags = -std=gnu11 -Isrc
test_framework = unity

[env:coletor]
platform = https://github.com/pioarduino/platform-espressif32/releases/download/54.03.21/platform-espressif32.zip
framework = espidf
board = esp32-s3-devkitc-1
board_build.flash_size = 16MB
board_build.psram_type = opi
monitor_speed = 115200
test_ignore = test_formato, test_detector, test_escala, test_modbus

[env:native]
platform = native
test_ignore = test_target_*
```

Ajustar `board_build.flash_size` e `psram_type` conforme o que a Step 1 apurou. Se a placa não for `esp32-s3-devkitc-1`-compatível em flash/PSRAM, usar `board_build.partitions` e um `board` custom — registrar o motivo em `docs/HARDWARE.md`.

- [ ] **Step 3: Escrever o teste de bootstrap**

`test/test_bootstrap/test_bootstrap.c`:

```c
#include <unity.h>

void setUp(void) {}
void tearDown(void) {}

static int soma(int a, int b) { return a + b; }

void test_ambiente_de_teste_roda(void) {
    TEST_ASSERT_EQUAL_INT(4, soma(2, 2));
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_ambiente_de_teste_roda);
    return UNITY_END();
}
```

- [ ] **Step 4: Rodar o teste no host**

Run: `pio test -e native`
Expected: PASS, 1 teste.

- [ ] **Step 5: `src/app/main.c` mínimo e build no alvo**

```c
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

void app_main(void) {
    while (1) {
        printf("[coletor] vivo\n");
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
```

Run: `pio run -e coletor -t upload -t monitor`
Expected: compila, grava e imprime `[coletor] vivo` uma vez por segundo.

- [ ] **Step 6: Commit**

```bash
git add platformio.ini docs/HARDWARE.md src/app/main.c test/test_bootstrap/
git commit -m "chore: bootstrap PlatformIO project with native and target envs"
```

---

### Task 1: SHA-256, base64 e cabeçalho canônico

**Files:**
- Create: `src/crypto/sha256.c`, `src/crypto/sha256.h`
- Create: `src/crypto/base64.c`, `src/crypto/base64.h`
- Create: `src/contrato/formato.c`, `src/contrato/formato.h`
- Test: `test/test_formato/test_formato.c`

**Interfaces:**
- Consumes: ambiente da Task 0.
- Produces:
  - `void sha256_hex(const char *dado, size_t n, char saida[65]);` — hex minúsculo, terminado em `\0`.
  - `size_t base64_encode(const uint8_t *dado, size_t n, char *saida, size_t saida_max);`
  - `size_t base64_decode(const char *texto, uint8_t *saida, size_t saida_max);` — devolve o número de bytes decodificados, `0` em entrada inválida. Usado pelos testes de assinatura (Task 7).
  - `int formato_montar_cabecalho(char *saida, size_t max, const char *tipo_arquivo, const char *coletor_id, const char *hub_id, const char *fingerprint, const char *data_referencia, const char *timezone_offset, const char *firmware_version, const char *cliente_id, const char *site_id);` — devolve o número de bytes escritos, ou `-1` se algum identificador contiver caractere proibido.
  - `void formato_hash_seed(const char *cabecalho_canonico, char saida[65]);`

- [ ] **Step 1: Vendorizar SHA-256 e base64**

Copiar para `src/crypto/` uma implementação SHA-256 de domínio público em C puro (a de `B-Con/crypto-algorithms`, `sha256.c`/`sha256.h`, serve e não tem dependências). Escrever `sha256_hex` em cima dela. Escrever `base64_encode` e `base64_decode` à mão (alfabeto padrão, com padding `=`) — são ~60 linhas juntas e evitam dependência que não existe no `env:native`.

- [ ] **Step 2: Escrever o teste falho do cabeçalho**

`test/test_formato/test_formato.c` — os valores esperados foram gerados pelo Python de referência e são o contrato:

```c
#include <string.h>
#include <unity.h>
#include "contrato/formato.h"
#include "crypto/sha256.h"

void setUp(void) {}
void tearDown(void) {}

static const char *CABECALHO_ESPERADO =
    "# schema_version: 3\n"
    "# tipo_arquivo: leituras\n"
    "# cliente_id: CLI-000123\n"
    "# site_id: SITE-0001\n"
    "# coletor_id: COL-TEST-01\n"
    "# hub_id: HUB-TEST-01\n"
    "# coletor_pubkey_fingerprint: 9F:3A:7E:B1\n"
    "# data_referencia: 2026-07-27\n"
    "# timezone_offset: -03:00\n"
    "# firmware_version: 0.1.0\n"
    "# colunas: seq|timestamp|sensor_id|area_id|tipo_medida|valor|unidade|"
    "protocolo_origem|status_leitura|cert_ver|cal_ganho|cal_offset|hash|sig\n"
    "# dia_anterior_hash_final: N/A\n";

void test_cabecalho_leituras_bate_com_o_python(void) {
    char buf[1024];
    int n = formato_montar_cabecalho(buf, sizeof buf, "leituras", "COL-TEST-01",
                                     "HUB-TEST-01", "9F:3A:7E:B1", "2026-07-27",
                                     "-03:00", "0.1.0", "CLI-000123", "SITE-0001");
    TEST_ASSERT_GREATER_THAN_INT(0, n);
    TEST_ASSERT_EQUAL_STRING(CABECALHO_ESPERADO, buf);
}

void test_seed_da_cadeia_bate_com_o_python(void) {
    char hash[65];
    formato_hash_seed(CABECALHO_ESPERADO, hash);
    TEST_ASSERT_EQUAL_STRING(
        "5cb25d3c4cd967bb566bce1a9d3ca5bb50ab0949048dbade5443ebf13edc29a9", hash);
}

void test_cabecalho_alarmes_nao_tem_dia_anterior(void) {
    char buf[1024];
    formato_montar_cabecalho(buf, sizeof buf, "alarmes", "COL-TEST-01", "HUB-TEST-01",
                             "9F:3A:7E:B1", "2026-07-27", "-03:00", "0.1.0",
                             "CLI-000123", "SITE-0001");
    TEST_ASSERT_NULL(strstr(buf, "dia_anterior_hash_final"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "# tipo_arquivo: alarmes\n"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "|tipo_evento|tipo_violacao|"));
}

void test_identificador_com_pipe_e_rejeitado(void) {
    char buf[1024];
    int n = formato_montar_cabecalho(buf, sizeof buf, "leituras", "COL|MAU",
                                     "HUB-TEST-01", "9F:3A:7E:B1", "2026-07-27",
                                     "-03:00", "0.1.0", "CLI-000123", "SITE-0001");
    TEST_ASSERT_EQUAL_INT(-1, n);
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_cabecalho_leituras_bate_com_o_python);
    RUN_TEST(test_seed_da_cadeia_bate_com_o_python);
    RUN_TEST(test_cabecalho_alarmes_nao_tem_dia_anterior);
    RUN_TEST(test_identificador_com_pipe_e_rejeitado);
    return UNITY_END();
}
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `pio test -e native -f test_formato`
Expected: FAIL — `formato.h` não existe.

- [ ] **Step 4: Implementar `formato_montar_cabecalho` e `formato_hash_seed`**

`src/contrato/formato.h`:

```c
#ifndef CONTRATO_FORMATO_H
#define CONTRATO_FORMATO_H

#include <stddef.h>

#define COLUNAS_LEITURAS "seq|timestamp|sensor_id|area_id|tipo_medida|valor|unidade|" \
                         "protocolo_origem|status_leitura|cert_ver|cal_ganho|cal_offset|hash|sig"
#define COLUNAS_ALARMES  "seq|timestamp|sensor_id|area_id|tipo_medida|tipo_evento|" \
                         "tipo_violacao|valor|limite_min_vigente|limite_max_vigente|hash|sig"

int  formato_identificador_valido(const char *valor);
int  formato_montar_cabecalho(char *saida, size_t max, const char *tipo_arquivo,
                              const char *coletor_id, const char *hub_id,
                              const char *fingerprint, const char *data_referencia,
                              const char *timezone_offset, const char *firmware_version,
                              const char *cliente_id, const char *site_id);
void formato_hash_seed(const char *cabecalho_canonico, char saida[65]);

#endif
```

`src/contrato/formato.c`:

```c
#include <stdio.h>
#include <string.h>
#include "contrato/formato.h"
#include "crypto/sha256.h"

int formato_identificador_valido(const char *valor) {
    for (const char *p = valor; *p; p++) {
        if (*p == '|' || *p == '\n' || *p == '\r') return 0;
    }
    return 1;
}

int formato_montar_cabecalho(char *saida, size_t max, const char *tipo_arquivo,
                             const char *coletor_id, const char *hub_id,
                             const char *fingerprint, const char *data_referencia,
                             const char *timezone_offset, const char *firmware_version,
                             const char *cliente_id, const char *site_id) {
    const char *ids[] = {coletor_id, hub_id, cliente_id, site_id};
    for (size_t i = 0; i < 4; i++) {
        if (!formato_identificador_valido(ids[i])) return -1;
    }
    int eh_leituras = strcmp(tipo_arquivo, "leituras") == 0;
    int n = snprintf(saida, max,
        "# schema_version: 3\n"
        "# tipo_arquivo: %s\n"
        "# cliente_id: %s\n"
        "# site_id: %s\n"
        "# coletor_id: %s\n"
        "# hub_id: %s\n"
        "# coletor_pubkey_fingerprint: %s\n"
        "# data_referencia: %s\n"
        "# timezone_offset: %s\n"
        "# firmware_version: %s\n"
        "# colunas: %s\n%s",
        tipo_arquivo, cliente_id, site_id, coletor_id, hub_id, fingerprint,
        data_referencia, timezone_offset, firmware_version,
        eh_leituras ? COLUNAS_LEITURAS : COLUNAS_ALARMES,
        eh_leituras ? "# dia_anterior_hash_final: N/A\n" : "");
    if (n < 0 || (size_t)n >= max) return -1;
    return n;
}

void formato_hash_seed(const char *cabecalho_canonico, char saida[65]) {
    sha256_hex(cabecalho_canonico, strlen(cabecalho_canonico), saida);
}
```

- [ ] **Step 5: Rodar e ver passar**

Run: `pio test -e native -f test_formato`
Expected: PASS, 4 testes.

- [ ] **Step 6: Commit**

```bash
git add src/crypto src/contrato test/test_formato
git commit -m "feat: canonical header and hash chain seed matching the Python contract"
```

---

### Task 2: Formatação de números e linha de leitura

**Files:**
- Create: `src/contrato/fmt_num.c`, `src/contrato/fmt_num.h`
- Modify: `src/contrato/formato.c`, `src/contrato/formato.h`
- Test: `test/test_formato/test_linha.c`

**Interfaces:**
- Consumes: `formato_hash_seed` (Task 1).
- Produces:
  - `void fmt_valor(double v, char *saida, size_t max);` — `%.4f` com zeros à direita removidos, mantendo pelo menos um dígito decimal (`19.8000`→`19.8`, `18.0000`→`18.0`).
  - `void fmt_coef(double v, char *saida, size_t max);` — sempre `%.4f`.
  - `int formato_linha_leitura(char *saida, size_t max, const char *hash_anterior, unsigned seq, const char *timestamp, const char *sensor_id, const char *area_id, const char *tipo_medida, double valor, const char *unidade, const char *protocolo_origem, const char *status_leitura, int cert_ver, double cal_ganho, double cal_offset, char novo_hash[65]);` — escreve a linha **sem** o campo `sig` e devolve seu comprimento, ou `-1` em identificador inválido.

Por que `fmt_valor` existe: o Python usa `str(valor)`, que não tem equivalente direto em C. A regra `%.4f` aparada é determinística, produz o mesmo texto para os valores de teste e — o que importa de verdade — é **estável**, porque o hash é calculado sobre o texto que o próprio firmware escreveu.

- [ ] **Step 1: Escrever o teste falho**

`test/test_formato/test_linha.c`:

```c
#include <string.h>
#include <unity.h>
#include "contrato/formato.h"
#include "contrato/fmt_num.h"

void setUp(void) {}
void tearDown(void) {}

static const char *SEED =
    "5cb25d3c4cd967bb566bce1a9d3ca5bb50ab0949048dbade5443ebf13edc29a9";

void test_fmt_valor_apara_zeros_mantendo_uma_casa(void) {
    char b[32];
    fmt_valor(19.8, b, sizeof b);   TEST_ASSERT_EQUAL_STRING("19.8", b);
    fmt_valor(20.05, b, sizeof b);  TEST_ASSERT_EQUAL_STRING("20.05", b);
    fmt_valor(18.0, b, sizeof b);   TEST_ASSERT_EQUAL_STRING("18.0", b);
    fmt_valor(-3.1, b, sizeof b);   TEST_ASSERT_EQUAL_STRING("-3.1", b);
}

void test_fmt_coef_sempre_quatro_casas(void) {
    char b[32];
    fmt_coef(0.965, b, sizeof b);   TEST_ASSERT_EQUAL_STRING("0.9650", b);
    fmt_coef(-0.12, b, sizeof b);   TEST_ASSERT_EQUAL_STRING("-0.1200", b);
}

void test_primeira_linha_bate_com_o_python(void) {
    char linha[512], hash[65];
    int n = formato_linha_leitura(linha, sizeof linha, SEED, 1,
        "2026-07-27T08:00:00-03:00", "SNR-EXP-TEMP-01", "AREA-EXPURGO",
        "temperatura", 19.8, "C", "4-20ma", "ok", 3, 0.9650, -0.1200, hash);
    TEST_ASSERT_GREATER_THAN_INT(0, n);
    TEST_ASSERT_EQUAL_STRING(
        "1|2026-07-27T08:00:00-03:00|SNR-EXP-TEMP-01|AREA-EXPURGO|temperatura|"
        "19.8|C|4-20ma|ok|3|0.9650|-0.1200|"
        "930cad814821e898ba99b106b3d9acea126d433180f60336b665a48b6fcec987", linha);
    TEST_ASSERT_EQUAL_STRING(
        "930cad814821e898ba99b106b3d9acea126d433180f60336b665a48b6fcec987", hash);
}

void test_segunda_linha_encadeia_no_hash_da_primeira(void) {
    char linha[512], hash[65];
    formato_linha_leitura(linha, sizeof linha,
        "930cad814821e898ba99b106b3d9acea126d433180f60336b665a48b6fcec987", 2,
        "2026-07-27T08:01:00-03:00", "SNR-EXP-TEMP-01", "AREA-EXPURGO",
        "temperatura", 20.05, "C", "4-20ma", "ok", 3, 0.9650, -0.1200, hash);
    TEST_ASSERT_EQUAL_STRING(
        "3278eac82426e28f682f00ac1f009da14565ae2351bf39a54c641dd1f0014cef", hash);
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_fmt_valor_apara_zeros_mantendo_uma_casa);
    RUN_TEST(test_fmt_coef_sempre_quatro_casas);
    RUN_TEST(test_primeira_linha_bate_com_o_python);
    RUN_TEST(test_segunda_linha_encadeia_no_hash_da_primeira);
    return UNITY_END();
}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pio test -e native -f test_formato`
Expected: FAIL — `fmt_num.h` não existe.

- [ ] **Step 3: Implementar `fmt_num`**

`src/contrato/fmt_num.c`:

```c
#include <stdio.h>
#include <string.h>
#include "contrato/fmt_num.h"

void fmt_coef(double v, char *saida, size_t max) {
    snprintf(saida, max, "%.4f", v);
}

void fmt_valor(double v, char *saida, size_t max) {
    snprintf(saida, max, "%.4f", v);
    char *ponto = strchr(saida, '.');
    if (!ponto) return;
    char *fim = saida + strlen(saida) - 1;
    while (fim > ponto + 1 && *fim == '0') { *fim = '\0'; fim--; }
}
```

- [ ] **Step 4: Implementar `formato_linha_leitura`**

Acrescentar a `src/contrato/formato.c` (e o protótipo ao `.h`):

```c
#include "contrato/fmt_num.h"

static void encadear(const char *hash_anterior, const char *linha_sem_hash,
                     char saida[65]) {
    char buf[1024];
    snprintf(buf, sizeof buf, "%s%s", hash_anterior, linha_sem_hash);
    sha256_hex(buf, strlen(buf), saida);
}

int formato_linha_leitura(char *saida, size_t max, const char *hash_anterior,
                          unsigned seq, const char *timestamp, const char *sensor_id,
                          const char *area_id, const char *tipo_medida, double valor,
                          const char *unidade, const char *protocolo_origem,
                          const char *status_leitura, int cert_ver,
                          double cal_ganho, double cal_offset, char novo_hash[65]) {
    if (!formato_identificador_valido(sensor_id) ||
        !formato_identificador_valido(area_id)) return -1;
    char v[32], g[32], o[32];
    fmt_valor(valor, v, sizeof v);
    fmt_coef(cal_ganho, g, sizeof g);
    fmt_coef(cal_offset, o, sizeof o);
    char sem_hash[512];
    int n = snprintf(sem_hash, sizeof sem_hash, "%u|%s|%s|%s|%s|%s|%s|%s|%s|%d|%s|%s",
                     seq, timestamp, sensor_id, area_id, tipo_medida, v, unidade,
                     protocolo_origem, status_leitura, cert_ver, g, o);
    if (n < 0 || (size_t)n >= sizeof sem_hash) return -1;
    encadear(hash_anterior, sem_hash, novo_hash);
    n = snprintf(saida, max, "%s|%s", sem_hash, novo_hash);
    if (n < 0 || (size_t)n >= max) return -1;
    return n;
}
```

- [ ] **Step 5: Rodar e ver passar**

Run: `pio test -e native -f test_formato`
Expected: PASS, 8 testes (4 da Task 1 + 4 desta).

- [ ] **Step 6: Commit**

```bash
git add src/contrato test/test_formato
git commit -m "feat: reading line with chained hash matching the Python contract"
```

---

### Task 3: Linha de alarme e rodapé

**Files:**
- Modify: `src/contrato/formato.c`, `src/contrato/formato.h`
- Test: `test/test_formato/test_alarme_rodape.c`

**Interfaces:**
- Consumes: `encadear`, `fmt_valor` (Task 2).
- Produces:
  - `int formato_linha_alarme(char *saida, size_t max, const char *hash_anterior, unsigned seq, const char *timestamp, const char *sensor_id, const char *area_id, const char *tipo_medida, const char *tipo_evento, const char *tipo_violacao, double valor, int tem_min, double limite_min, int tem_max, double limite_max, char novo_hash[65]);` — `tem_min`/`tem_max` a zero escrevem `—`.
  - `int formato_rodape(char *saida, size_t max, unsigned total, const char *hash_final, const char *assinatura_b64, const char *campo_total);` — `campo_total` é `"total_linhas"` ou `"total_eventos"`.

- [ ] **Step 1: Escrever o teste falho**

`test/test_formato/test_alarme_rodape.c`:

```c
#include <unity.h>
#include "contrato/formato.h"

void setUp(void) {}
void tearDown(void) {}

void test_cabecalho_de_alarmes_semeia_a_cadeia(void) {
    char cab[1024], hash[65];
    formato_montar_cabecalho(cab, sizeof cab, "alarmes", "COL-TEST-01", "HUB-TEST-01",
                             "9F:3A:7E:B1", "2026-07-27", "-03:00", "0.1.0",
                             "CLI-000123", "SITE-0001");
    formato_hash_seed(cab, hash);
    TEST_ASSERT_EQUAL_STRING(
        "1c80899d97b0c5874c4aea103740b464567bec0672d8813cb4bb85277c4a2ead", hash);
}

void test_linha_de_alarme_bate_com_o_python(void) {
    char linha[512], hash[65];
    formato_linha_alarme(linha, sizeof linha,
        "1c80899d97b0c5874c4aea103740b464567bec0672d8813cb4bb85277c4a2ead", 1,
        "2026-07-27T08:05:00-03:00", "SNR-EXP-TEMP-01", "AREA-EXPURGO", "temperatura",
        "entrada_alarme", "acima_limite", 23.4, 1, 18.0, 1, 22.0, hash);
    TEST_ASSERT_EQUAL_STRING(
        "1|2026-07-27T08:05:00-03:00|SNR-EXP-TEMP-01|AREA-EXPURGO|temperatura|"
        "entrada_alarme|acima_limite|23.4|18.0|22.0|"
        "d56a55708610222dd0b5c8f1ca6d4ff7bbd9012f3db294a12d71625c825ee4b8", linha);
}

void test_limite_ausente_vira_travessao(void) {
    char linha[512], hash[65];
    formato_linha_alarme(linha, sizeof linha, "00", 1, "2026-07-27T08:05:00-03:00",
        "S1", "A1", "temperatura", "entrada_alarme", "abaixo_limite",
        1.8, 1, 2.5, 0, 0.0, hash);
    TEST_ASSERT_NOT_NULL(strstr(linha, "|2.5|\xE2\x80\x94|"));
}

void test_rodape_de_leituras(void) {
    char buf[256];
    formato_rodape(buf, sizeof buf, 2,
        "3278eac82426e28f682f00ac1f009da14565ae2351bf39a54c641dd1f0014cef",
        "ASSIN==", "total_linhas");
    TEST_ASSERT_EQUAL_STRING(
        "# total_linhas: 2\n"
        "# hash_final: 3278eac82426e28f682f00ac1f009da14565ae2351bf39a54c641dd1f0014cef\n"
        "# assinatura: ASSIN==\n", buf);
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_cabecalho_de_alarmes_semeia_a_cadeia);
    RUN_TEST(test_linha_de_alarme_bate_com_o_python);
    RUN_TEST(test_limite_ausente_vira_travessao);
    RUN_TEST(test_rodape_de_leituras);
    return UNITY_END();
}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pio test -e native -f test_formato`
Expected: FAIL — `formato_linha_alarme` não existe.

- [ ] **Step 3: Implementar**

Acrescentar a `src/contrato/formato.c`:

```c
int formato_linha_alarme(char *saida, size_t max, const char *hash_anterior,
                         unsigned seq, const char *timestamp, const char *sensor_id,
                         const char *area_id, const char *tipo_medida,
                         const char *tipo_evento, const char *tipo_violacao,
                         double valor, int tem_min, double limite_min,
                         int tem_max, double limite_max, char novo_hash[65]) {
    if (!formato_identificador_valido(sensor_id) ||
        !formato_identificador_valido(area_id)) return -1;
    char v[32], lmin[32], lmax[32];
    fmt_valor(valor, v, sizeof v);
    if (tem_min) fmt_valor(limite_min, lmin, sizeof lmin); else snprintf(lmin, sizeof lmin, "\xE2\x80\x94");
    if (tem_max) fmt_valor(limite_max, lmax, sizeof lmax); else snprintf(lmax, sizeof lmax, "\xE2\x80\x94");
    char sem_hash[512];
    int n = snprintf(sem_hash, sizeof sem_hash, "%u|%s|%s|%s|%s|%s|%s|%s|%s|%s",
                     seq, timestamp, sensor_id, area_id, tipo_medida, tipo_evento,
                     tipo_violacao, v, lmin, lmax);
    if (n < 0 || (size_t)n >= sizeof sem_hash) return -1;
    encadear(hash_anterior, sem_hash, novo_hash);
    n = snprintf(saida, max, "%s|%s", sem_hash, novo_hash);
    if (n < 0 || (size_t)n >= max) return -1;
    return n;
}

int formato_rodape(char *saida, size_t max, unsigned total, const char *hash_final,
                   const char *assinatura_b64, const char *campo_total) {
    int n = snprintf(saida, max, "# %s: %u\n# hash_final: %s\n# assinatura: %s\n",
                     campo_total, total, hash_final, assinatura_b64);
    if (n < 0 || (size_t)n >= max) return -1;
    return n;
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pio test -e native -f test_formato`
Expected: PASS, 12 testes.

- [ ] **Step 5: Commit**

```bash
git add src/contrato test/test_formato
git commit -m "feat: alarm line and sealed footer"
```

---

### Task 4: Detector de alarme com histerese

**Files:**
- Create: `src/alarme/detector.c`, `src/alarme/detector.h`
- Test: `test/test_detector/test_detector.c`

**Interfaces:**
- Consumes: nada além de C padrão.
- Produces:
  - `typedef struct { char sensor_id[48]; int em_alarme; int tipo_violacao; unsigned contador; } estado_sensor_t;` — `tipo_violacao`: `0` nenhum, `1` acima, `2` abaixo.
  - `typedef struct { int houve_evento; int tipo_evento; int tipo_violacao; } evento_alarme_t;` — `tipo_evento`: `0` nenhum, `1` entrada, `2` saída.
  - `evento_alarme_t detector_avaliar(estado_sensor_t *st, int status_ok, double valor, int tem_min, double lmin, int tem_max, double lmax, unsigned n, double margem);`

Referência de comportamento: `hub/detector_alarme.py`. Regras: só avalia com `status_ok`; entra em alarme após `n` leituras consecutivas fora; sai quando estiver dentro **com margem** nas duas pontas configuradas; qualquer leitura dentro dos limites zera o contador.

- [ ] **Step 1: Escrever o teste falho**

`test/test_detector/test_detector.c`:

```c
#include <string.h>
#include <unity.h>
#include "alarme/detector.h"

void setUp(void) {}
void tearDown(void) {}

static estado_sensor_t novo(void) {
    estado_sensor_t st;
    memset(&st, 0, sizeof st);
    return st;
}

void test_uma_leitura_fora_nao_dispara(void) {
    estado_sensor_t st = novo();
    evento_alarme_t ev = detector_avaliar(&st, 1, 23.0, 1, 18.0, 1, 22.0, 3, 0.0);
    TEST_ASSERT_FALSE(ev.houve_evento);
    TEST_ASSERT_EQUAL_UINT(1, st.contador);
}

void test_tres_leituras_fora_disparam_entrada(void) {
    estado_sensor_t st = novo();
    detector_avaliar(&st, 1, 23.0, 1, 18.0, 1, 22.0, 3, 0.0);
    detector_avaliar(&st, 1, 23.1, 1, 18.0, 1, 22.0, 3, 0.0);
    evento_alarme_t ev = detector_avaliar(&st, 1, 23.2, 1, 18.0, 1, 22.0, 3, 0.0);
    TEST_ASSERT_TRUE(ev.houve_evento);
    TEST_ASSERT_EQUAL_INT(1, ev.tipo_evento);
    TEST_ASSERT_EQUAL_INT(1, ev.tipo_violacao);
    TEST_ASSERT_TRUE(st.em_alarme);
    TEST_ASSERT_EQUAL_UINT(0, st.contador);
}

void test_leitura_dentro_zera_o_contador(void) {
    estado_sensor_t st = novo();
    detector_avaliar(&st, 1, 23.0, 1, 18.0, 1, 22.0, 3, 0.0);
    detector_avaliar(&st, 1, 20.0, 1, 18.0, 1, 22.0, 3, 0.0);
    TEST_ASSERT_EQUAL_UINT(0, st.contador);
}

void test_leitura_nao_ok_e_ignorada(void) {
    estado_sensor_t st = novo();
    evento_alarme_t ev = detector_avaliar(&st, 0, 99.0, 1, 18.0, 1, 22.0, 3, 0.0);
    TEST_ASSERT_FALSE(ev.houve_evento);
    TEST_ASSERT_EQUAL_UINT(0, st.contador);
}

void test_saida_exige_margem(void) {
    estado_sensor_t st = novo();
    st.em_alarme = 1; st.tipo_violacao = 1;
    evento_alarme_t sem_folga = detector_avaliar(&st, 1, 21.9, 1, 18.0, 1, 22.0, 3, 0.5);
    TEST_ASSERT_FALSE(sem_folga.houve_evento);
    evento_alarme_t com_folga = detector_avaliar(&st, 1, 21.4, 1, 18.0, 1, 22.0, 3, 0.5);
    TEST_ASSERT_TRUE(com_folga.houve_evento);
    TEST_ASSERT_EQUAL_INT(2, com_folga.tipo_evento);
    TEST_ASSERT_EQUAL_INT(1, com_folga.tipo_violacao);
    TEST_ASSERT_FALSE(st.em_alarme);
}

void test_abaixo_do_minimo_dispara_abaixo_limite(void) {
    estado_sensor_t st = novo();
    detector_avaliar(&st, 1, 1.0, 1, 2.5, 0, 0.0, 2, 0.0);
    evento_alarme_t ev = detector_avaliar(&st, 1, 1.1, 1, 2.5, 0, 0.0, 2, 0.0);
    TEST_ASSERT_TRUE(ev.houve_evento);
    TEST_ASSERT_EQUAL_INT(2, ev.tipo_violacao);
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_uma_leitura_fora_nao_dispara);
    RUN_TEST(test_tres_leituras_fora_disparam_entrada);
    RUN_TEST(test_leitura_dentro_zera_o_contador);
    RUN_TEST(test_leitura_nao_ok_e_ignorada);
    RUN_TEST(test_saida_exige_margem);
    RUN_TEST(test_abaixo_do_minimo_dispara_abaixo_limite);
    return UNITY_END();
}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pio test -e native -f test_detector`
Expected: FAIL — `detector.h` não existe.

- [ ] **Step 3: Implementar**

`src/alarme/detector.c`:

```c
#include "alarme/detector.h"

evento_alarme_t detector_avaliar(estado_sensor_t *st, int status_ok, double valor,
                                 int tem_min, double lmin, int tem_max, double lmax,
                                 unsigned n, double margem) {
    evento_alarme_t ev = {0, 0, 0};
    if (!status_ok) return ev;               // gate de plausibilidade

    if (st->em_alarme) {
        int dentro_com_folga = (!tem_max || valor < lmax - margem) &&
                               (!tem_min || valor > lmin + margem);
        if (dentro_com_folga) {
            ev.houve_evento = 1;
            ev.tipo_evento = 2;              // saida_alarme
            ev.tipo_violacao = st->tipo_violacao;
            st->em_alarme = 0;
            st->tipo_violacao = 0;
            st->contador = 0;
        }
        return ev;
    }

    int acima = tem_max && valor > lmax;
    int abaixo = tem_min && valor < lmin;
    if (!acima && !abaixo) { st->contador = 0; return ev; }

    st->contador++;
    if (st->contador < n) return ev;

    st->em_alarme = 1;
    st->tipo_violacao = acima ? 1 : 2;
    st->contador = 0;
    ev.houve_evento = 1;
    ev.tipo_evento = 1;                      // entrada_alarme
    ev.tipo_violacao = st->tipo_violacao;
    return ev;
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pio test -e native -f test_detector`
Expected: PASS, 6 testes.

- [ ] **Step 5: Commit**

```bash
git add src/alarme test/test_detector
git commit -m "feat: edge alarm detector with hysteresis and exit margin"
```

---

### Task 5: Escala, calibração e filtro EWMA

**Files:**
- Create: `src/medicao/escala.c`, `src/medicao/escala.h`
- Create: `src/medicao/filtro.c`, `src/medicao/filtro.h`
- Test: `test/test_escala/test_escala.c`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `double escala_map(double x, double in_min, double in_max, double out_min, double out_max);`
  - `double escala_calibrar(double nominal, double ganho, double offset);` — `ganho * nominal + offset`.
  - `const char *escala_status(double valor, int tem_faixa_min, double faixa_min, int tem_faixa_max, double faixa_max);` — devolve `"ok"` ou `"suspeito"`.
  - `typedef struct { double valor; int iniciado; } ewma_t;` e `double filtro_ewma(ewma_t *e, double amostra, double alpha);`

Referência: `hub/leitor.py::_normalizar`/`_fora_da_faixa`, `hub/vendor/modbus-connector/common/scaling.py`. Pipeline: `bruto → map → nominal → calibração → valor gravado`.

- [ ] **Step 1: Escrever o teste falho**

`test/test_escala/test_escala.c`:

```c
#include <string.h>
#include <unity.h>
#include "medicao/escala.h"
#include "medicao/filtro.h"

void setUp(void) {}
void tearDown(void) {}

void test_map_4a20ma_para_faixa_de_engenharia(void) {
    TEST_ASSERT_DOUBLE_WITHIN(1e-9, -50.0, escala_map(4.0,  4.0, 20.0, -50.0, 150.0));
    TEST_ASSERT_DOUBLE_WITHIN(1e-9, 150.0, escala_map(20.0, 4.0, 20.0, -50.0, 150.0));
    TEST_ASSERT_DOUBLE_WITHIN(1e-9,  50.0, escala_map(12.0, 4.0, 20.0, -50.0, 150.0));
}

void test_calibracao_aplica_ganho_e_offset(void) {
    TEST_ASSERT_DOUBLE_WITHIN(1e-9, 19.18, escala_calibrar(20.0, 0.965, -0.12));
}

void test_valor_fora_da_faixa_fisica_vira_suspeito(void) {
    TEST_ASSERT_EQUAL_STRING("ok",       escala_status(20.0, 1, -10.0, 1, 60.0));
    TEST_ASSERT_EQUAL_STRING("suspeito", escala_status(99.0, 1, -10.0, 1, 60.0));
    TEST_ASSERT_EQUAL_STRING("suspeito", escala_status(-20.0, 1, -10.0, 1, 60.0));
    TEST_ASSERT_EQUAL_STRING("ok",       escala_status(999.0, 0, 0.0, 0, 0.0));
}

void test_ewma_primeira_amostra_passa_direto(void) {
    ewma_t e = {0.0, 0};
    TEST_ASSERT_DOUBLE_WITHIN(1e-9, 10.0, filtro_ewma(&e, 10.0, 0.3));
}

void test_ewma_suaviza_a_partir_da_segunda(void) {
    ewma_t e = {0.0, 0};
    filtro_ewma(&e, 10.0, 0.3);
    TEST_ASSERT_DOUBLE_WITHIN(1e-9, 13.0, filtro_ewma(&e, 20.0, 0.3));
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_map_4a20ma_para_faixa_de_engenharia);
    RUN_TEST(test_calibracao_aplica_ganho_e_offset);
    RUN_TEST(test_valor_fora_da_faixa_fisica_vira_suspeito);
    RUN_TEST(test_ewma_primeira_amostra_passa_direto);
    RUN_TEST(test_ewma_suaviza_a_partir_da_segunda);
    return UNITY_END();
}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pio test -e native -f test_escala`
Expected: FAIL — headers não existem.

- [ ] **Step 3: Implementar**

`src/medicao/escala.c`:

```c
#include "medicao/escala.h"

double escala_map(double x, double in_min, double in_max,
                  double out_min, double out_max) {
    if (in_min == in_max) return out_min;
    return out_min + (x - in_min) * (out_max - out_min) / (in_max - in_min);
}

double escala_calibrar(double nominal, double ganho, double offset) {
    return ganho * nominal + offset;
}

const char *escala_status(double valor, int tem_faixa_min, double faixa_min,
                          int tem_faixa_max, double faixa_max) {
    if (tem_faixa_min && valor < faixa_min) return "suspeito";
    if (tem_faixa_max && valor > faixa_max) return "suspeito";
    return "ok";
}
```

`src/medicao/filtro.c`:

```c
#include "medicao/filtro.h"

double filtro_ewma(ewma_t *e, double amostra, double alpha) {
    if (!e->iniciado) { e->valor = amostra; e->iniciado = 1; return e->valor; }
    e->valor = alpha * amostra + (1.0 - alpha) * e->valor;
    return e->valor;
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pio test -e native -f test_escala`
Expected: PASS, 5 testes.

- [ ] **Step 5: Commit**

```bash
git add src/medicao test/test_escala
git commit -m "feat: linear scaling, calibration, plausibility gate and EWMA filter"
```

---

### Task 6: Modbus RTU e decode do N4AIB16

**Files:**
- Create: `src/modbus/rtu.c`, `src/modbus/rtu.h`
- Create: `src/modbus/n4aib16.c`, `src/modbus/n4aib16.h`
- Test: `test/test_modbus/test_modbus.c`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `uint16_t rtu_crc16(const uint8_t *dado, size_t n);` — CRC16 Modbus, polinômio `0xA001`, semente `0xFFFF`.
  - `size_t rtu_montar_leitura(uint8_t *saida, uint8_t endereco, uint8_t funcao, uint16_t reg_inicial, uint16_t qtd);` — devolve o tamanho do frame (8 bytes).
  - `int rtu_parse_resposta(const uint8_t *frame, size_t n, uint8_t endereco_esperado, uint8_t funcao_esperada, uint16_t *registros, size_t max_regs);` — devolve a quantidade de registradores, `-1` em CRC/endereço/função errados, `-2` se for exceção Modbus.
  - `double n4aib16_bruto_para_ma(uint16_t bruto);` — `bruto / 100.0` (calibração medida no módulo real: 100 contagens por mA).

Referência: `hub/vendor/modbus-connector/drivers/n4aib16.py`. O N4AIB16 lê por **função 0x04 (input registers)**, base `0x0000`, CH1..CH15 corrente e CH16 tensão. FC03 devolve exceção 0x02 neste módulo.

- [ ] **Step 1: Escrever o teste falho**

`test/test_modbus/test_modbus.c`:

```c
#include <stdint.h>
#include <unity.h>
#include "modbus/rtu.h"
#include "modbus/n4aib16.h"

void setUp(void) {}
void tearDown(void) {}

void test_crc16_de_frame_conhecido(void) {
    // Frame padrão Modbus: addr 0x01, FC 0x04, reg 0x0000, qtd 0x0001
    const uint8_t f[] = {0x01, 0x04, 0x00, 0x00, 0x00, 0x01};
    TEST_ASSERT_EQUAL_HEX16(0xCA31, rtu_crc16(f, sizeof f));
}

void test_monta_frame_de_leitura_com_crc(void) {
    uint8_t f[8];
    size_t n = rtu_montar_leitura(f, 0x01, 0x04, 0x0000, 0x0001);
    TEST_ASSERT_EQUAL_UINT(8, n);
    TEST_ASSERT_EQUAL_HEX8(0x01, f[0]);
    TEST_ASSERT_EQUAL_HEX8(0x04, f[1]);
    TEST_ASSERT_EQUAL_HEX8(0x00, f[2]);
    TEST_ASSERT_EQUAL_HEX8(0x00, f[3]);
    TEST_ASSERT_EQUAL_HEX8(0x00, f[4]);
    TEST_ASSERT_EQUAL_HEX8(0x01, f[5]);
    uint16_t crc = rtu_crc16(f, 6);
    TEST_ASSERT_EQUAL_HEX8(crc & 0xFF, f[6]);          // CRC little-endian
    TEST_ASSERT_EQUAL_HEX8((crc >> 8) & 0xFF, f[7]);
}

void test_parse_de_resposta_valida(void) {
    uint8_t f[16] = {0x01, 0x04, 0x04, 0x01, 0x2C, 0x07, 0xD0};
    uint16_t crc = rtu_crc16(f, 7);
    f[7] = crc & 0xFF; f[8] = (crc >> 8) & 0xFF;
    uint16_t regs[8];
    int n = rtu_parse_resposta(f, 9, 0x01, 0x04, regs, 8);
    TEST_ASSERT_EQUAL_INT(2, n);
    TEST_ASSERT_EQUAL_UINT16(300, regs[0]);
    TEST_ASSERT_EQUAL_UINT16(2000, regs[1]);
}

void test_parse_rejeita_crc_errado(void) {
    uint8_t f[9] = {0x01, 0x04, 0x04, 0x01, 0x2C, 0x07, 0xD0, 0x00, 0x00};
    uint16_t regs[8];
    TEST_ASSERT_EQUAL_INT(-1, rtu_parse_resposta(f, 9, 0x01, 0x04, regs, 8));
}

void test_parse_detecta_excecao_modbus(void) {
    uint8_t f[5] = {0x01, 0x84, 0x02, 0x00, 0x00};
    uint16_t crc = rtu_crc16(f, 3);
    f[3] = crc & 0xFF; f[4] = (crc >> 8) & 0xFF;
    uint16_t regs[8];
    TEST_ASSERT_EQUAL_INT(-2, rtu_parse_resposta(f, 5, 0x01, 0x04, regs, 8));
}

void test_bruto_do_n4aib16_vira_miliamperes(void) {
    TEST_ASSERT_DOUBLE_WITHIN(1e-9,  3.0, n4aib16_bruto_para_ma(300));
    TEST_ASSERT_DOUBLE_WITHIN(1e-9, 20.0, n4aib16_bruto_para_ma(2000));
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_crc16_de_frame_conhecido);
    RUN_TEST(test_monta_frame_de_leitura_com_crc);
    RUN_TEST(test_parse_de_resposta_valida);
    RUN_TEST(test_parse_rejeita_crc_errado);
    RUN_TEST(test_parse_detecta_excecao_modbus);
    RUN_TEST(test_bruto_do_n4aib16_vira_miliamperes);
    return UNITY_END();
}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pio test -e native -f test_modbus`
Expected: FAIL — headers não existem.

Se `test_crc16_de_frame_conhecido` falhar **depois** de a implementação estar escrita e revisada, confirmar o valor esperado rodando o CRC de referência do projeto:
`wsl -d Ubuntu -- bash -lc "cd /home/afonso/docker/odoo_sentinela/hub/vendor/modbus-connector && python3 -c \"import modbus_scanner as m; print(hex(m.crc16(bytes([1,4,0,0,0,1]))))\""`
e corrigir o esperado do teste, não a implementação.

- [ ] **Step 3: Implementar**

`src/modbus/rtu.c`:

```c
#include "modbus/rtu.h"

uint16_t rtu_crc16(const uint8_t *dado, size_t n) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < n; i++) {
        crc ^= dado[i];
        for (int b = 0; b < 8; b++) {
            crc = (crc & 1) ? (uint16_t)((crc >> 1) ^ 0xA001) : (uint16_t)(crc >> 1);
        }
    }
    return crc;
}

size_t rtu_montar_leitura(uint8_t *saida, uint8_t endereco, uint8_t funcao,
                          uint16_t reg_inicial, uint16_t qtd) {
    saida[0] = endereco;
    saida[1] = funcao;
    saida[2] = (uint8_t)(reg_inicial >> 8);
    saida[3] = (uint8_t)(reg_inicial & 0xFF);
    saida[4] = (uint8_t)(qtd >> 8);
    saida[5] = (uint8_t)(qtd & 0xFF);
    uint16_t crc = rtu_crc16(saida, 6);
    saida[6] = (uint8_t)(crc & 0xFF);
    saida[7] = (uint8_t)(crc >> 8);
    return 8;
}

int rtu_parse_resposta(const uint8_t *frame, size_t n, uint8_t endereco_esperado,
                       uint8_t funcao_esperada, uint16_t *registros, size_t max_regs) {
    if (n < 5) return -1;
    uint16_t crc = rtu_crc16(frame, n - 2);
    if (frame[n - 2] != (uint8_t)(crc & 0xFF) || frame[n - 1] != (uint8_t)(crc >> 8)) return -1;
    if (frame[0] != endereco_esperado) return -1;
    if (frame[1] == (uint8_t)(funcao_esperada | 0x80)) return -2;
    if (frame[1] != funcao_esperada) return -1;
    size_t bytes = frame[2];
    if (bytes % 2 != 0 || bytes / 2 > max_regs || n < 3 + bytes + 2) return -1;
    for (size_t i = 0; i < bytes / 2; i++) {
        registros[i] = (uint16_t)((frame[3 + i * 2] << 8) | frame[4 + i * 2]);
    }
    return (int)(bytes / 2);
}
```

`src/modbus/n4aib16.c`:

```c
#include "modbus/n4aib16.h"

#define CONTAGENS_POR_MA 100.0

double n4aib16_bruto_para_ma(uint16_t bruto) {
    return (double)bruto / CONTAGENS_POR_MA;
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pio test -e native -f test_modbus`
Expected: PASS, 6 testes.

- [ ] **Step 5: Commit**

```bash
git add src/modbus test/test_modbus
git commit -m "feat: Modbus RTU framing, CRC16 and N4AIB16 channel decoding"
```

---

### Task 7: Assinador ECDSA P-256 com chave no NVS

**Files:**
- Create: `src/crypto/assinador.c`, `src/crypto/assinador.h`
- Test: `test/test_target_cripto/test_cripto.c`

**Interfaces:**
- Consumes: `base64_encode` (Task 1).
- Produces:
  - `int assinador_iniciar(void);` — carrega a chave do NVS; se não existir, gera uma P-256 e persiste. `0` em sucesso.
  - `int assinador_assinar_hash(const char *hash_hex, char *sig_b64, size_t max);` — assina os 64 bytes ASCII do hash, DER + base64.
  - `int assinador_pubkey_pem(char *saida, size_t max);`
  - `int assinador_fingerprint(char saida[100]);` — SHA-256 do DER SubjectPublicKeyInfo, hex **maiúsculo**, separado por `:`.

Este teste roda **no ESP32** (`env:coletor`), porque depende de mbedTLS e NVS.

- [ ] **Step 1: Escrever o teste falho (roda no alvo)**

`test/test_target_cripto/test_cripto.c`:

```c
#include <string.h>
#include <unity.h>
#include "nvs_flash.h"
#include "crypto/assinador.h"
#include "crypto/base64.h"

void setUp(void) {}
void tearDown(void) {}

static const char *HASH =
    "5cb25d3c4cd967bb566bce1a9d3ca5bb50ab0949048dbade5443ebf13edc29a9";

void test_inicia_e_gera_chave(void) {
    TEST_ASSERT_EQUAL_INT(0, assinador_iniciar());
}

void test_pubkey_sai_em_pem(void) {
    char pem[512];
    TEST_ASSERT_EQUAL_INT(0, assinador_pubkey_pem(pem, sizeof pem));
    TEST_ASSERT_NOT_NULL(strstr(pem, "-----BEGIN PUBLIC KEY-----"));
    TEST_ASSERT_NOT_NULL(strstr(pem, "-----END PUBLIC KEY-----"));
}

void test_fingerprint_tem_formato_de_octetos(void) {
    char fp[100];
    TEST_ASSERT_EQUAL_INT(0, assinador_fingerprint(fp));
    TEST_ASSERT_EQUAL_UINT(95, strlen(fp));   // 32 octetos hex + 31 ':'
    TEST_ASSERT_EQUAL_CHAR(':', fp[2]);
}

void test_assinatura_decodifica_para_der_de_ecdsa(void) {
    char sig[256];
    uint8_t der[128];
    TEST_ASSERT_EQUAL_INT(0, assinador_assinar_hash(HASH, sig, sizeof sig));
    TEST_ASSERT_GREATER_THAN_UINT(80, strlen(sig));
    size_t n = base64_decode(sig, der, sizeof der);
    TEST_ASSERT_GREATER_THAN_UINT(68, n);          // DER de P-256: 70..72 bytes
    TEST_ASSERT_LESS_THAN_UINT(73, n);
    TEST_ASSERT_EQUAL_HEX8(0x30, der[0]);          // SEQUENCE
    TEST_ASSERT_EQUAL_UINT(n - 2, der[1]);         // comprimento declarado
}

void test_chave_sobrevive_a_reinicio_do_modulo(void) {
    char fp1[100], fp2[100];
    assinador_fingerprint(fp1);
    TEST_ASSERT_EQUAL_INT(0, assinador_iniciar());   // recarrega do NVS
    assinador_fingerprint(fp2);
    TEST_ASSERT_EQUAL_STRING(fp1, fp2);
}

void app_main(void) {
    nvs_flash_init();
    UNITY_BEGIN();
    RUN_TEST(test_inicia_e_gera_chave);
    RUN_TEST(test_pubkey_sai_em_pem);
    RUN_TEST(test_fingerprint_tem_formato_de_octetos);
    RUN_TEST(test_assinatura_decodifica_para_der_de_ecdsa);
    RUN_TEST(test_chave_sobrevive_a_reinicio_do_modulo);
    UNITY_END();
}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pio test -e coletor -f test_target_cripto`
Expected: FAIL — `assinador.h` não existe.

- [ ] **Step 3: Implementar o assinador**

Usar `mbedtls_pk_context` com `MBEDTLS_ECP_DP_SECP256R1`. Pontos obrigatórios:

- Geração: `mbedtls_ecp_gen_key` com `mbedtls_ctr_drbg` semeado por `mbedtls_entropy_func` (o ESP-IDF já liga o TRNG de hardware).
- Persistência: serializar com `mbedtls_pk_write_key_der` e gravar como blob no NVS, namespace `"coletor"`, chave `"ec_priv"`. Carregar com `mbedtls_pk_parse_key`.
- Assinatura: `mbedtls_pk_sign(&pk, MBEDTLS_MD_SHA256, digest_do_hash_hex, 32, sig_der, ...)` — onde `digest_do_hash_hex` é `SHA256(hash_hex_ascii, 64)`. Isto reproduz exatamente `chave.sign(hash_hex.encode(), ec.ECDSA(hashes.SHA256()))` do Python: a mensagem assinada são os 64 caracteres do hash, não os 32 bytes que ele representa. Errar isso faz o validador rejeitar tudo.
- Fingerprint: `mbedtls_pk_write_pubkey_der` → `SHA256` desse DER → hex maiúsculo com `:` entre octetos.

- [ ] **Step 4: Rodar e ver passar**

Run: `pio test -e coletor -f test_target_cripto`
Expected: PASS, 5 testes.

- [ ] **Step 5: Verificação cruzada com o Python**

Imprimir no monitor serial a pubkey PEM e uma assinatura do `HASH` do teste; conferir no WSL2:

```
wsl -d Ubuntu -- bash -lc "cd /home/afonso/docker/odoo_sentinela && python3 -c \"
import base64
from cryptography.hazmat.primitives import serialization
from contrato import identidade
pem = open('/tmp/coletor.pub').read()
sig = base64.b64decode(open('/tmp/coletor.sig').read().strip())
h = '5cb25d3c4cd967bb566bce1a9d3ca5bb50ab0949048dbade5443ebf13edc29a9'
identidade.verificar_assinatura(serialization.load_pem_public_key(pem.encode()), sig, h.encode())
print('assinatura VALIDA')\""
```

Expected: imprime `assinatura VALIDA`. Se levantar `InvalidSignature`, o erro está quase sempre em assinar os bytes crus do hash em vez dos 64 caracteres ASCII.

- [ ] **Step 6: Commit**

```bash
git add src/crypto/assinador.c src/crypto/assinador.h test/test_target_cripto
git commit -m "feat: ECDSA P-256 signer with NVS-persisted device key"
```

---

### Task 8: Arquivo diário no SD com reparo de cauda

**Files:**
- Create: `src/armazenamento/arquivo.c`, `src/armazenamento/arquivo.h`
- Test: `test/test_target_arquivo/test_arquivo.c`

**Interfaces:**
- Consumes: `formato_*` (Tasks 1–3), `assinador_*` (Task 7).
- Produces:
  - `typedef struct { char coletor_id[48]; char hub_id[48]; char cliente_id[48]; char site_id[48]; char firmware[16]; char tz_offset[8]; char data_atual[11]; char hash[65]; unsigned seq; int tipo; } arquivo_t;` — `tipo`: `0` leituras, `1` alarmes.
  - `int arquivo_abrir(arquivo_t *a, const char *data_referencia);` — cria o `.parcial` com cabeçalho + `hdr_sig`, ou retoma um existente reparando a cauda.
  - `int arquivo_registrar_linha(arquivo_t *a, const char *linha_sem_sig, const char *hash_novo);` — assina `hash_novo`, grava `linha|sig\n`, `fsync`.
  - `int arquivo_selar(arquivo_t *a);` — grava rodapé e renomeia `.parcial` → `.txt`.
  - `int arquivo_reparar_cauda(const char *caminho, char hash_atual[65], unsigned *proximo_seq, unsigned *linhas_descartadas);` — recalcula o hash de cada linha; trunca a partir da primeira divergente.
  - `int armazenamento_montar_sd(void);` — monta o cartão em `/sdcard`, sem formatar em falha.
  - `int armazenamento_espaco_livre_kb(unsigned long *livre_kb, unsigned long *total_kb);`

**Divergência deliberada da referência Python:** `hub/arquivo_diario.py::reconstruir_estado` confia no conteúdo do arquivo. No FatFS, uma queda de energia durante a atualização da FAT pode deixar cauda truncada ou lixo, e confiar nela corromperia a cadeia em silêncio. Aqui a retomada **verifica cada linha**.

- [ ] **Step 1: Escrever o teste falho (roda no alvo)**

`test/test_target_arquivo/test_arquivo.c` — usa o SD já montado em `/sdcard`.

**Estes cinco testes são uma sequência deliberada sobre o mesmo arquivo**: o `remove()` do primeiro é o único reset, e cada teste depende do estado deixado pelo anterior. Rodá-los isolados ou fora de ordem falha por desenho — não é flakiness, não "consertar" tornando-os independentes (o que se quer provar aqui é justamente a continuidade da cadeia entre aberturas).

```c
#include <stdio.h>
#include <string.h>
#include <unity.h>
#include "armazenamento/arquivo.h"
#include "contrato/formato.h"
#include "crypto/assinador.h"

void setUp(void) {}
void tearDown(void) {}

static arquivo_t novo_arquivo(void) {
    arquivo_t a;
    memset(&a, 0, sizeof a);
    strcpy(a.coletor_id, "COL-TEST-01");
    strcpy(a.hub_id, "HUB-TEST-01");
    strcpy(a.cliente_id, "CLI-000123");
    strcpy(a.site_id, "SITE-0001");
    strcpy(a.firmware, "0.1.0");
    strcpy(a.tz_offset, "-03:00");
    a.tipo = 0;
    return a;
}

void test_abrir_cria_parcial_com_cabecalho_e_hdr_sig(void) {
    remove("/sdcard/2026-07-27_HUB-TEST-01-COL-TEST-01_leituras.parcial");
    arquivo_t a = novo_arquivo();
    TEST_ASSERT_EQUAL_INT(0, arquivo_abrir(&a, "2026-07-27"));
    FILE *f = fopen("/sdcard/2026-07-27_HUB-TEST-01-COL-TEST-01_leituras.parcial", "r");
    TEST_ASSERT_NOT_NULL(f);
    char buf[2048] = {0};
    fread(buf, 1, sizeof buf - 1, f);
    fclose(f);
    TEST_ASSERT_NOT_NULL(strstr(buf, "# schema_version: 3\n"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\n# hdr_sig: "));
    TEST_ASSERT_EQUAL_UINT(1, a.seq);
}

void test_registrar_linha_grava_com_assinatura(void) {
    arquivo_t a = novo_arquivo();
    arquivo_abrir(&a, "2026-07-27");
    char linha[512], hash[65];
    formato_linha_leitura(linha, sizeof linha, a.hash, a.seq,
        "2026-07-27T08:00:00-03:00", "SNR-EXP-TEMP-01", "AREA-EXPURGO",
        "temperatura", 19.8, "C", "4-20ma", "ok", 3, 0.9650, -0.1200, hash);
    TEST_ASSERT_EQUAL_INT(0, arquivo_registrar_linha(&a, linha, hash));
    TEST_ASSERT_EQUAL_UINT(2, a.seq);
    TEST_ASSERT_EQUAL_STRING(hash, a.hash);
}

void test_reabrir_retoma_a_cadeia_sem_recomecar(void) {
    arquivo_t a = novo_arquivo();
    arquivo_abrir(&a, "2026-07-27");
    char hash_antes[65];
    strcpy(hash_antes, a.hash);
    unsigned seq_antes = a.seq;

    arquivo_t b = novo_arquivo();
    arquivo_abrir(&b, "2026-07-27");
    TEST_ASSERT_EQUAL_STRING(hash_antes, b.hash);
    TEST_ASSERT_EQUAL_UINT(seq_antes, b.seq);
}

void test_cauda_corrompida_e_descartada_na_retomada(void) {
    FILE *f = fopen("/sdcard/2026-07-27_HUB-TEST-01-COL-TEST-01_leituras.parcial", "a");
    fputs("99|LIXO|SEM|HASH|VALIDO\n", f);
    fclose(f);

    char hash[65]; unsigned seq = 0, descartadas = 0;
    TEST_ASSERT_EQUAL_INT(0, arquivo_reparar_cauda(
        "/sdcard/2026-07-27_HUB-TEST-01-COL-TEST-01_leituras.parcial",
        hash, &seq, &descartadas));
    TEST_ASSERT_EQUAL_UINT(1, descartadas);

    f = fopen("/sdcard/2026-07-27_HUB-TEST-01-COL-TEST-01_leituras.parcial", "r");
    char buf[4096] = {0};
    fread(buf, 1, sizeof buf - 1, f);
    fclose(f);
    TEST_ASSERT_NULL(strstr(buf, "LIXO"));
}

void test_selar_grava_rodape_e_renomeia_para_txt(void) {
    arquivo_t a = novo_arquivo();
    arquivo_abrir(&a, "2026-07-27");
    TEST_ASSERT_EQUAL_INT(0, arquivo_selar(&a));
    TEST_ASSERT_NULL(fopen("/sdcard/2026-07-27_HUB-TEST-01-COL-TEST-01_leituras.parcial", "r"));
    FILE *f = fopen("/sdcard/2026-07-27_HUB-TEST-01-COL-TEST-01_leituras.txt", "r");
    TEST_ASSERT_NOT_NULL(f);
    char buf[4096] = {0};
    fread(buf, 1, sizeof buf - 1, f);
    fclose(f);
    TEST_ASSERT_NOT_NULL(strstr(buf, "\n# total_linhas: "));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\n# hash_final: "));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\n# assinatura: "));
}

void app_main(void) {
    // Montagem do SD conforme docs/HARDWARE.md; assinador antes dos testes.
    armazenamento_montar_sd();
    assinador_iniciar();
    UNITY_BEGIN();
    RUN_TEST(test_abrir_cria_parcial_com_cabecalho_e_hdr_sig);
    RUN_TEST(test_registrar_linha_grava_com_assinatura);
    RUN_TEST(test_reabrir_retoma_a_cadeia_sem_recomecar);
    RUN_TEST(test_cauda_corrompida_e_descartada_na_retomada);
    RUN_TEST(test_selar_grava_rodape_e_renomeia_para_txt);
    UNITY_END();
}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pio test -e coletor -f test_target_arquivo`
Expected: FAIL — `arquivo.h` não existe.

- [ ] **Step 3: Implementar `armazenamento_montar_sd` e a abertura**

Montar o SD com `esp_vfs_fat_sdmmc_mount` (ou `esp_vfs_fat_sdspi_mount`, conforme `docs/HARDWARE.md`) em `/sdcard`, `format_if_mount_failed = false` — formatar automaticamente apagaria a prova.

`arquivo_abrir`: se o `.parcial` existe, chamar `arquivo_reparar_cauda` e retomar; senão montar o cabeçalho (`formato_montar_cabecalho` com `assinador_fingerprint`), calcular `formato_hash_seed`, assinar essa seed, escrever `cabeçalho + "# hdr_sig: <b64>\n"`, `seq = 1`.

- [ ] **Step 4: Implementar `arquivo_registrar_linha` e `arquivo_selar`**

`arquivo_registrar_linha`: `assinador_assinar_hash(hash_novo, sig, ...)`, escrever `"%s|%s\n"`, `fflush` + `fsync(fileno(f))`. Manter o `FILE*` **aberto** entre gravações (não abrir/fechar por linha) e atualizar `a->hash` e `a->seq` só depois do `fsync` retornar.

`arquivo_selar`: reparar a cauda, assinar o `hash_final`, escrever `formato_rodape` (`"total_linhas"` ou `"total_eventos"` conforme `a->tipo`), fechar, `rename` de `.parcial` para `.txt`.

- [ ] **Step 5: Implementar `arquivo_reparar_cauda`**

Ler linha a linha. Linhas iniciadas por `#` que não sejam `# hdr_sig:` entram no cabeçalho canônico; `hash_seed` desse cabeçalho é o estado inicial. Para cada linha de corpo: separar os dois últimos campos (`hash` e `sig`), recalcular `SHA256(hash_anterior + resto)` e comparar com o campo `hash`. Na primeira divergência (ou linha com contagem de campos errada), truncar o arquivo naquele offset (`ftruncate`), contar as descartadas e parar. Devolver o hash e o próximo `seq`.

- [ ] **Step 6: Rodar e ver passar**

Run: `pio test -e coletor -f test_target_arquivo`
Expected: PASS, 5 testes.

- [ ] **Step 7: Commit**

```bash
git add src/armazenamento test/test_target_arquivo
git commit -m "feat: daily signed file on SD with chain resume and tail repair"
```

---

### Task 9: Leitura real do barramento RS-485

**Files:**
- Create: `src/medicao/leitor.c`, `src/medicao/leitor.h`
- Modify: `src/app/main.c`
- Modify: `docs/HARDWARE.md`

**Interfaces:**
- Consumes: `rtu_*`, `n4aib16_*` (Task 6), `escala_*`, `filtro_ewma` (Task 5).
- Produces:
  - `typedef struct { char sensor_id[48]; char area_id[48]; char tipo_medida[32]; char unidade[16]; char protocolo_origem[16]; uint8_t canal; int tem_map; double map_in[2], map_out[2]; int tem_faixa_min, tem_faixa_max; double faixa_min, faixa_max; double alpha; ewma_t ewma; int cert_ver; double cal_ganho, cal_offset; int tem_min, tem_max; double limite_min, limite_max; } canal_cfg_t;`
  - `typedef struct { double valor; const char *status; } leitura_t;`
  - `int leitor_iniciar(int uart_num, int tx, int rx, int de_re, int baud, char paridade, int stop_bits);`
  - `int leitor_ler_dispositivo(uint8_t endereco, canal_cfg_t *canais, size_t n_canais, leitura_t *saida);` — devolve `0` em sucesso; em timeout/CRC preenche todas as saídas com `status = "sensor_offline"` e devolve `-1`.

- [ ] **Step 1: Configurar a UART e o controle de direção**

Usar `uart_driver_install` + `uart_param_config` com os pinos de `docs/HARDWARE.md`. Se o transceptor exigir DE/RE por GPIO, usar `uart_set_mode(uart, UART_MODE_RS485_HALF_DUPLEX)` — o driver do IDF controla RTS automaticamente e é mais confiável que alternar GPIO à mão. Registrar em `docs/HARDWARE.md` qual dos dois a placa exige.

- [ ] **Step 2: Escrever o loop de transação com timeout e retry**

Para cada dispositivo: montar o frame com `rtu_montar_leitura(addr, 0x04, 0x0000, 16)`, esvaziar o buffer de RX antes de transmitir, transmitir, ler resposta com timeout de 500 ms, `rtu_parse_resposta`. Em falha, repetir **2 vezes**; persistindo, devolver `-1`.

- [ ] **Step 3: Ligar o pipeline de conversão**

Por canal: `bruto → n4aib16_bruto_para_ma → [escala_map se tem_map] → filtro_ewma (se alpha > 0) → escala_calibrar → escala_status`. Devolver `valor` e `status`.

- [ ] **Step 4: Testar contra o hardware real**

Ligar um N4AIB16 no barramento, endereço 1, com um sinal conhecido (fonte de corrente ou o próprio sensor). Rodar `main.c` imprimindo cada leitura no monitor.
Expected: valores estáveis e plausíveis; ao desligar o dispositivo, todas as leituras viram `sensor_offline` sem travar o loop.

Conferência cruzada com a mesma placa lida pelo Pi (opcional, se o barramento estiver acessível):
`wsl -d Ubuntu -- bash -lc "cd /home/afonso/docker/odoo_sentinela && python3 -m hub.vendor.modbus-connector.drivers.n4aib16 -p /dev/ttyUSB0 -a 1 --json"`

- [ ] **Step 5: Commit**

```bash
git add src/medicao/leitor.c src/medicao/leitor.h src/app/main.c docs/HARDWARE.md
git commit -m "feat: RS-485 Modbus reader with retry and conversion pipeline"
```

---

### Task 10: Cliente MQTT — telemetria, alarme, status e LWT

**Files:**
- Create: `src/rede/mqtt_cliente.c`, `src/rede/mqtt_cliente.h`
- Test: `test/test_target_mqtt/test_mqtt.c`

**Interfaces:**
- Consumes: nada dos módulos anteriores.
- Produces:
  - `int mqtt_iniciar(const char *uri, const char *coletor_id, const char *hub_id);` — configura o LWT retido antes de conectar.
  - `int mqtt_publicar_telemetria(const char *sensor_id, const char *timestamp, const char *tipo_medida, double valor, const char *unidade, const char *area_id, const char *status);`
  - `int mqtt_publicar_alarme(const char *sensor_id, const char *timestamp, const char *area_id, const char *tipo_medida, const char *tipo_evento, const char *tipo_violacao, double valor, int tem_min, double lmin, int tem_max, double lmax);`
  - `int mqtt_publicar_status(unsigned config_version_aplicada, unsigned long uptime_s, unsigned long sd_livre_kb, int rssi);` — retido.
  - `void mqtt_registrar_callback_config(void (*cb)(const char *payload, int len));`

Payloads copiados de `hub/publicador_mqtt.py` — as chaves são contrato porque a API e a SPA já as consomem:

- telemetria: `{"timestamp","tipo_medida","valor","unidade","area_id","status"}`
- alarme: `{"timestamp","sensor_id","area_id","tipo_medida","tipo_evento","tipo_violacao","valor","limite_min","limite_max"}` (limite ausente = `null`)
- status: `{"estado":"online","config_version_aplicada","uptime_s","sd_livre_kb","rssi"}`; LWT: `{"estado":"offline"}`

- [ ] **Step 1: Escrever o teste falho (roda no alvo, contra o Mosquitto do Pi)**

`test/test_target_mqtt/test_mqtt.c` verifica o que dá para verificar sem um assinante: que `mqtt_iniciar` conecta, que as publicações retornam um `msg_id` positivo e que o JSON montado bate byte a byte com o esperado. Extrair a montagem do payload para funções puras `mqtt_montar_telemetria(char*, size_t, ...)` e `mqtt_montar_alarme(...)` e testá-las por igualdade de string:

```c
void test_payload_de_telemetria_bate_com_o_contrato(void) {
    char buf[512];
    mqtt_montar_telemetria(buf, sizeof buf, "2026-07-27T08:00:00-03:00",
                           "temperatura", 19.8, "C", "AREA-EXPURGO", "ok");
    TEST_ASSERT_EQUAL_STRING(
        "{\"timestamp\":\"2026-07-27T08:00:00-03:00\",\"tipo_medida\":\"temperatura\","
        "\"valor\":19.8,\"unidade\":\"C\",\"area_id\":\"AREA-EXPURGO\",\"status\":\"ok\"}", buf);
}

void test_limite_ausente_vira_null_no_alarme(void) {
    char buf[512];
    mqtt_montar_alarme(buf, sizeof buf, "SNR-01", "2026-07-27T08:05:00-03:00",
                       "AREA-EXPURGO", "temperatura", "entrada_alarme", "abaixo_limite",
                       1.8, 1, 2.5, 0, 0.0);
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"limite_min\":2.5"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"limite_max\":null"));
}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pio test -e coletor -f test_target_mqtt`
Expected: FAIL — `mqtt_cliente.h` não existe.

- [ ] **Step 3: Implementar com `esp-mqtt`**

`esp_mqtt_client_config_t` com `session.last_will.topic = "sentinela/status/coletor/<coletor_id>"`, `msg = "{\"estado\":\"offline\"}"`, `qos = 1`, `retain = true`. No evento `MQTT_EVENT_CONNECTED`: assinar `sentinela/config/coletor/<coletor_id>` com QoS 1 e publicar o status retido. Publicações de telemetria e alarme com QoS 0 (o arquivo é a fonte de verdade; MQTT é conveniência). Falha de publicação **nunca** propaga erro para o loop de leitura.

- [ ] **Step 4: Rodar e ver passar; confirmar no broker**

Run: `pio test -e coletor -f test_target_mqtt`
Expected: PASS.

No WSL2, com o broker do stack de pé:
`wsl -d Ubuntu -- bash -lc "mosquitto_sub -h localhost -t 'sentinela/#' -v"`
Expected: aparecem `sentinela/telemetria/...` e o `sentinela/status/coletor/...` retido.

- [ ] **Step 5: Commit**

```bash
git add src/rede/mqtt_cliente.c src/rede/mqtt_cliente.h test/test_target_mqtt
git commit -m "feat: MQTT client for telemetry, alarms and retained status with LWT"
```

---

### Task 11: Agente de configuração

**Files:**
- Create: `src/rede/config_agente.c`, `src/rede/config_agente.h`
- Test: `test/test_config/test_config.c` (native — o parse é puro)

**Interfaces:**
- Consumes: `mqtt_registrar_callback_config` (Task 10), `canal_cfg_t` (Task 9).
- Produces:
  - `typedef struct { unsigned config_version; unsigned intervalo_leitura_s; unsigned alarme_n; double alarme_margem; char coletor_id[48]; char hub_id[48]; char cliente_id[48]; char site_id[48]; char tz_offset[8]; canal_cfg_t canais[16]; size_t n_canais; } config_t;`
  - `int config_parse(const char *json, size_t len, config_t *saida);` — `0` em sucesso, `-1` se JSON inválido ou faltar `config_version`.
  - `int config_salvar_nvs(const config_t *c);` / `int config_carregar_nvs(config_t *c);`
  - `void config_padrao_rdc15(config_t *c);` — fallback regulatório: temperatura 18–22 °C em expurgo, 20–24 °C em preparo/esterilização, pressão diferencial mínima 2,5 Pa; `intervalo_leitura_s = 60`, `alarme_n = 3`, `alarme_margem = 0.0`.

Regra: config com `config_version` menor ou igual à já aplicada é ignorada. Config que não parseia **não** substitui a vigente.

- [ ] **Step 1: Escrever o teste falho**

```c
void test_parse_de_config_minima(void) {
    const char *j = "{\"config_version\":7,\"intervalo_leitura_s\":60,\"alarme_n\":3,"
        "\"alarme_margem\":0.0,\"coletor_id\":\"COL-TEST-01\",\"hub_id\":\"HUB-TEST-01\","
        "\"cliente_id\":\"CLI-000123\",\"site_id\":\"SITE-0001\",\"timezone_offset\":\"-03:00\","
        "\"canais\":[{\"ch\":1,\"sensor_id\":\"SNR-EXP-TEMP-01\",\"area_id\":\"AREA-EXPURGO\","
        "\"tipo_medida\":\"temperatura\",\"unidade\":\"C\",\"protocolo_origem\":\"4-20ma\","
        "\"map_in\":[4,20],\"map_out\":[-50,150],\"limite_min\":18.0,\"limite_max\":22.0,"
        "\"cert_ver\":3,\"cal_ganho\":0.965,\"cal_offset\":-0.12}]}";
    config_t c;
    TEST_ASSERT_EQUAL_INT(0, config_parse(j, strlen(j), &c));
    TEST_ASSERT_EQUAL_UINT(7, c.config_version);
    TEST_ASSERT_EQUAL_UINT(1, c.n_canais);
    TEST_ASSERT_EQUAL_STRING("SNR-EXP-TEMP-01", c.canais[0].sensor_id);
    TEST_ASSERT_TRUE(c.canais[0].tem_map);
    TEST_ASSERT_DOUBLE_WITHIN(1e-9, 150.0, c.canais[0].map_out[1]);
    TEST_ASSERT_EQUAL_INT(3, c.canais[0].cert_ver);
}

void test_json_invalido_e_rejeitado(void) {
    config_t c;
    TEST_ASSERT_EQUAL_INT(-1, config_parse("{nao é json", 11, &c));
}

void test_fallback_regulatorio_tem_limiares(void) {
    config_t c;
    config_padrao_rdc15(&c);
    TEST_ASSERT_EQUAL_UINT(60, c.intervalo_leitura_s);
    TEST_ASSERT_EQUAL_UINT(3, c.alarme_n);
    TEST_ASSERT_TRUE(c.canais[0].tem_min);
    TEST_ASSERT_TRUE(c.canais[0].tem_max);
}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pio test -e native -f test_config`
Expected: FAIL — `config_agente.h` não existe.

- [ ] **Step 3: Implementar o parse**

Usar `cJSON` (componente do ESP-IDF). Para o `env:native`, vendorizar `cJSON.c`/`cJSON.h` em `src/vendor/cjson/` — é single-file e compila em qualquer lugar.

- [ ] **Step 4: Implementar persistência e aplicação**

`config_salvar_nvs` grava o JSON cru como blob (namespace `"coletor"`, chave `"config"`) junto com `config_version`. No callback do MQTT: parsear → se `version > aplicada`, salvar, aplicar e publicar o status retido com a nova `config_version_aplicada`. No boot: carregar do NVS; se não houver nada, `config_padrao_rdc15`.

- [ ] **Step 5: Rodar e ver passar**

Run: `pio test -e native -f test_config`
Expected: PASS, 3 testes.

- [ ] **Step 6: Commit**

```bash
git add src/rede/config_agente.c src/rede/config_agente.h src/vendor/cjson test/test_config
git commit -m "feat: config agent with retained MQTT config, NVS cache and regulatory fallback"
```

---

### Task 12: Servidor FTP read-only

**Files:**
- Create: `src/rede/ftpd.c`, `src/rede/ftpd.h`

**Interfaces:**
- Consumes: SD montado em `/sdcard` (Task 8).
- Produces: `int ftpd_iniciar(uint16_t porta, const char *usuario, const char *senha);`

Requisitos, todos do design:

- Comandos suportados: `USER`, `PASS`, `SYST`, `TYPE`, `PWD`, `CWD`, `PASV`, `LIST`, `NLST`, `RETR`, `SIZE`, `QUIT`.
- Comandos de escrita (`STOR`, `DELE`, `RNFR`, `RNTO`, `MKD`, `RMD`, `APPE`) respondem `550 Permission denied` — sempre, mesmo autenticado. É a garantia de que um Hub comprometido não corrompe a prova.
- Modo **passivo** apenas (`PASV`); responder `502` a `PORT`.
- **Uma sessão de cada vez**: nova conexão enquanto há sessão ativa recebe `421 Too many connections`.
- Raiz travada em `/sdcard`; qualquer caminho com `..` responde `550`.
- Enquanto um `RETR` do `.parcial` estiver em andamento, o loop de leitura **não pode** ser bloqueado — servir a partir de um handle próprio, em tarefa separada.

- [ ] **Step 1: Implementar o servidor**

Socket TCP com `lwip`, tarefa FreeRTOS dedicada, buffer de transferência de 4 KB. Autenticação simples por usuário/senha vindos da config.

- [ ] **Step 2: Testar contra um cliente FTP real**

Do WSL2, com o coletor na rede:

```
wsl -d Ubuntu -- bash -lc "python3 -c \"
from ftplib import FTP
f = FTP(); f.connect('<ip-do-coletor>', 21); f.login('coletor','<senha>')
f.set_pasv(True)
print(f.nlst())
with open('/tmp/baixado.txt','wb') as fh: f.retrbinary('RETR ' + f.nlst()[0], fh.write)
try:
    f.storbinary('STOR intruso.txt', open('/etc/hostname','rb'))
    print('FALHA DE SEGURANCA: escrita aceita')
except Exception as e:
    print('escrita recusada, ok:', e)
f.quit()\""
```

Expected: lista os arquivos, baixa um deles íntegro, e a tentativa de `STOR` é recusada.

- [ ] **Step 3: Verificar que o download não interrompe a coleta**

Com o loop de leitura rodando a cada 5 s, baixar um arquivo grande e conferir no monitor serial que nenhuma leitura foi perdida no intervalo.
Expected: sequência de `seq` contínua, sem buracos.

- [ ] **Step 4: Commit**

```bash
git add src/rede/ftpd.c src/rede/ftpd.h
git commit -m "feat: read-only passive FTP server exposing the SD card"
```

---

### Task 13: UI — bring-up do painel e dashboard

**Files:**
- Create: `src/ui/ui.c`, `src/ui/ui.h`
- Create: `src/ui/ui_dashboard.c`
- Modify: `platformio.ini` (dependência do LVGL)
- Modify: `docs/HARDWARE.md`

**Interfaces:**
- Consumes: `leitura_t` (Task 9), estado de rede/MQTT (Task 10).
- Produces:
  - `void ui_iniciar(void);` — inicializa painel RGB, touch e LVGL.
  - `void ui_atualizar_leitura(const char *sensor_id, double valor, const char *unidade, int em_alarme, int tem_min, double lmin, int tem_max, double lmax);`
  - `void ui_atualizar_status(int wifi_ok, int mqtt_ok, unsigned long sd_livre_kb, const char *hora);`

- [ ] **Step 1: Subir o painel com `esp_lcd`**

Configurar `esp_lcd_new_rgb_panel` com os pinos e timings de `docs/HARDWARE.md`, framebuffer na PSRAM, e o touch (GT911) via `esp_lcd_touch`. Critério de aceitação desta etapa: tela pintada de uma cor sólida e coordenadas de toque impressas no monitor.

- [ ] **Step 2: Ligar o LVGL**

Adicionar `lib_deps = lvgl/lvgl@^9.2.0` ao `env:coletor`, criar `lv_conf.h` com `LV_COLOR_DEPTH 16`, registrar o driver de display e de input, e rodar `lv_timer_handler` numa tarefa própria a cada 5 ms.
Expected: um `lv_label` "Sentinela" aparece centralizado.

- [ ] **Step 3: Montar o dashboard**

Grid de tiles (`lv_obj` com `lv_flex`), um por sensor da config: `sensor_id` pequeno em cima, valor grande no centro, unidade ao lado, faixa vigente embaixo. Cor de fundo do tile: normal quando dentro dos limites, alarme quando fora, cinza quando o sensor está offline.

Barra superior: ícones de WiFi e MQTT, SD livre, hora. Rodapé: `coletor_id`.

- [ ] **Step 4: Verificar com dados reais**

Rodar com o barramento ligado.
Expected: valores atualizam na cadência configurada; desligar o dispositivo Modbus deixa o tile cinza em até dois intervalos.

- [ ] **Step 5: Commit**

```bash
git add src/ui platformio.ini docs/HARDWARE.md
git commit -m "feat: RGB panel bring-up, LVGL integration and live dashboard"
```

---

### Task 14: UI — detalhe, diagnóstico, alarme e provisionamento

**Files:**
- Create: `src/ui/ui_detalhe.c`, `src/ui/ui_diag.c`, `src/ui/ui_alarme.c`, `src/ui/ui_provisionamento.c`
- Modify: `src/ui/ui.c`, `src/ui/ui.h`

**Interfaces:**
- Consumes: tudo das tasks anteriores.
- Produces:
  - `void ui_mostrar_detalhe(const char *sensor_id);`
  - `void ui_diag_atualizar(uint8_t endereco, int respondendo, unsigned erros_crc, unsigned latencia_ms);`
  - `void ui_alarme_mostrar(const char *sensor_id, double valor, const char *tipo_violacao, unsigned long segundos);`
  - `void ui_alarme_esconder(const char *sensor_id);`

- [ ] **Step 1: Tela de detalhe**

Toque num tile abre a tela: `lv_chart` do tipo linha com as últimas 60 leituras do sensor (buffer circular em RAM), linhas de limite mínimo e máximo, última atualização, e o estado do dispositivo Modbus que serve aquele canal. Botão de voltar.

- [ ] **Step 2: Tela de diagnóstico**

Tabela (`lv_table`) com uma linha por endereço do barramento: endereço, driver, respondendo, erros de CRC acumulados, latência da última transação. Abaixo, um bloco com SSID e RSSI, estado do MQTT (**distinguindo `sem rede` de `auth recusada`**, requisito do design), SD livre, nome do último arquivo selado, `config_version` aplicada e a fonte da hora (`NTP` ou `RTC` ou `Pi`).

- [ ] **Step 3: Overlay de alarme**

`lv_obj` em `LV_LAYER_TOP`, fundo vermelho translúcido, com `sensor_id`, valor, limite violado e tempo decorrido, atualizado a cada segundo. Vários sensores em alarme viram lista. Botão "Reconhecer": esconde o overlay e **publica um evento de ack por MQTT** — não apaga nada do arquivo, não altera o estado do detector.

- [ ] **Step 4: Tela de provisionamento**

Protegida por PIN de 4 dígitos (guardado no NVS, default `0000` com aviso na tela para trocar). Campos: SSID e senha do WiFi, host e porta do broker, `coletor_id`, usuário e senha do FTP. Botão "Chave pública": mostra o fingerprint em texto grande e um QR code (`lv_qrcode`) com o PEM, para o enrollment no Odoo.

Aviso obrigatório na tela: a credencial FTP configurada aqui **é sobrescrita** pela config que vier do Odoo (D6/§5.3 do design). Serve ao primeiro boot e à recuperação em campo.

- [ ] **Step 5: Verificar o fluxo completo no hardware**

Percorrer as cinco telas com o dedo, provocar um alarme real (forçar um valor fora de faixa), reconhecer, e ler o QR da chave pública com um celular.
Expected: navegação sem travar o loop de leitura; o `seq` do arquivo continua contínuo durante toda a interação.

- [ ] **Step 6: Commit**

```bash
git add src/ui
git commit -m "feat: detail, diagnostics, alarm overlay and provisioning screens"
```

---

### Task 15: Loop principal, rollover e watchdog

**Files:**
- Modify: `src/app/main.c`
- Create: `src/app/relogio.c`, `src/app/relogio.h`

**Interfaces:**
- Consumes: todos os módulos anteriores.
- Produces:
  - `int relogio_sincronizar(void);` — SNTP, com checagem de sanidade.
  - `int relogio_agora_iso(char *saida, size_t max, const char *tz_offset);`
  - `int relogio_data_hoje(char *saida, size_t max, const char *tz_offset);`

- [ ] **Step 1: Implementar o relógio com checagem de sanidade**

SNTP quando houver rede. Rejeitar como implausível qualquer horário anterior à data de build do firmware ou mais de 24 h à frente do último timestamp conhecido; nesse caso, usar `último timestamp + intervalo esperado`, marcar a anomalia no diagnóstico e publicá-la no status.

- [ ] **Step 2: Montar o loop principal**

```
boot:
  nvs_flash_init; assinador_iniciar; armazenamento_montar_sd
  config: carrega NVS -> senão config_padrao_rdc15
  ui_iniciar; wifi; mqtt_iniciar; ftpd_iniciar; relogio_sincronizar
  arquivo_abrir(leituras, hoje); arquivo_abrir(alarmes, hoje)   # repara cauda se preciso
  recuperar pendentes: todo .parcial de data anterior a hoje é selado agora

loop (a cada intervalo_leitura_s):
  para cada dispositivo:
    leitor_ler_dispositivo
    para cada canal:
      monta linha -> arquivo_registrar_linha (assina + fsync)
      mqtt_publicar_telemetria
      detector_avaliar
        se evento: linha no arquivo de alarmes + mqtt_publicar_alarme
      ui_atualizar_leitura
  se mudou o dia: arquivo_selar(ambos); arquivo_abrir(ambos, nova data)
  a cada 30 s: mqtt_publicar_status
```

- [ ] **Step 3: Ligar o watchdog**

`esp_task_wdt_init` com timeout de 30 s; registrar a tarefa do loop de leitura e a da UI; `esp_task_wdt_reset` em cada iteração. A tarefa do FTP **não** entra no watchdog (uma transferência longa é legítima).

- [ ] **Step 4: Teste de rollover acelerado**

Configurar `intervalo_leitura_s = 5` e forçar a virada de dia (ajustar o relógio para 23:59:50).
Expected: às 00:00 os dois arquivos são selados, renomeados para `.txt`, e dois novos `.parcial` aparecem com `seq` reiniciado em 1 e cadeia nova. O arquivo de alarmes é selado **mesmo com zero eventos**.

- [ ] **Step 5: Teste de queda de energia**

Com o loop rodando, cortar a alimentação no meio de uma gravação (repetir 10 vezes).
Expected: no boot seguinte, o `.parcial` é reparado (no máximo uma linha descartada, registrada no log) e a sequência continua. Nenhuma cadeia quebrada.

- [ ] **Step 6: Commit**

```bash
git add src/app
git commit -m "feat: main loop with daily rollover, clock sanity and watchdog"
```

---

### Task 16: Endurecimento — flash encryption e secure boot v2

**Files:**
- Modify: `platformio.ini`
- Create: `docs/SEGURANCA.md`

> **AVISO — operação irreversível.** Habilitar secure boot v2 e flash encryption **queima eFuses** do ESP32-S3. Não há como desfazer, e uma placa mal configurada fica inutilizável para desenvolvimento. Executar esta task **primeiro numa placa de teste sacrificial**, e só depois nas placas de produção. Não executar em nenhuma placa que ainda esteja sendo usada para desenvolver.

- [ ] **Step 1: Documentar o procedimento antes de executar**

Escrever `docs/SEGURANCA.md` com: onde fica a chave de assinatura do secure boot (fora do repositório, com backup — perdê-la impede futuras atualizações), o comando exato de geração, e o procedimento de flash de uma placa nova.

- [ ] **Step 2: Gerar a chave de assinatura do secure boot**

```
espsecure.py generate_signing_key --version 2 --scheme rsa3072 secure_boot_signing_key.pem
```

Guardar fora do repositório. Adicionar `*.pem` ao `.gitignore` e conferir que não há chave rastreada: `git ls-files | findstr .pem` deve não retornar nada.

- [ ] **Step 3: Habilitar no sdkconfig**

Em `platformio.ini`, no `env:coletor`, apontar um `sdkconfig.defaults` com:

```
CONFIG_SECURE_BOOT=y
CONFIG_SECURE_BOOT_V2_ENABLED=y
CONFIG_SECURE_BOOT_SIGNING_KEY="secure_boot_signing_key.pem"
CONFIG_SECURE_FLASH_ENC_ENABLED=y
CONFIG_SECURE_FLASH_ENCRYPTION_MODE_RELEASE=y
```

- [ ] **Step 4: Gravar na placa de teste e validar**

Run: `pio run -e coletor -t upload`
Expected: a placa sobe normalmente. Depois, confirmar que a chave privada do coletor **não** é legível por dump: `esptool.py read_flash` na região do NVS deve devolver conteúdo cifrado.

- [ ] **Step 5: Confirmar que a assinatura continua válida**

Rodar de novo a verificação cruzada da Task 7 Step 5.
Expected: `assinatura VALIDA` — o endurecimento não pode mudar a chave nem o formato.

- [ ] **Step 6: Commit**

```bash
git add platformio.ini sdkconfig.defaults docs/SEGURANCA.md .gitignore
git commit -m "chore: enable flash encryption and secure boot v2"
```

---

### Task 17: Validação ponta-a-ponta contra o validador oficial

**Files:**
- Create: `docs/VALIDACAO.md`

**Interfaces:**
- Consumes: tudo.
- Produces: evidência de que o firmware honra o contrato. Este é o critério de aceitação do projeto inteiro.

- [ ] **Step 1: Gerar um dia completo**

Rodar o coletor com `intervalo_leitura_s = 5` por pelo menos 30 minutos, provocando ao menos uma entrada e uma saída de alarme, e um corte de energia no meio. Depois, forçar a selagem (virada de dia).

- [ ] **Step 2: Baixar os arquivos pelo caminho real**

Baixar por FTP a partir do WSL2 (mesmo caminho que o Hub usa), não pelo cartão no leitor de cartão do PC — o objetivo é validar o caminho inteiro.

- [ ] **Step 3: Registrar a chave pública do coletor**

```
wsl -d Ubuntu -- bash -lc "cd /home/afonso/docker/odoo_sentinela && python3 -c \"
from ingestao.registro_coletores import registrar_coletor
registrar_coletor('ingestao/coletores_conhecidos.json','COL-TEST-01', open('/tmp/coletor.pub').read())\""
```

- [ ] **Step 4: Validar leituras e alarmes**

```
wsl -d Ubuntu -- bash -lc "cd /home/afonso/docker/odoo_sentinela && python3 -c \"
from ingestao import validador, registro_coletores
chave = registro_coletores.obter_chave_publica('ingestao/coletores_conhecidos.json','COL-TEST-01')
for caminho in ('/tmp/leituras.txt','/tmp/alarmes.txt'):
    r = validador.validar_texto(open(caminho).read(), chave)
    print(caminho, r.status_validacao, r.motivo_rejeicao, r.total_linhas)\""
```

Expected: `status_validacao` de aceitação para os dois arquivos, `motivo_rejeicao` vazio, e o total de linhas batendo com o que o firmware registrou.

Se rejeitar, ler o `motivo_rejeicao` e corrigir o **firmware** — o validador é o contrato. Os pontos de erro mais prováveis, em ordem: assinar os bytes do hash em vez dos 64 caracteres ASCII (Task 7); cabeçalho com campo fora de ordem (Task 1); `cal_ganho`/`cal_offset` sem as 4 casas (Task 2).

- [ ] **Step 5: Escrever `docs/VALIDACAO.md`**

Registrar o procedimento acima, a saída obtida e a data. É o documento que prova que o firmware está conforme, e o roteiro de regressão para versões futuras.

- [ ] **Step 6: Commit**

```bash
git add docs/VALIDACAO.md
git commit -m "docs: end-to-end validation against the official ingestion validator"
```

---

### Task 18: Rotação do SD e confirmação de download

> Pode ser executada em qualquer momento depois da Task 12. Implementa a decisão D10 do design, que nenhuma outra task cobre.

**Files:**
- Create: `src/armazenamento/rotacao.c`, `src/armazenamento/rotacao.h`
- Modify: `src/rede/mqtt_cliente.c`, `src/rede/mqtt_cliente.h`
- Test: `test/test_rotacao/test_rotacao.c` (native — a política de escolha é pura)

**Interfaces:**
- Consumes: `armazenamento_espaco_livre_kb` (Task 8), `mqtt_registrar_callback_config` (Task 10).
- Produces:
  - `int rotacao_escolher_vitima(const char **nomes, const int *baixado, size_t n, size_t *indice);` — dado o conjunto de arquivos selados e a marca de "já baixado pelo Hub", devolve `0` e o índice do **mais antigo já baixado**; `-1` se nenhum candidato existir.
  - `int rotacao_verificar(unsigned limite_percentual);` — se a ocupação passar do limite, apaga uma vítima, registra e publica o evento. Devolve o número de arquivos apagados.
  - `void mqtt_registrar_callback_baixado(void (*cb)(const char *nome_arquivo));` — assina `sentinela/coletado/{hub_id}/{coletor_id}`, onde o Hub publica o nome de cada arquivo que terminou de baixar.

Por que o tópico de confirmação existe: o FTP do coletor é **read-only** (D3), então o Hub não tem como marcar nada no cartão. Sem essa confirmação, "apagar só o que já foi baixado" seria indecidível e a rotação apagaria prova ainda não transportada.

- [ ] **Step 1: Escrever o teste falho**

`test/test_rotacao/test_rotacao.c`:

```c
#include <string.h>
#include <unity.h>
#include "armazenamento/rotacao.h"

void setUp(void) {}
void tearDown(void) {}

void test_escolhe_o_mais_antigo_ja_baixado(void) {
    const char *nomes[] = {
        "2026-07-25_HUB-A-COL-A_leituras.txt",
        "2026-07-26_HUB-A-COL-A_leituras.txt",
        "2026-07-27_HUB-A-COL-A_leituras.txt",
    };
    const int baixado[] = {0, 1, 1};
    size_t idx = 99;
    TEST_ASSERT_EQUAL_INT(0, rotacao_escolher_vitima(nomes, baixado, 3, &idx));
    TEST_ASSERT_EQUAL_UINT(1, idx);   // o de 25 não foi baixado: intocável
}

void test_sem_candidato_baixado_nao_apaga_nada(void) {
    const char *nomes[] = {"2026-07-25_HUB-A-COL-A_leituras.txt"};
    const int baixado[] = {0};
    size_t idx = 99;
    TEST_ASSERT_EQUAL_INT(-1, rotacao_escolher_vitima(nomes, baixado, 1, &idx));
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_escolhe_o_mais_antigo_ja_baixado);
    RUN_TEST(test_sem_candidato_baixado_nao_apaga_nada);
    return UNITY_END();
}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pio test -e native -f test_rotacao`
Expected: FAIL — `rotacao.h` não existe.

- [ ] **Step 3: Implementar a escolha da vítima**

Ordenar por nome (o prefixo `AAAA-MM-DD` torna a ordem lexicográfica igual à cronológica) e devolver o primeiro com `baixado != 0`. Nunca considerar `.parcial`.

- [ ] **Step 4: Implementar a marca de "baixado" e a verificação**

Manter no NVS um conjunto dos nomes confirmados (namespace `"coletor"`, chave `"baixados"`, JSON de strings). O callback do tópico `sentinela/coletado/{hub_id}/{coletor_id}` acrescenta um nome e persiste.

`rotacao_verificar(90)`: se `(total - livre) * 100 / total > 90`, escolher a vítima, apagar, remover do conjunto, registrar no log e publicar no status um campo `ultimo_descarte` com o nome e a data. Se não houver vítima, **não apagar nada** e publicar `sd_critico: true` no status — o alarme sobe, a prova fica.

- [ ] **Step 5: Rodar e ver passar**

Run: `pio test -e native -f test_rotacao`
Expected: PASS, 2 testes.

- [ ] **Step 6: Verificar no hardware**

Encher o cartão com arquivos de teste até passar de 90%, publicar a confirmação de um deles com
`wsl -d Ubuntu -- bash -lc "mosquitto_pub -h <ip-do-broker> -t 'sentinela/coletado/HUB-TEST-01/COL-TEST-01' -m '2026-07-25_HUB-TEST-01-COL-TEST-01_leituras.txt'"`
e chamar `rotacao_verificar(90)`.
Expected: só o arquivo confirmado é apagado; os não confirmados permanecem; a coleta não para em nenhum momento.

- [ ] **Step 7: Commit**

```bash
git add src/armazenamento/rotacao.c src/armazenamento/rotacao.h src/rede/mqtt_cliente.c src/rede/mqtt_cliente.h test/test_rotacao
git commit -m "feat: SD rotation limited to files confirmed downloaded by the hub"
```

---

## Trabalho correspondente no lado Python (plano separado)

Este plano cobre **só o firmware**. O lado do Hub precisa de um plano próprio, no repositório `odoo_sentinela`, cobrindo: `hub/coletores_externos.py` (varredura FTP dos N coletores, download de `.txt` e `.parcial`, expiração do parcial quando o selado chega), instanciação do `enviador_sftp` por coletor, publicação da config retida por coletor em `api/config_publisher.py`, e os campos de endereço/credencial FTP no modelo `sensor_monitor.coletor`. Ver §8 do design.

Enquanto esse plano não existir, dá para exercitar o firmware inteiro manualmente com `ftplib` e `mosquitto_pub`/`mosquitto_sub`, como as Tasks 12 e 17 fazem.
