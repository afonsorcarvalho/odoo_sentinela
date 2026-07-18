# Spec técnica — Firmware do Coletor (ESP32)

> Documento de especificação para implementação. Complementa `diretrizes_projeto.md` (seções 4, 5, 7, 8, 10, 11). Escrito para ser entregue a uma sessão de implementação (Claude no WSL2) construir o firmware diretamente a partir daqui.

**Escopo deste documento**: firmware do **coletor externo WiFi/Ethernet** (ESP32-WROOM-32SE). O caso de sensores em **RS-485 não usa este firmware** — nesse caso, quem lê o barramento, monta e assina o arquivo é o próprio Hub (Raspberry Pi), não um ESP32 separado (ver `diretrizes_projeto.md`, seções 5/6). Se no futuro decidirem por um coletor físico dedicado também para RS-485, este documento serve de base, mas hoje não é o caso.

---

## 1. Papel do coletor no sistema

O coletor é a **fonte de verdade da integridade e autenticidade** dos dados de sensor (decisão da diretriz, seção 5) — é o dispositivo fisicamente ligado ao sensor, então é ele quem assina a leitura na origem. O Hub (Raspberry Pi) que o recebe **não** deve alterar, re-assinar ou consolidar o arquivo gerado aqui — só preservar e retransmitir. Essa mesma lógica se estende agora também aos **eventos de alarme** (seção 5) — o coletor não é só fonte de verdade da leitura bruta, é também fonte de verdade do fato "isso ficou fora de faixa, nesse momento".

## 2. Hardware (lista de componentes)

| Componente | Escolha recomendada | Observação |
|---|---|---|
| Módulo principal | **ESP32-WROOM-32SE** | Já vem com secure element **ATECC608A integrado** de fábrica — usado para a chave de assinatura do dispositivo. Evita chip/placa adicional. |
| Cartão SD | microSD de alta resistência a escrita (grau industrial) | Gravação contínua e frequente (ver seção 6) — cartão de consumo é ponto de falha física real. |
| Leitura 4-20mA | ADC externo dedicado (ex. **ADS1115**, I2C, 16-bit) | O ADC interno do ESP32 é conhecido por ruído/não-linearidade, especialmente com WiFi ativo — não recomendado para medição de precisão regulatória. Corrente convertida em tensão via resistor de precisão (*burden resistor*), lida pelo ADS1115. |
| Leitura I2C | Nativo do ESP32 | Mesmo barramento pode ser compartilhado com o ADS1115 (endereços I2C diferentes). |
| Leitura Serial | UART nativa do ESP32 | — |
| Conectividade WiFi | Nativa do ESP32-WROOM-32SE | — |
| Conectividade Ethernet (quando aplicável) | Módulo SPI Ethernet externo (ex. **W5500**) | ESP32-WROOM-32SE não tem PHY Ethernet nativo. |
| Relógio de tempo real (RTC) | **DS3231** (ou equivalente, I2C) | Recomendado — mantém hora precisa em boot sem rede, e serve de checagem de sanidade contra respostas NTP implausíveis. Timestamp é dado crítico para o sistema, não deveria depender só de NTP disponível a cada boot. |
| Indicação local (LED/buzzer) | **Não incluído na v1** (decidido) | Avaliação de alarme já existe no firmware (seção 5), mas não aciona indicador físico nesta versão — sinalização visual continua centralizada no LCD do Hub. Candidato a v2. |

## 3. Arquitetura de firmware (módulos)

1. **Leitor de sensores**: agenda leitura por sensor conforme intervalo configurado (padrão 1/min, configurável por sensor). Cada leitura gera uma linha candidata com timestamp do momento real da leitura (não um "tick" compartilhado).
2. **Gravador de arquivo de leituras + cadeia de hash**: monta a linha no formato definido (seção 4), grava no SD **imediatamente** (flush/fsync por linha), atualiza a cadeia de hash.
3. **Avaliador de alarme**: compara cada leitura contra o limiar vigente em cache local (seção 5.1); em transição de estado, aciona o gravador do arquivo de alarme.
4. **Gravador de arquivo de alarme + cadeia de hash** (novo, esta rodada): mesmo padrão do gravador de leituras, mas orientado a evento (seção 5).
5. **Assinador (secure element)**: ao fechar os arquivos do dia (rollover de meia-noite), calcula o hash final e assina via operação ECDSA do ATECC608A — **para os dois arquivos** (leituras e alarmes).
6. **Cliente de rede**: FTP (envio dos arquivos do dia assim que fechados/assinados) + MQTT (publicação de cada leitura e de cada transição de alarme em tempo real, e recepção de configuração de limiar — seção 5.1).
7. **Sincronização de tempo**: NTP quando há rede; RTC (DS3231) como referência entre sincronizações e checagem de sanidade.
8. **Watchdog**: reinício automático do firmware em caso de travamento.

