# Hub — Fatia 1: "Hub como coletor RS-485" (leitor → arquivo assinado + MQTT)

**Data:** 2026-07-21
**Autor:** Afonso Carvalho + Claude (sessão de brainstorming)
**Fase do roadmap:** 6 (Edge — software do Hub / Raspberry Pi 3B), primeira fatia fina
**Referências:** `diretrizes_projeto.md` (§5, §6, §6.1, §7, §11), `roadmap_implementacao.md` (Fase 6), `coletor_simulado/` (contrato de formato/assinatura já congelado), projeto `modbus-connector` (lib Modbus RTU já existente no Pi)

---

## 1. Contexto e objetivo

O lado servidor da plataforma (Fases 0–4) já está avançado: módulo Odoo 18, TimescaleDB, serviço de ingestão, `coletor_simulado` (gera arquivos assinados válidos), APIs (auth/histórico/alarmes/live SSE) e o frontend SPA. O **Hub (Raspberry Pi 3B) ainda não existe no repositório**.

Esta fatia entrega o **primeiro papel do Hub: atuar como coletor direto do barramento RS-485** (diretriz §5/§6 — no caso RS-485 não há coletor físico separado, o próprio Hub lê, monta e assina o arquivo). É a fatia fina de dado real na borda: ler sensores Modbus RTU → converter para grandeza física → gravar o arquivo `.txt` diário assinado (byte-compatível com o que a `ingestao/` já valida) → publicar telemetria em tempo real num Mosquitto local.

**Realidade de hardware/servidor desta sessão (decidido):**
- Hardware presente no Pi: **apenas o adaptador USB-RS485** (`/dev/ttyUSB*`) e um **N4AIB16 real** no barramento. **Sem ATECC608**, sem LCD, sem modem 4G.
- Servidor: **só dev local**, sem Mosquitto central nem SFTPGo rodando. Logo, o Hub publica no **Mosquitto local**; bridge/SFTP/OpenVPN ficam para fatias seguintes.

### 1.1 Objetivos (o que esta fatia entrega)
- Loop de leitura Modbus RTU multi-barramento sobre a lib `modbus-connector`, começando pelo perfil **N4AIB16**.
- Conversão 4-20 mA → grandeza física (via `common/scaling` do `modbus-connector`) + filtros por canal.
- Escritor do arquivo diário no formato congelado: hash encadeado por linha, selagem diária com assinatura sobre `hash_final`.
- Assinatura via interface `Assinador` com implementação **software (EC SECP256R1)** — mesmo esquema do `coletor_simulado`.
- Publicação de cada leitura no Mosquitto local (primeira versão do contrato de tópico de telemetria).
- Recuperação no boot de arquivo de dia anterior não-selado.
- Teste de aceitação: o arquivo gerado pelo Hub **passa** no `ingestao/validador.py`.

### 1.2 Não-objetivos (fatias seguintes)
Bridge MQTT local→central, cliente SFTP Hub→servidor, cliente OpenVPN, LCD + alarme local, modem 4G + SMS, control-plane real (config descendo do Odoo via MQTT retido), arquivo de alarme orientado a evento, e assinatura por ATECC608. Todos previstos, nenhum nesta fatia.

---

## 2. Decisões desta sessão

1. **Stack Modbus:** reusar o projeto **`modbus-connector`** (pyserial-only, com driver N4AIB16 + filtros + scaling já testados), **não** `pymodbus`. Contraria a letra da diretriz §6.1, mas evita reescrever código maduro já rodando no Pi. Registrado como revisão consciente da §6.1.
2. **Consumo da lib:** **git submodule** em `hub/vendor/modbus-connector`. Empacotar com `pyproject.toml` + `pip install` fica como limpeza futura (a lib hoje roda por scripts com `sys.path` manipulado; empacotar exige restruturar). O submodule destrava já e mantém a lib rastreável/atualizável.
3. **Contrato de formato/assinatura compartilhado:** **extrair** `formato.py` + `identidade.py` de `coletor_simulado/` para um pacote novo **`contrato/`**, importado *tanto* pelo `coletor_simulado` quanto pelo `hub`. Fonte única de verdade do formato — garante byte-compatibilidade com a ingestão. (Única mexida em código existente nesta fatia.)
4. **Mapeamento sensor↔registrador:** **arquivo de config local** (YAML) no Hub — semente do que o control-plane (Odoo→MQTT) vai entregar depois.
5. **Assinatura:** **software (EC)** agora, atrás de interface `Assinador`; ATECC608 vira outra implementação sem tocar o resto.