## 4. Formato do arquivo de leituras `.txt` (definitivo — replicado da diretriz para autocontenção deste documento)

Um arquivo por coletor por dia. Texto plano delimitado por `|`. Cada arquivo é uma unidade fechada e autoválida — **cadeia de hash não atravessa dias** (começa do zero a cada arquivo).

### Cabeçalho
```
# schema_version: 1
# tipo_arquivo: leituras
# coletor_id: COL-0007A1B2
# hub_id: HUB-0001A2F3
# coletor_pubkey_fingerprint: 9F:3A:7E:...:B1
# data_referencia: 2026-07-16
# timezone_offset: -03:00
# firmware_version: 2.3.1
# dia_anterior_hash_final: 7e3b9f2a1c...   (informativo, não é dependência criptográfica)
```

### Corpo (uma linha por leitura)
```
seq|timestamp|sensor_id|area_id|tipo_medida|valor|unidade|protocolo_origem|status_leitura|hash
1|2026-07-16T00:01:00-03:00|SNR-EXP-TEMP-01|EXPURGO|temperatura|19.8|C|4-20mA|ok|3f2a91e0...
```

### Rodapé
```
# total_linhas: 17280
# hash_final: 5d9c3f8e21...
# assinatura: MEUCIQD...==
```

### Regras de implementação que estavam em aberto — resolvidas aqui:

- **Seed da cadeia de hash**: `hash_0 = SHA256(cabeçalho_canônico)` — o próprio cabeçalho entra na cadeia. Cada linha seguinte: `hash_n = SHA256(hash_(n-1) + linha_n_sem_o_campo_hash)`.
- **Escaping do delimitador `|`**: **resolvido por proibição, não por escaping**. Nenhum campo do formato é texto livre digitado por usuário — todos são identificadores/enums controlados pelo cadastro (Odoo). Regra a implementar tanto no firmware quanto como constraint no Odoo (`sensor_code`, `area_code`, `coletor_code`, `hub_code`): **proibir os caracteres `|`, `\n` e `\r` nesses identificadores na origem**.
- **Compactação**: **resolvido — não compactar em v1**. Volume pequeno o suficiente para não justificar a complexidade. Se necessário depois, compactar só **após** validação, do lado do servidor.
- **Assinatura**: cobre o `hash_final` (não cada linha individualmente) — uma operação ECDSA por dia.

## 5. Arquivo de alarme `.txt` (novo, esta rodada)

Mesmo princípio do arquivo de leituras (autocontido, cadeia de hash por dia, assinado pelo coletor), mas **orientado a evento** (transição de estado), não a amostragem — grava só quando um sensor entra ou sai de condição de alarme. Isso mantém o volume baixo (a maioria dos dias não deve ter evento nenhum) e dá ao registro de alarme a mesma força de evidência que já demos ao registro de leitura: não é algo recalculado depois a partir do bruto, é um fato assinado no momento em que aconteceu.

**Arquivo separado do de leituras** (não interleaved) — motivos: consumidores diferentes no servidor (leituras alimentam o TimescaleDB, alarmes alimentam o `alarm.event` do Odoo e notificações), cadência muito diferente (denso e periódico vs. esparso e por evento), e mantém o princípio de "uma cadeia de hash por tipo de arquivo" simples de validar independentemente.

### Cabeçalho
```
# schema_version: 1
# tipo_arquivo: alarmes
# coletor_id: COL-0007A1B2
# hub_id: HUB-0001A2F3
# coletor_pubkey_fingerprint: 9F:3A:7E:...:B1
# data_referencia: 2026-07-16
# timezone_offset: -03:00
# firmware_version: 2.3.1
```