---

## 3. Arquitetura e decomposição em módulos

Novo diretório **`hub/`** no repo `odoo_sentinela`. Unidades pequenas, cada uma com uma responsabilidade, testáveis isoladamente.

| Módulo | Responsabilidade | Depende de |
|---|---|---|
| `hub/config.py` | Carregar e **validar** o YAML de config (barramentos, dispositivos, canais→sensor, maps, filtros, intervalo, identidade). Erros de config falham cedo e claro. | PyYAML |
| `hub/leitor.py` | Loop/varredura: para cada barramento→dispositivo→canal, lê via driver do `modbus-connector`, aplica map + filtro, e produz **leituras normalizadas**. | `hub/config`, `modbus-connector` |
| `hub/arquivo_diario.py` | Escritor do `.txt` diário: append com hash encadeado, rotação por data, **selagem** (assina + rodapé), recuperação de arquivo não-selado no boot. | `contrato/formato`, `hub/assinador` |
| `hub/assinador.py` | Interface `Assinador` + `AssinadorSoftware` (chave EC). Ponto de extensão para ATECC608. | `contrato/identidade` |
| `hub/publicador_mqtt.py` | Publica cada leitura no Mosquitto local. Falha de publish **não** derruba o loop nem impede a gravação do arquivo (o arquivo é a fonte de verdade). | `paho-mqtt` |
| `hub/main.py` | Compõe tudo, roda o loop, trata sinais (SIGTERM → sela o dia corrente e encerra limpo). | todos acima |

### 3.1 Leitura normalizada (a fronteira interna principal)
O `leitor` emite dicts com exatamente os campos que a linha do arquivo e o payload MQTT precisam — desacopla o mundo Modbus (barramento/endereço/registrador/mA) do mundo de domínio (sensor/área/grandeza):

```python
{
  "timestamp": datetime,        # tz-aware, com offset local
  "sensor_id": "SNR-EXP-TEMP-01",
  "area_id": "AREA-EXPURGO",
  "tipo_medida": "temperatura",
  "valor": 19.8,                # já convertido para a grandeza física
  "unidade": "C",
  "protocolo_origem": "4-20ma",
  "status_leitura": "ok",       # ok | fora_faixa_fisica | sensor_offline | erro_leitura
}
```

### 3.2 Interface `Assinador`
```python
class Assinador(Protocol):
    def fingerprint(self) -> str: ...          # ex.: "9F:3A:...:B1"
    def assinar(self, dado: bytes) -> bytes: ...  # assinatura sobre o hash_final

class AssinadorSoftware(Assinador):
    def __init__(self, caminho_chave): ...     # carrega/gera EC SECP256R1 (contrato/identidade)
```

---

## 4. Ciclo de vida do arquivo diário

- **Append:** a cada leitura, uma linha é anexada ao arquivo do dia corrente com o hash encadeado (`contrato/formato.gerar_linha_leitura`). O estado do último hash e do `seq` fica em memória durante a execução.
- **Publicação:** independente do arquivo — cada leitura também vai pro MQTT imediatamente. Publish e append são as duas saídas paralelas de uma leitura; nenhuma bloqueia a outra.
- **Rotação/selagem:** ao virar a data local (ou em SIGTERM), o arquivo do dia é selado — calcula `hash_final`, o `Assinador` assina, escreve o rodapé (`# total_linhas / # hash_final / # assinatura`), e um novo arquivo do próximo dia começa do zero (cadeia de hash reinicia a cada dia, diretriz §7).
- **Recuperação no boot:** se existir um arquivo de um dia **passado** ainda sem rodapé (crash antes de selar), o Hub relê o corpo, reconstrói o `hash_final` e o sela antes de iniciar o loop do dia corrente. Se o arquivo não-selado for do **dia corrente**, o loop continua anexando a ele (reconstrói `seq`/hash do que já existe).
- **Localização:** `~/sentinela-hub/dados/{coletor_id}/{data_referencia}.txt` (staging local; a fatia de transporte fará o SFTP a partir daqui).

---

## 5. Esquema do arquivo de config local

`hub/config.example.yaml` (o real fica fora do git — carrega identidade/segredos):

```yaml
hub_id: HUB-0001A2F3
coletor_id: COL-RS485-BUS0        # "coletor lógico" deste barramento RS-485
firmware_version: 0.1.0
timezone_offset: "-03:00"
intervalo_leitura_s: 60            # default; 5s em teste
caminho_chave: ~/sentinela-hub/chaves/coletor.pem
caminho_dados: ~/sentinela-hub/dados
mqtt:
  host: localhost
  port: 1883
barramentos:
  - porta: /dev/ttyUSB0
    baud: 9600
    paridade: N
    stop_bits: 1
    dispositivos:
      - endereco: 1
        driver: n4aib16            # "perfil" = driver do modbus-connector
        canais:
          - ch: 1
            sensor_id: SNR-EXP-TEMP-01
            area_id: AREA-EXPURGO
            tipo_medida: temperatura
            unidade: C
            protocolo_origem: 4-20ma
            map: {in: [4, 20], out: [-50, 150]}   # mA → °C (scaling.map_range)
            filtro: {tipo: ewma, alpha: 0.3}       # opcional
```

Regras de validação (falham cedo): identificadores sem `|`/`\n`/`\r` (constraint do formato); `map.in`/`map.out` com 2 elementos; `ch` dentro do range do driver; `porta` existe (aviso, não erro fatal — pode estar desconectada).

---

## 6. Contrato de telemetria MQTT (v1 — criado nesta fatia)

Não havia contrato de tópico congelado (a Fase 0 previa, mas não foi implementado no servidor). Esta fatia estabelece a **v1**, a reconciliar quando o bridge/ingestão do servidor for construído.

- **Tópico:** `sentinela/telemetria/{hub_id}/{coletor_id}/{sensor_id}`
- **Payload (JSON):**
  ```json
  {"timestamp":"2026-07-21T00:01:00-03:00","tipo_medida":"temperatura","valor":19.8,"unidade":"C","area_id":"AREA-EXPURGO","status":"ok"}
  ```
- **QoS 0**, não-retido (telemetria é fluxo; o arquivo assinado é o registro durável).
- Mosquitto local sobe no Pi (container ou systemd — decidir na implementação; sem auth nesta fatia, só localhost).

Este contrato será documentado também num arquivo curto de contratos versionado quando a fatia de transporte entrar (fecha a pendência de "documento de contratos" da Fase 0 para o eixo de telemetria).

---

## 7. Estratégia de testes (TDD)

- **Unitários (sem hardware):** `config` (parse/validação), `arquivo_diario` (append/hash encadeado/rotação/selagem/recuperação de crash), `assinador` (assina/verifica), `leitor` (com driver Modbus **mockado**), `publicador_mqtt` (com client mockado). Estes cobrem a lógica e rodam no CI.
- **Integração no Pi (com N4AIB16 real):** smoke test lendo o barramento de verdade via USB-RS485, validando conversão mA→física e status de dispositivo offline (desconectar → `sensor_offline`).
- **Teste de aceitação (o que prova a fatia):** gerar um arquivo diário completo pelo Hub e **passá-lo pelo `ingestao/validador.py`** — precisa validar hash encadeado + assinatura sem erro. Fecha o ciclo de compatibilidade com o servidor.

---

## 8. Pendências deixadas explícitas (não bloqueiam esta fatia)

- Mecanismo exato do Mosquitto local no Pi (container vs systemd) — decidir na implementação.
- Nome/estrutura do arquivo de contratos versionado onde o tópico de telemetria será formalizado (junto da fatia de transporte).
- Intervalo de leitura por-sensor (hoje global) — vira override quando o control-plane entrar.
- `protocolo_origem` por canal: default `4-20ma` (interface nativa do sensor no N4AIB16), configurável.