### Corpo (uma linha por transição de estado)
```
seq|timestamp|sensor_id|area_id|tipo_medida|tipo_evento|tipo_violacao|valor|limite_min_vigente|limite_max_vigente|hash
1|2026-07-16T03:14:00-03:00|SNR-EXP-PRES-01|EXPURGO|pressao_diferencial|entrada_alarme|abaixo_limite|1.8|2.5|—|a1b2c3...
2|2026-07-16T03:22:00-03:00|SNR-EXP-PRES-01|EXPURGO|pressao_diferencial|saida_alarme|abaixo_limite|2.7|2.5|—|d4e5f6...
```
- `tipo_evento`: `entrada_alarme` ou `saida_alarme`.
- `tipo_violacao`: `acima_limite` ou `abaixo_limite`.
- `limite_min_vigente`/`limite_max_vigente`: **snapshot do limiar no momento do evento** (mesmo princípio de autocontenção dos outros campos) — se o limiar mudar depois, o registro histórico não muda de critério retroativamente. Mesma lógica já usada no modelo `alarm.event` do Odoo (`limite_configurado_snapshot`).

### Rodapé
```
# total_eventos: 2
# hash_final: ...
# assinatura: ...
```

**Regra importante**: o arquivo (cabeçalho + rodapé) é gerado e assinado **todos os dias, mesmo com `total_eventos: 0`**. Um arquivo assinado afirmando "zero eventos hoje" é, em si, uma prova positiva de monitoramento contínuo — diferente de simplesmente não existir arquivo, que não distingue "não teve alarme" de "ninguém verificou".

### 5.1 Gestão de configuração remota (control plane — ver diretriz seção 10.1)

O limiar de alarme é só um item de uma capacidade mais ampla: **o servidor (Odoo) gerencia remotamente a configuração operacional de cada coletor**. Fonte de verdade da config = servidor; fonte de verdade do dado medido = dispositivo (não se contradizem).

**Config gerenciável remotamente** (desce Odoo → Hub → coletor via MQTT): limiares de alarme, intervalo de leitura por sensor, habilitar/desabilitar sensor, e (para o Hub no papel RS-485) a config Modbus (barramentos, endereços, perfis de registrador).

**Config local-only (provisionamento, não remoto)**: credenciais de rede (WiFi/APN), `coletor_id`, chaves — semeadas localmente (o dispositivo precisa de rede para receber config, então a config da rede não pode vir pela rede).

**Mecânica (decidida)**:
- **Estado via MQTT retained**: o servidor publica a config corrente (com `config_version`) num tópico **retido** por dispositivo. Coletor offline recebe a última versão ao reconectar — nada se perde.
- **Cache local**: o coletor aplica e cacheia; não reconsulta a cada leitura.
- **Confirmação de volta**: o coletor **reporta via MQTT qual `config_version` está rodando**. O Odoo mostra o drift (desejada vs aplicada por dispositivo) — é isso que fecha o laço de gerência.
- **Fail-safe obrigatório**: se nunca recebeu config, usa os **padrões regulatórios hardcoded** (RDC 15, diretriz seção 3) — nunca opera sem limiar definido.
- **Sem assinatura na config na v1 (decidido)**: confia-se na segurança do canal (OpenVPN Hub↔servidor; rede local ESP32↔Hub). Candidato a endurecimento em v2 (servidor assina, dispositivo verifica) — ver diretriz seção 10.1.

### 5.1.1 Comandos remotos (decidido — v1)

Além de config declarativa, o dispositivo aceita **ações imperativas** do servidor: **reboot, force-sync (reenviar arquivo/dia), pedir diagnóstico/status**.

- Vão por tópico MQTT **não-retido** (comando é evento único, não estado) — crucial: um tópico retido faria a reconexão re-executar um comando velho.
- Cada comando carrega **id único**; o dispositivo **confirma (ack)** e **de-duplica** por id — reconexão ou reentrega não re-executa.
- Mesma postura de segurança da config (canal-confiável na v1).

### 5.2 Publicação em tempo real

Cada transição de estado também é publicada via MQTT no broker local do Hub, no momento em que acontece (mesmo padrão do arquivo de leituras: MQTT é o canal de baixa latência/melhor esforço, o arquivo assinado é o registro definitivo).

**Considerado e descartado para v1**: reafirmação periódica ("heartbeat") enquanto o sensor permanece em alarme (ex. uma linha extra a cada N minutos provando que o alarme continuou sendo monitorado). Não é necessário — o intervalo entre `entrada_alarme` e `saida_alarme` já prova a duração sem ambiguidade. Fica como possível refinamento de v2 se a necessidade de auditoria pedir prova de monitoramento contínuo durante o alarme, não só início/fim.

## 6. Fluxo operacional

1. **Boot**: sincroniza hora (NTP se rede disponível; senão usa RTC). Carrega configuração (sensores, intervalo, credenciais do Hub, cache de limiares — ou fallback regulatório se não houver cache). Abre (ou cria) os arquivos do dia corrente (leituras e alarme) — se já existem abertos (reinício no meio do dia), retoma a cadeia de hash a partir da última linha gravada em cada um.
2. **Loop de leitura**: para cada sensor, no intervalo configurado, lê o valor, grava a linha no arquivo de leituras (flush imediato), publica via MQTT. Em seguida, avalia contra o limiar em cache — se houver transição de estado, grava a linha correspondente no arquivo de alarme (flush imediato) e publica a transição via MQTT.
3. **Rollover de meia-noite**: fecha **os dois arquivos** do dia (leituras e alarme, este último mesmo se vazio), calcula `hash_final` de cada um, assina os dois com o secure element, grava os rodapés, inicia os arquivos do dia seguinte.
4. **Envio dos arquivos fechados**: dispara envio via FTP (leituras e alarme) para o Hub assim que fechados/assinados. Retry com backoff em caso de falha. Não há necessidade de confirmação síncrona do Hub — a assinatura já garante integridade independente de quem lê depois.

## 7. Resiliência e tratamento de falhas

- **Perda de conectividade** (WiFi/Ethernet cai): leitura, avaliação de alarme e gravação local continuam normalmente — só a publicação MQTT e o envio FTP ficam pendentes. Retry automático quando a rede voltar.
- **Perda de energia**: gravação com flush por linha (em ambos os arquivos) minimiza a janela de perda à última operação em andamento no momento da queda.
- **SD cheio ou com falha**: deve gerar um evento de erro visível — não deve travar o firmware nem perder leituras/alarmes silenciosamente.
- **Relógio implausível**: se o RTC ou NTP retornar horário inconsistente, registrar como anomalia e usar o último timestamp conhecido + intervalo esperado como fallback.
- **Cache de limiar desatualizado/ausente**: usar fallback regulatório (seção 5.1) — nunca avaliar alarme sem limiar definido.

## 8. Provisionamento e identidade do dispositivo

Cada coletor precisa, antes de entrar em operação:
1. Ter seu **`coletor_id`** definido (deve corresponder ao `coletor_code` já cadastrado no Odoo).
2. Ter a **chave pública do secure element (ATECC608A)** extraída e registrada no Odoo (`pubkey_fingerprint`) — processo de fábrica/instalação, fora do escopo deste firmware, mas o firmware deve expor um modo/comando de "ler chave pública" para esse processo.
3. Receber a configuração de rede e o endereço do Hub — mecanismo exato delegado à implementação (seção 11).

## 9. Configuração (o que deve ser ajustável por dispositivo)

- Intervalo de leitura por sensor (padrão 1 minuto).
- Endereço/credenciais do Hub (FTP e broker MQTT local).
- `timezone_offset`.
- Lista de sensores conectados (mapeamento pino/endereço I2C/canal ADC → `sensor_id`).
- Limiares padrão de fallback (regulatórios, hardcoded por vertical — seção 5.1).
- Nível de log/diagnóstico.

## 10. Frameworks e bibliotecas recomendadas

- **ESP-IDF** (framework oficial da Espressif) como base, não Arduino — suporte nativo de primeira classe para o secure element do ESP32-WROOM-32SE.
- Cliente FTP: biblioteca leve compatível com ESP-IDF — avaliar na implementação.
- Cliente MQTT: `esp-mqtt` (componente nativo do ESP-IDF).
- SHA-256: `mbedtls` (já incluso no ESP-IDF).

## 11. Pontos delegados à sessão de implementação

Decisões de baixo nível que não mudam a arquitetura definida aqui — não precisam de mais discussão antes de codificar:

1. **Mecanismo de provisionamento** de rede/`coletor_id` (portal cativo, cabo serial na fábrica, app de configuração). Restrição a manter: `coletor_id` precisa corresponder ao `coletor_code` já cadastrado no Odoo.
2. **OTA (atualização de firmware remota)** — decidir se entra em v1, e mecanismo (ESP-IDF suporta OTA via partições A/B nativamente).
3. **Biblioteca de cliente FTP específica** a adotar no ESP-IDF.
4. **Retry/backoff exato** para FTP e MQTT, e quanto de armazenamento local reservar para fila de envio pendente.
5. **Tópico e formato exato da mensagem MQTT** de sincronização de limiar (seção 5.1) — estrutura de payload, versionamento de configuração.
