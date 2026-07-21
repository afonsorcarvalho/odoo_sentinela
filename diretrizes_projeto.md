# Plataforma de Monitoramento de Sensores em Nuvem — Diretrizes do Projeto

> Documento de consolidação das discussões iniciais de arquitetura e produto. Reflete decisões tomadas até aqui e aponta os pontos ainda em aberto. Deve ser tratado como vivo — atualizar conforme o projeto avança.

**Data:** 16/07/2026
**Participantes:** Afonso Carvalho + Claude (sessão de brainstorming técnico)

---

## 1. Posicionamento do produto

Decisão: o produto é uma **plataforma genérica de monitoramento de sensores industriais em nuvem**, não um software vertical fechado. A **CME hospitalar é o primeiro caso de uso / cliente-alvo**, usado como referência de design e primeiro mercado a atacar — mas a arquitetura (hub multiprotocolo, backend, modelo de dados) deve ser pensada para se estender a outros ambientes industriais no futuro (câmaras frias, plantas fabris, etc.), não travada em CME.

Implicação prática: o modelo de dados (sensores, salas/áreas, limiares de alarme, tipos de medição) deve ser genérico o suficiente para não exigir refatoração ao entrar em um vertical novo — CME é o primeiro conjunto de regras de negócio (RDC 15) aplicado sobre uma plataforma neutra.

## 2. Estado da arte (resumo da pesquisa)

**CME hospitalar — soluções brasileiras**: [CMEXX](https://cmexx.com.br/), [CME Cloud](https://cmecloud.com.br/), [Stericontrol](https://www.stericontrol.com/), [Hosplog](https://hosplog.com.br/solucoes/central-material-esterilizado/). Todas focadas em **rastreabilidade de instrumental** (Datamatrix/RFID, conformidade RDC 15/RE 2606) — nenhuma encontrada oferece monitoramento contínuo de sensores físicos (temperatura/umidade/pressão) em tempo real com dashboard em nuvem.

**CME — soluções internacionais**: [CensiTrac (Censis)](https://censis.com/solutions/censitrac/), Getinge [T-DOC](https://www.getinge.com/int/products/t-doc-select/), Steris [SPM](https://www.steris.com/healthcare/products/spm). Cloud-based, mas focadas em gestão de workflow/instrumental e integração com esterilizadoras de fabricantes específicos — não são hubs agnósticos de protocolo.

**Plataformas IoT industriais genéricas** (referência de arquitetura): ThingsBoard (open-source, self-hosted, forte em Modbus/OPC-UA/MQTT), Ubidots e Datacake (cloud gerenciado, MQTT). Boa referência técnica, mas nenhuma verticalizada para compliance regulatório de saúde nem orientada a upload de arquivo.

**Conclusão**: existe um gap real de mercado — monitoramento de sensor físico em tempo real, com hub agnóstico de protocolo, verticalizável por compliance (começando por CME/RDC 15), não tem concorrente direto identificado.

## 3. Caso de uso inicial: CME hospitalar (RDC 15)

Parâmetros regulatórios confirmados na Resolução RDC nº 15/2012 (Anvisa):

| Área | Temperatura | Pressão diferencial | Artigo |
|---|---|---|---|
| Expurgo (Classe II) | 18°C – 22°C | **Negativa**, mín. 2,5 Pa | Art. 52 |
| Preparo / Esterilização | 20°C – 24°C | **Positiva**, mín. 2,5 Pa | Art. 54 |
| Desinfecção química | — | Negativa | Art. 56 |

- **Retenção mínima de registros: 5 anos** (Art. 26 §1º), para fins de inspeção/auditoria.
- A norma **não define frequência obrigatória de registro** — granularidade (ex.: leitura por minuto) é decisão de produto, não exigência legal.
- Áreas monitoradas: expurgo, preparo, esterilização, arsenal.
- Sensores relevantes: temperatura, umidade relativa, pressão diferencial de ar entre ambientes.

## 4. Arquitetura geral (revisada — duas camadas de borda, com o Hub em papel duplo)

**Revisão importante**: a arquitetura não é mais Sensor → Hub → Servidor. Existe uma camada intermediária de **coletores** entre o sensor e o Hub — mas o "coletor" pode ser um dispositivo físico separado (ESP32, para WiFi/Ethernet) ou o **próprio Hub agindo como coletor** (para RS-485, onde não há dispositivo separado com capacidade de assinar). Um Hub pode atender **N coletores externos**, variável por instalação, além de eventualmente coletar diretamente via seu próprio barramento RS-485.

```
[Sensor físico] --[Serial / I2C / 4-20mA]--> [COLETOR EXTERNO: ESP32-WROOM-32SE, WiFi/Ethernet]
                                                    │
                                    grava .txt local (SD), assina digitalmente
                                    (fonte de verdade da integridade do dado)
                                                    │
                                    FTP (arquivo assinado) + MQTT (tempo real)
                                                    │
                                                    ▼
[Sensor físico] --[RS-485]---------------->  [HUB: Raspberry Pi]
                                   - para coletores externos: preserva arquivos intactos,
                                     recebe MQTT direto no broker local
                                   - para RS-485: script próprio lê o barramento, monta
                                     e ASSINA o arquivo (Hub = coletor nesse caso, com
                                     seu próprio secure element) e publica no broker local
                                   - roda broker MQTT local (Mosquitto)
                                   - LCD + avaliação de alarme (alimentado pelo MQTT local)
                                   - bridge do broker local → broker do servidor
                                                     │
                                              [OpenVPN — túnel Hub↔Servidor]
                                                     │
                        ┌────────────────────────────┼────────────────────────────┐
                        ▼                                                          ▼
              [Broker MQTT central]                                    [Serviço de ingestão de arquivo]
              (não exposto publicamente,                                (recebe arquivo do coletor via Hub,
               só acessível via VPN)                                     valida hash + assinatura do COLETOR)
                        │                                                          │
                        └────────────────────────────┬─────────────────────────────┘
                                                       ▼
                              ┌───────────────────────┐      ┌──────────────────────────┐
                              │  TimescaleDB (dados     │◄────►│  Odoo (cadastro, empresas,│
                              │  temporais, self-hosted,│      │  sites, hubs, coletores,  │
                              │  multi-tenant)          │      │  sensores, alarmes)       │
                              └───────────────────────┘      └──────────────────────────┘
                                                       │
                                                       ▼
                                          [Frontend — a definir em rodada futura]
```

## 5. Coletor (ESP32) — fonte de verdade da integridade

**Decisão (nova, esta rodada)**: o **coletor, não o Hub, é a fonte de toda a verdade criptográfica** dos dados de sensor. É ele quem está fisicamente ligado ao sensor, então é ele quem deve assinar a leitura na origem — preservando a cadeia de custódia desde o ponto real de medição, não a partir de um intermediário.

- **Hardware recomendado**: **ESP32-WROOM-32SE**, variante do módulo ESP32 que já vem com o secure element **ATECC608A integrado de fábrica** — resolve a necessidade de identidade/assinatura por dispositivo sem chip adicional nem placa extra.
- Lê sensores via **Serial, I2C ou 4-20mA**.
- Conecta ao Hub via **RS-485, WiFi ou Ethernet** (varia por instalação/coletor).
- Grava localmente (SD card) o arquivo `.txt` do dia, com hash encadeado interno (escopo por arquivo, sem encadear entre dias — ver seção 7) e **assinatura digital própria** (chave do ATECC608A) ao fechar o arquivo.
- Repassa dados ao Hub por dois canais complementares:
  - **Arquivo assinado, via FTP** (só para coletores WiFi/Ethernet — FTP exige TCP/IP). Como o arquivo já sai assinado na origem, o canal de transporte não precisa garantir integridade por conta própria — isso já está resolvido antes de sair do coletor. É por isso que FTP é aceitável aqui (rede local, dado já protegido), diferente do trecho Hub→Servidor (rede aberta), onde FTP foi descartado.
  - **Leituras em tempo real via MQTT**, publicando direto no **broker MQTT local do Hub** (não no broker do servidor).
- **Revisão (esta rodada) — caso RS-485**: sensores/dispositivos em barramento RS-485 não têm capacidade própria de montar e assinar arquivo (não são um ESP32 com SD e secure element). Para esses, **não existe um coletor separado gerando o arquivo** — o próprio **Hub roda um script que lê o barramento RS-485 diretamente, monta cada linha do arquivo `.txt` e o assina**. Ou seja, nesse cenário específico, **o Hub assume o papel de coletor**. Isso resolve o ponto que estava em aberto sobre "ponte RS-485→MQTT": não é uma ponte a partir de um coletor externo, é o próprio script do Hub que, ao montar cada linha, publica-a simultaneamente no broker MQTT local — mesma lógica que um coletor ESP32 faria internamente, só que rodando no Hub. Consequência de hardware: **o Hub também precisa de um secure element** (mesma recomendação de antes, ATECC608 via I2C) — mas agora com justificativa específica: só para assinar os arquivos que ele mesmo gera a partir do barramento RS-485, não para os arquivos que recebe prontos e assinados dos coletores WiFi/Ethernet (esses continuam intocados, ver seção 6).

## 6. Hub (Raspberry Pi) — agregação, transporte, e coletor direto para RS-485

O Hub tem **dois papéis distintos**, dependendo da origem do dado:
- Para coletores **WiFi/Ethernet (ESP32)**: papel passivo — **não assina**, apenas agrega, preserva e retransmite os arquivos já assinados na origem.
- Para sensores/dispositivos em **RS-485**: papel ativo — **o próprio Hub é o coletor** (ver seção 5), lê o barramento diretamente, monta e assina o arquivo `.txt`.

Isso significa que **o Hub precisa de secure element** (revisão desta rodada — a recomendação de removê-lo foi parcial demais): ATECC608 via I2C, necessário especificamente para a função de coletor-embutido no caso RS-485. Não é usado para assinar/re-assinar o que já vem assinado dos coletores WiFi/Ethernet.

**Hardware: Raspberry Pi 3B, placa completa (decidido)**. Implicações específicas dessa escolha:
- **Conflito de UART com o Bluetooth onboard**: no Pi 3B, a UART de hardware boa (PL011, clock próprio e estável) fica reservada por padrão para o Bluetooth interno — nos pinos GPIO só fica exposta a mini-UART, cujo baud rate depende do clock da CPU e é instável para serial confiável. **Passo obrigatório de setup**: desabilitar o Bluetooth onboard (`dtoverlay=disable-bt` no `config.txt`, mais desabilitar os serviços `hciuart`/`bluetooth`) para liberar a PL011 para a HAT de RS-485 — sem isso, a leitura do barramento fica sujeita a erros intermitentes de baud rate.
- **Sem eMMC**: por ser placa completa (não Compute Module), o armazenamento depende inteiramente do cartão microSD — reforça a importância do SD de grau industrial (seção 6) já que não há alternativa mais robusta disponível nessa escolha.
- **Robustez mecânica fica por conta do gabinete**: sem carrier board própria, a resiliência física em campo (vibração, poeira, tensão nos conectores das HATs empilhadas — RS-485 + secure element via I2C) depende do desenho do gabinete/fixação em trilho DIN — vira item de projeto mecânico, não só de firmware.
- **Performance**: adequada para a carga prevista (Mosquitto local, cliente OpenVPN, script de leitura RS-485, cliente SFTP, driver do LCD) — volume de dados é pequeno o suficiente para não pressionar os 1GB de RAM/CPU quad-core do 3B.
- HAT com transceptor RS-485 (ex. MAX485) necessária para o barramento onde o Hub atua como coletor (seção 5).
- **Modem 4G (decidido nesta rodada)**: modem celular (USB dongle ou HAT) com **suporte a antena externa** e capacidade de **SMS**, mais SIM de plano M2M/IoT (tráfego pequeno, bem abaixo de 1GB/mês por Hub). Serve a dois propósitos unificados: link de internet do Hub e canal de SMS de alarme crítico (ver seção 10).

Responsabilidades:
- **Preserva os arquivos recebidos de coletores WiFi/Ethernet intactos** (decidido) — não regrava nem consolida. Atua como repositório redundante local + retransmissor para esses.
- **Para RS-485: gera e assina seus próprios arquivos** (um por "coletor lógico" no barramento, ver seção 7) via script próprio de leitura do barramento.
- **Roda um broker MQTT local (Mosquitto)** — coletores WiFi/Ethernet publicam diretamente nele; para RS-485, o próprio script de leitura do Hub publica cada linha assim que a monta (mesma lógica interna de um coletor, só que executando no Hub).
- Esse broker local faz **bridge** (recurso nativo do Mosquitto) para o broker MQTT central do servidor.
- **LCD e avaliação de alarme locais**, alimentados pelo fluxo MQTT em tempo real (de coletores externos e do próprio processamento RS-485 interno). Continua funcionando mesmo se o link com o servidor cair.
- **Cartão SD de grau industrial** recomendado, dado o volume de escrita contínua.
- Sincroniza com o servidor via **OpenVPN** (decidido) — túnel autenticado/criptografado, dentro do qual trafegam tanto o transporte do arquivo quanto o bridge MQTT.
- **Conectividade de internet (decidido nesta rodada) — configurável por site**: cada Hub pode operar com **4G como link primário** (independe da rede do hospital — só precisa de energia e sinal) **ou com cabeado primário + 4G como failover** (mais confiável, economiza dados móveis, mas exige negociação com o TI do cliente). A escolha é feita no survey de instalação de cada unidade; o Hub precisa suportar os dois modos. **Encaixe com a arquitetura**: redes 4G usam CGNAT (sem IP público de entrada), mas isso é irrelevante aqui porque é o Hub que **inicia** o túnel OpenVPN de saída, e tudo trafega dentro dele — o desenho já escolhido faz o 4G funcionar sem gambiarra. **Risco de campo a tratar no survey**: CME costuma ficar em área interna do hospital (subsolo/sem janela), onde o sinal celular é fraco — checar cobertura antes de prometer 4G, e prever antena externa.
- **Identidade de rede**: certificado OpenVPN padrão, separado da chave do secure element (que serve só para assinar os arquivos RS-485 que o próprio Hub gera).
- Transporta os arquivos assinados (dos coletores WiFi/Ethernet e os que ele mesmo gerou via RS-485) para o servidor via **SFTP/SFTPGo, restrito à interface da VPN** (decidido, ver seção 8).

### 6.1 Leitura Modbus RTU no barramento RS-485 (decidido nesta rodada)

O protocolo de aplicação sobre RS-485 é **Modbus RTU** (padrão da esmagadora maioria dos sensores industriais). Modelo mestre-escravo: **o Hub é o mestre**, cada sensor/transdutor é um escravo com endereço único (1–247); o Hub varre os escravos sequencialmente e lê os registradores. Biblioteca: **pymodbus** (Python, no script do Hub).

- **Timing folgado**: um ciclo completo de varredura de dezenas de dispositivos leva 1–2s a 9600 baud — trivial frente ao intervalo de 1 leitura/min. Sem risco de gargalo.
- **Mapa de registradores como DADO, não hardcoded — via catálogo de perfis de dispositivo (decidido)**: cada modelo de transdutor tem um "perfil Modbus" (mapa completo: função 0x03/0x04, endereço do registrador, 16/32 bits, ordem de bytes/words, escala, offset, unidade). Cada sensor instalado referencia um perfil + seu endereço de escravo. Adicionar um fabricante novo = criar um perfil, sem mexer em código. Modelagem detalhada em `odoo_modelo_dados_spec.md`.
- **Divisão da config**: **por barramento** (baud/paridade/stop bits — todos os dispositivos do mesmo fio compartilham) vs. **por dispositivo** (endereço de escravo + perfil).
- **Multi-bus desde a v1 (decidido)**: o Hub suporta vários barramentos RS-485. O Pi 3B tem só uma UART boa (PL011); barramentos adicionais vêm de **adaptadores USB-RS485** (cada um = uma porta serial). Necessário para sites com dispositivos de parâmetros seriais incompatíveis ou muitos dispositivos.
- **Falha em duas camadas**: o Modbus já traz **CRC16** contra ruído elétrico de frame (distinto da nossa cadeia de hash, que é contra adulteração). Dispositivo que não responde → retry; persistindo → `status_leitura = sensor_offline` no arquivo.
- **Instalação física** (guia de instalação): terminação de 120Ω nas duas pontas do barramento, polarização, e mesmos parâmetros seriais em todos os dispositivos do mesmo fio.

## 7. Formato do arquivo .txt (revisado — unidade é por coletor, não por Hub)

**Revisão importante**: como o coletor é quem assina, a unidade de arquivo passa a ser **um arquivo por coletor por dia** (não mais por Hub). O Hub armazena e retransmite N desses arquivos por dia, um por coletor sob sua responsabilidade.

Texto plano delimitado por `|`, com cabeçalho e rodapé de metadados. Formato longo (uma linha por leitura de sensor), alinhado ao modelo de hypertable do TimescaleDB.

**Cabeçalho**:
```
# schema_version: 1
# coletor_id: COL-0007A1B2
# hub_id: HUB-0001A2F3
# coletor_pubkey_fingerprint: 9F:3A:7E:...:B1
# data_referencia: 2026-07-16
# timezone_offset: -03:00
# firmware_version: 2.3.1
# dia_anterior_hash_final: 7e3b9f2a1c...  (informativo, não é dependência criptográfica)
```
`hub_id` identifica sob qual Hub o coletor operava naquele dia — é informativo/contextual (o coletor pode, em teoria, ser realocado entre hubs; a leitura em si já é autocontida via `area_id`, ver abaixo).

**Caso RS-485 (revisão desta rodada)**: quando o próprio Hub atua como coletor (seção 5/6), ele gera esse mesmo formato de arquivo, com `coletor_id` identificando o "coletor lógico" daquele barramento RS-485 (não um dispositivo físico separado) e assinatura feita com a chave do secure element do próprio Hub. O formato do arquivo, o esquema de hash e a lógica de assinatura são idênticos ao caso de coletor físico — só muda quem gera.

Cada arquivo diário é uma **unidade fechada e autoválida** — cadeia de hash interna começa do zero a cada dia (não atravessa dias), pelo mesmo motivo de robustez já discutido: um cartão SD com defeito não pode invalidar criptograficamente todo o histórico posterior.

**Corpo** (uma linha por leitura):
```
seq|timestamp|sensor_id|area_id|tipo_medida|valor|unidade|protocolo_origem|status_leitura|hash
1|2026-07-16T00:01:00-03:00|SNR-EXP-TEMP-01|EXPURGO|temperatura|19.8|C|4-20mA|ok|3f2a91e0...
2|2026-07-16T00:01:00-03:00|SNR-EXP-PRES-01|EXPURGO|pressao_diferencial|-3.1|Pa|RS485|ok|8b70e245...
```
- `area_id` gravado em cada linha: leitura autocontida, não depende de lookup no cadastro atual do Odoo.
- `protocolo_origem`: rastreabilidade de proveniência (4-20mA, RS-485, I2C).
- `status_leitura`: qualidade do dado (`ok`, `fora_faixa_fisica`, `sensor_offline`, `erro_leitura`).
- `seq`: detecção simples de linhas removidas, complementar ao hash encadeado.
- `tipo_medida`: mantém o schema genérico para outros verticais industriais futuros.

**Rodapé**:
```
# total_linhas: 17280
# hash_final: 5d9c3f8e21...
# assinatura: MEUCIQD...==   (chave do coletor, ATECC608A)
```
Assinatura aplicada uma única vez por dia sobre o `hash_final` — sela o arquivo inteiro com uma operação criptográfica só, mais barata que assinar linha a linha.

**Ainda em aberto**: regra de escaping do delimitador `|`; formato de compactação antes do envio.

## 8. Ingestão e transporte

**Coletor → Hub** (decidido):
- Coletores WiFi/Ethernet: arquivo assinado via **FTP** (aceitável aqui porque a integridade já vem garantida pela assinatura do coletor, e o tráfego fica na rede local) + leituras em tempo real via **MQTT** para o broker local do Hub.
- Coletores RS-485: **sem coletor externo** — o próprio Hub lê o barramento, monta e assina o arquivo, e publica direto no broker MQTT local (ver seções 5/6).

**Hub → Servidor (decidido nesta rodada)**:
- Túnel **OpenVPN** entre Hub e servidor. **Atualização (implementação, 21/07/2026):** o cliente OpenVPN **já está pronto e provisionado** — o projeto `openvpn-config-updater` (no Raspberry) mantém o `.ovpn` fresco (servidor oferece via FTP, com rollback). O Hub já é peer da VPN (`tun0`, ex. `10.8.0.19`); o **servidor de produção é o VPS `191.252.113.190` / `sistema.fitadigital.com.br`, alcançável em `10.8.0.1` pela VPN**. Logo, a "fatia OpenVPN" **não constrói PKI nem cliente** — reduz-se a bindar os serviços do servidor (SFTPGo, Mosquitto central) na interface da VPN e apontar o Hub para `10.8.0.1`. **Chave do SFTP não reusa o cert do OpenVPN** (formatos/PKI distintos, rotação acoplada); como o SFTP roda dentro do túnel, o cert da VPN já é a autenticação de rede e a chave SSH por-hub serve só ao isolamento de pasta no SFTPGo.
- **Transporte do arquivo: SFTP via SFTPGo (self-hosted)**, escutando **apenas na interface da VPN** (nunca exposto publicamente) — reavaliação em relação à rodada anterior: como o Raspberry Pi é um Linux completo (sem a limitação de processamento do ESP32) e a VPN já resolve autenticação/criptografia de rede, o ganho do mTLS na camada de aplicação deixou de compensar o esforço de construir um endpoint HTTPS próprio. SFTPGo dá isolamento por Hub (pasta própria) sem exigir gestão manual de `authorized_keys` para 50+ hubs.
- **Confirmação de validação via MQTT**, não via resposta síncrona HTTP: o serviço de ingestão publica o resultado (aceito/rejeitado, com motivo) de volta no broker, que chega ao Hub pelo mesmo bridge já existente — fecha o gap de feedback que motivava a opção HTTPS, sem precisar construir uma API nova.
- Bridge do broker MQTT local do Hub para o broker MQTT central — **broker central não fica exposto publicamente**, só acessível via a malha OpenVPN.
- Serviço de ingestão: recebe o arquivo (do coletor externo, preservado intacto, ou gerado pelo próprio Hub via RS-485), valida hash encadeado + assinatura (do coletor ou do Hub, conforme a origem), grava em lote (`COPY`) no TimescaleDB, avalia alarmes contra os limiares vigentes, dispara evento no Odoo quando aplicável.
- Storage do servidor deve ser imutável (WORM / object lock).

## 9. Backend

- **Odoo**: cadastro (empresas/clientes, usuários, sites, hubs, **coletores**, sensores, salas/áreas, tipos de alarme), workflow de ocorrências/manutenção. **Correção nesta rodada**: multi-tenancy **não** usa `res.company` (isso é para filiais/entidades legais internas) — cliente externo é `res.partner`, isolamento via `ir.rule` na cadeia até `site_id.partner_id`. **Modelo de dados completo especificado em `odoo_modelo_dados_spec.md`.**
- **TimescaleDB**: dados temporais (leituras de sensores, agregados, eventos de alarme). Escolhido sobre InfluxDB/QuestDB/TDengine/VictoriaMetrics por: SQL nativo (JOIN direto com metadados do Odoo), *continuous aggregates* para downsampling, compressão (~95-98%) para retenção longa a custo baixo.
- **Multi-tenancy desde o início** (escala alvo: SaaS com 50+ unidades de CME nos primeiros 12 meses): particionamento por tempo e espaço (`company_id`/`site_id`) no hypertable.
- **Retenção**: ver seção 9.3 (decidida nesta rodada).

### 9.3 Retenção de dados (decidido nesta rodada)

**Virada conceitual — duas classes de dado com lógicas diferentes**: o **arquivo assinado** (object storage) é o artefato legal e contém todas as leituras cruas; as **linhas cruas no Timescale** são uma *cópia consultável* do que já está durável e assinado. Logo, não é preciso manter a leitura-por-minuto no Timescale para sempre — o arquivo assinado é o registro cru autoritativo, e o Timescale é conveniência de consulta.

**Modelo em camadas (decidido)**:
- **Arquivos assinados (object storage)**: retenção legal completa, com **object-lock garantindo o piso de 5 anos** da RDC 15 (Art. 26 §1º); ciclo de vida move os "frios" para tier de arquivo barato (tipo Glacier) após ~1-2 anos.
- **Agregados contínuos no Timescale** (mín/máx/média por hora e dia): minúsculos, mantidos pela **retenção inteira** — alimentam relatórios de conformidade e histórico longo.
- **Linhas cruas no Timescale**: só numa **janela quente** (recomendação: 12-24 meses). Depois, dropa o cru mantendo os agregados; resolução total de um dia antigo é **re-hidratável do arquivo assinado** se necessário (raro, ex. disputa de auditoria).

**Piso legal vs teto (decidido)**: os 5 anos são o **piso** (garantido pelo object-lock, inegociável). A política *pós-5-anos* é **configurável por contrato/cliente** (alguns mantêm indefinidamente, outros expurgam) — **com constraint de que nenhuma configuração pode ir abaixo do piso de 5 anos**. Manter indefinidamente é barato (tier frio) e vira diferencial; o propósito deve ser documentado para atender a minimização da LGPD (dado ambiental, não identifica paciente).

**Offboarding de cliente (decidido)**: quando um contrato termina, o hospital continua sendo o responsável legal pelos próprios 5 anos. Fluxo: **exportar tudo ao cliente** (arquivos assinados + relatórios/agregados) → **reter pelo piso legal** (cada registro até completar seus 5 anos, já naturalmente imposto pelo object-lock) → **depois apagar**. Requer um estado de ciclo de vida do cliente/site no Odoo (ativo/offboarding/arquivado/expurgado) e capacidade de export completo. Modelagem em `odoo_modelo_dados_spec.md`.

### 9.1 Hospedagem (decidido nesta rodada)

**Esclarecimento do que "self-hosted" significa aqui**: software **auto-gerenciado** (sem PaaS/banco gerenciado, sem lock-in), rodando em **infra alugada** (não hardware próprio). Não é on-premise/bare metal.

- **Onde**: VPS alugada (o Afonso já possui uma), **em datacenter no Brasil** (residência de dados). Nota jurídica: a LGPD **não obriga** armazenar no Brasil, mas a transferência internacional está mal regulamentada pela ANPD e editais/compliance hospitalar costumam exigir hospedagem nacional — então Brasil é o default pragmático e comercialmente seguro, não uma obrigação legal estrita.
- **Como**: **tudo em Docker (Docker Compose)**. Containers previstos: reverse proxy (Traefik/Caddy com TLS automático) na frente; `odoo`; **`postgres-odoo` e `timescaledb` como dois containers Postgres separados** (mantém a separação de tuning/restart, mesmo dividindo o hardware da VPS única); `mosquitto` (broker central); `sftpgo`; `openvpn`; e os serviços Python (ingestão, API de leitura, API de tempo real, auth/JWT). SPA React servida como estática pelo reverse proxy.
- **Dados com estado em volumes persistentes**: os dois bancos, o filestore do Odoo e os arquivos recebidos pelo SFTPGo — são a "joia da coroa" e o alvo do backup.

### 9.2 Durabilidade e disponibilidade (tensão da VPS única — resolvida por estágio)

Uma VPS única com tudo em Docker é um **ponto único de falha**, o que conflita com o requisito de HA. Reconciliação por separação de conceitos:
- **Disponibilidade** (estar no ar): numa VPS única, uma queda tira o sistema do ar por algumas horas — **tolerável em piloto/início**. A réplica de streaming fica **estagiada** como passo seguinte (crescer a VPS verticalmente e depois separar serviços/banco em nós dedicados conforme a carga sobe), não como bloqueador de lançamento.
- **Durabilidade** (não perder o dado): **inegociável desde o dia 1**, independe de ter 1 ou 2 máquinas. Garantida pelo **backup sair da VPS** — PITR do banco (ex. pgBackRest) + cópia imutável dos arquivos assinados, ambos para **object storage em domínio de falha separado**.
- **Object-lock/WORM real**: um MinIO em container dá API S3 local, mas se está no mesmo disco que tudo o mais, a imutabilidade é fraca (o root da VPS apaga o volume). A cópia imutável de verdade deve ir para **object storage externo com object-lock que as credenciais da aplicação não conseguem sobrescrever**.
- **PENDÊNCIA CRÍTICA PRÉ-PRODUÇÃO — destino do backup off-box**: recomendação = **object storage S3 com object-lock de um provedor no Brasil** (ex. Magalu Cloud object storage, confirmando suporte a object-lock), idealmente de provedor distinto do da VPS para separar ainda mais o domínio de falha. O sistema pode ser **construído** sem isso, mas **não deve ir a produção com dado real de cliente** sem o backup off-box configurado. A confirmar com o Afonso.

## 10. Alarmes

Modelo decidido: **sincronização bidirecional** entre Hub (LCD local) e nuvem (Odoo), com log de auditoria dos dois lados.

Com o fluxo MQTT em tempo real dos coletores para o broker local do Hub (seção 6), o Hub mantém visibilidade **quase instantânea** dos sensores mesmo sem depender do ritmo do FTP (que é só para o arquivo oficial/assinado) — o que sustenta o LCD e a avaliação de alarme local como desenhado originalmente.

**Decisão desta rodada — arquivo de alarme assinado no coletor**: além do arquivo de leituras, o coletor agora também gera e assina um **arquivo de alarme diário** (orientado a evento — só grava em transição de estado, entrada/saída de alarme), com o mesmo padrão de integridade (cadeia de hash, assinatura pelo secure element). Motivo: um alarme é um fato regulatório em si, não algo que deveria depender de reconstrução posterior a partir do dado bruto — ter o coletor assinando o evento no momento em que acontece dá mais força de evidência e funciona mesmo sem o Hub/servidor disponíveis. O arquivo é gerado (e assinado) **todos os dias, mesmo com zero eventos** — um atestado positivo de monitoramento contínuo. Especificação completa em `esp32_coletor_spec.md` (seção 5).

Isso estende a sincronização de limiar (antes só Hub↔nuvem) **até o coletor**, via o bridge MQTT já existente — com fallback obrigatório para os valores regulatórios (RDC 15) caso o coletor nunca tenha recebido configuração.

**Fallback de alarme crítico por SMS (decidido nesta rodada)**: o mesmo modem 4G que dá conectividade ao Hub (seção 6) também emite **SMS de alarme crítico** — hardware/SIM unificados. Cenário que isso cobre: se o link de dados com o servidor cair mas o 4G/SMS estiver vivo, um alarme crítico ainda alerta o responsável diretamente no celular. Reforça também com o Hub numa pequena UPS: um piscar de energia não silencia o alerta. Isso **fecha o item que estava em aberto** (fallback de alarme offline). Sub-itens delegados à implementação: para quem/quais números o SMS vai (cadastro no Odoo), quais alarmes são "críticos" o suficiente para disparar SMS (evitar spam), e anti-flood (não mandar SMS a cada oscilação).

Recomendações a validar:
- Limiares da RDC 15 (tabela da seção 3) como **valores-padrão travados**, editáveis apenas por perfil com permissão elevada e com justificativa registrada.

**Indicação local (LED/buzzer) no coletor — decidido**: **não entra na v1**. A avaliação de alarme já existe no firmware do coletor (necessária para gerar o arquivo de alarme), mas não aciona indicador físico nesta versão — sinalização visual continua centralizada no LCD do Hub. Candidato a v2.

## 10.1 Control plane — gestão de configuração e comandos remotos (decidido nesta rodada)

Formaliza como recurso de primeira classe o que antes estava só implícito (a sincronização de limiar era o único pedaço especificado). O objetivo é gerência sobre cada ponto de coleta a partir do servidor.

**Duas fontes de verdade complementares, sem contradição com "o coletor é a fonte de verdade"**: o **dado medido** (leituras/alarmes) tem fonte de verdade no dispositivo (mede e assina); a **configuração** (como o dispositivo deve operar) tem fonte de verdade no **servidor/Odoo**. Uma é o que aconteceu; a outra é como o aparelho foi mandado operar.

**O que é gerenciável remotamente** (desce Odoo → Hub → coletor via MQTT): limiares de alarme, intervalo de leitura por sensor, habilitar/desabilitar sensor, e **toda a configuração Modbus** (barramentos, endereços, perfis de registrador — que já precisa descer pro Hub de qualquer forma para ele ler o barramento).

**O que fica no provisionamento local** (uma vez, não remoto): conectividade e identidade do próprio dispositivo (credenciais WiFi/APN, `coletor_id`, chaves) — problema do ovo/galinha (precisa de rede para receber config, então a config da rede tem que ser semeada localmente).

**Mecânica do canal de config (decidido)**:
- **Baseada em estado, via MQTT retained**: servidor publica a config corrente (com número de versão) num tópico retido por dispositivo; dispositivo offline pega a última versão ao reconectar — nada se perde.
- **Versão + confirmação de volta**: dispositivo reporta via MQTT qual versão de config está rodando; o Odoo mostra o *drift* ("dispositivo X na v5, última é v6, ainda não aplicou"). Esse laço fechado é a "gerência" de verdade — sabe-se o estado real de cada aparelho.
- **Fallback**: se o dispositivo nunca recebeu config, usa os padrões regulatórios hardcoded (já especificado para limiares, generalizado).
- **Trilha de auditoria**: toda alteração registrada (chatter do Odoo).

**Comandos remotos (decidido — incluídos na v1)**: além de config declarativa, o servidor pode enviar ações imperativas — **reboot, force-sync (reenviar arquivo/dia), pedir diagnóstico/status**. Diferença técnica importante frente à config: comandos vão por tópico MQTT **não-retido**, com **id único + ack + de-duplicação** no dispositivo — para que uma reconexão não re-execute um comando antigo (config é estado, comando é evento único).

**Segurança da config/comando — decisão desta rodada**: **sem assinatura na v1**. Confia-se na segurança do canal (OpenVPN no trecho Hub↔servidor; rede local no trecho ESP32↔Hub). **Assimetria consciente** com o cuidado que tivemos no caminho do dado (que é assinado): um broker comprometido ou MITM na rede local poderia, em tese, empurrar config maliciosa (ex: afrouxar limiar para mascarar violação). **Registrado como candidato forte a endurecimento em v2** (assinar a config no servidor e o dispositivo verificar antes de aplicar).

## 11. Segurança e integridade dos dados

- **Hash encadeado por linha, escopo interno a cada arquivo diário** (sem encadeamento entre dias).
- **Assinatura digital na origem mais próxima do sensor**: coletores WiFi/Ethernet assinam com a chave do ATECC608A embutido no módulo ESP32-WROOM-32SE; para RS-485, onde não há coletor físico separado, **o próprio Hub assina** com seu secure element (ATECC608 via I2C, ver seção 6), atuando como coletor daquele barramento. Em ambos os casos, o princípio é o mesmo: quem gera a leitura é quem assina, o mais perto possível do ponto físico de medição.
- Ancoragem do hash via MQTT quase em tempo real (do coletor para o broker local do Hub, e daí para o broker central) — dá ao servidor prova de existência do dado antes mesmo do arquivo oficial (assinado) chegar.
- **Ledger de recebimento no servidor**: tabela própria que registra, para cada dia recebido de cada coletor: `coletor_id`, `hub_id`, `data`, `hash_final`, `assinatura`, `horário de recebimento`, `status de validação`. Detecta lacunas na sequência sem depender da integridade física de nenhum arquivo antigo.
- Storage do servidor imutável (WORM/object lock).
- Broker MQTT central não exposto publicamente — acessível só via túnel OpenVPN. **Consequência (seção 12)**: browsers de clientes não conectam direto no broker; recebem tempo real via nossa API (SSE/WSS) que retransmite por tenant. Isso permite manter o broker central como **Mosquitto** (não precisa de EMQX para auth de browser).
- FTP entre coletor e Hub é aceitável (rede local + dado já assinado na origem); FTP tradicional continua descartado para qualquer trecho que atravesse rede aberta (ex. Hub→Servidor, se não estivesse dentro da VPN).
- LGPD: avaliar se os dados coletados (ambientais, não identificam pacientes diretamente) trazem exigência adicional de tratamento — ponto a aprofundar com jurídico se necessário.

## 12. Frontend

**Decidido nesta rodada — arquitetura híbrida.** Spec completa em `frontend_spec.md`.

- **Telas administrativas/config → Odoo nativo (OWL)**: cadastro e ciclo de vida de alarme, aproveitando os modelos já especificados.
- **Dashboard de monitoramento do cliente → SPA React dedicada** (Vite + React, TanStack Query, uPlot para gráficos, Tailwind + shadcn/ui). Web responsivo, **sem app nativo na v1**.
- **Mapa de dados**: valores ao vivo via push da nossa API de tempo real (que escuta o MQTT interno); séries históricas via nova **API de leitura sobre o Timescale** (FastAPI, com downsampling pelos continuous aggregates); alarmes e metadados via API do Odoo.
- **Tempo real — consequência da decisão de não expor o broker**: como o browser não está na VPN e o broker central não é público, o caminho é `browser → nossa API (SSE/WSS) → broker interno`, com a API retransmitindo por tenant. Isso mantém superfície de auth única (Odoo como provedor de identidade, JWT) e permite que o broker central siga sendo Mosquitto (não precisa de EMQX, já que browsers não conectam direto nele).
- **Componentes novos que isso adiciona ao sistema**: API de leitura do Timescale, API de tempo real (SSE/WSS), endpoint de autenticação/JWT, e a própria SPA React estática sobre HTTPS.

## 13. Pontos em aberto / próximos passos

1. ~~Protocolo Hub↔Servidor para o arquivo~~ — **resolvido, ver seção 8**: SFTP via SFTPGo, restrito à interface OpenVPN, com confirmação de validação via MQTT. Decidido com base na reavaliação: Raspberry Pi é Linux completo (sem a limitação de processamento do ESP32) e a VPN já cobre autenticação/criptografia de rede, reduzindo o ganho do mTLS frente ao esforço de construir uma API própria.
2. ~~Ponte RS-485→MQTT no Hub~~ — **resolvido, ver seções 5/6**: não é uma ponte a partir de coletor externo, o próprio Hub lê o barramento, monta e assina o arquivo, e publica no broker local — o Hub assume o papel de coletor nesse caso. Detalhe Modbus fechado na seção 6.1 (item 11).
3. ~~Modelo específico do Raspberry Pi~~ — **resolvido: Pi 3B, placa completa** (ver seção 6). Abre sub-itens: desabilitar Bluetooth onboard para liberar a UART PL011 (necessário para RS-485 confiável), e projeto de gabinete/fixação mecânica (sem carrier board própria).
4. ~~Indicação local de alarme crítico no coletor~~ — **resolvido: não entra na v1** (ver seção 10). Candidato a v2.
5. ~~Modelo de dados do Odoo~~ — **resolvido, spec completa em `odoo_modelo_dados_spec.md`** (10 modelos, hierarquia, regras de negócio, segurança). Sub-itens que restam: versão do Odoo a usar, desenho da API de integração com o serviço de ingestão, e definição se o cliente final terá portal Odoo próprio.
6. ~~Política de retenção pós-5-anos~~ — **resolvido, ver seção 9.3**: modelo em camadas (arquivo assinado = registro autoritativo; Timescale cru só em janela quente, agregados mantidos; object-lock garante o piso de 5 anos). Pós-5-anos **configurável por contrato** (nunca abaixo do piso). Offboarding: exporta ao cliente + retém piso legal + apaga.
7. ~~Canal de fallback de alarme offline (SMS/celular)~~ — **resolvido: entra na v1** (ver seção 10), unificado no mesmo modem 4G que dá conectividade ao Hub. Sub-itens delegados: destinatários/números (cadastro Odoo), quais alarmes disparam SMS, anti-flood.
8. ~~Frontend~~ — **resolvido, spec completa em `frontend_spec.md`** (híbrido Odoo + SPA React, web responsivo, mapa de dados, tempo real via SSE). Sub-itens delegados/em aberto listados lá (relatórios de conformidade, push nativo v2, login do cliente final). Adiciona à arquitetura: API de leitura do Timescale, API de tempo real, endpoint de JWT.
9. ~~Hospedagem do self-hosted~~ — **resolvido, ver seção 9.1/9.2**: infra alugada (VPS que o Afonso já tem), datacenter no Brasil, tudo em Docker Compose. VPS única é postura de início (HA por réplica fica estagiada). **Pendência crítica pré-produção**: destino do backup off-box (object storage S3 com object-lock no Brasil) — sistema pode ser construído sem, mas não vai a produção com dado real sem isso.
10. ~~Regra de escaping do delimitador `|` e formato de compactação~~ — **resolvido, ver `esp32_coletor_spec.md` seção 4**: escaping resolvido por proibição do caractere `|` nos identificadores na origem (constraint no Odoo), não por compactação em v1 (arquivos pequenos o suficiente para não precisar).
11. ~~Endereçamento Modbus/multiponto no script de leitura RS-485~~ — **resolvido, ver seção 6.1**: Modbus RTU, Hub como mestre (pymodbus), catálogo de perfis de dispositivo para o mapa de registradores, multi-bus desde a v1 via adaptadores USB-RS485. Modelagem no Odoo detalhada em `odoo_modelo_dados_spec.md`.
12. **Firmware do coletor ESP32**: spec completa em `esp32_coletor_spec.md` (hardware, arquitetura de firmware, fluxo operacional, resiliência). Provisionamento, OTA, biblioteca de cliente FTP e política de retry/backoff foram deliberadamente delegados para a sessão de implementação decidir.
13. **Arquivo de alarme assinado no coletor**: decidido nesta rodada (seção 10, `esp32_coletor_spec.md` seção 5). Sub-item que resta: tópico/formato exato da mensagem MQTT de sincronização de limiar até o coletor (delegado à implementação).
14. **Conectividade 4G do Hub**: decidido (seção 6) — configurável por site (4G primário ou cabeado+4G failover), modem com SMS e antena externa. Sub-itens que restam: seleção do modelo de modem, suporte a dois modos no Hub, e checagem de cobertura celular no survey de instalação de cada site.
15. **Destino do backup off-box** (pendência crítica pré-produção, seção 9.2): object storage S3 com object-lock no Brasil — a confirmar/contratar.
16. ~~Gestão de configuração e comandos remotos (control plane)~~ — **decidido, ver seção 10.1** (e `esp32_coletor_spec.md` 5.1/5.1.1, `odoo_modelo_dados_spec.md` regra 6): config via MQTT retido + versão + confirmação de volta (drift visível no Odoo); comandos remotos (reboot/force-sync/diagnóstico) via tópico não-retido com id+ack. **Config sem assinatura na v1** (confia no canal) — endurecimento por assinatura **reclassificado**: deixa de ser "candidato v2 genérico" e passa a ser **requisito da trilha "tier regulado"** (Part 11/ALCOA+), ver `matriz_conformidade.html` e `roadmap_implementacao.md`.
17. **Trilha "tier regulado" (nova, opcional)** — alinhamento pleno a 21 CFR Part 11 / ALCOA+ / RDC 658-665-945, para desbloquear farma/dispositivos/laboratórios. Base de integridade de dados já forte; faltam 3 frentes: assinatura eletrônica humana, assinatura de config, pacote de validação CSV/GAMP 5. Mapeamento completo em `matriz_conformidade.html`. Não bloqueia o mercado hospitalar base (RDC 15).

## 14. Fontes consultadas

- [CMEXX](https://cmexx.com.br/)
- [CME Cloud](https://cmecloud.com.br/)
- [Stericontrol](https://www.stericontrol.com/)
- [Hosplog — CME](https://hosplog.com.br/solucoes/central-material-esterilizado/)
- [CensiTrac (Censis)](https://censis.com/solutions/censitrac/)
- [T-DOC Select — Getinge](https://www.getinge.com/int/products/t-doc-select/)
- [SPM — Steris](https://www.steris.com/healthcare/products/spm)
- [Comparativo Datacake vs Ubidots vs ThingsBoard](https://industrialmonitordirect.com/blogs/knowledgebase/white-label-mqtt-dashboard-platforms-datacake-vs-ubidots-vs-thingsboard)
- [Odoo IoT Box — arquitetura técnica](https://lse-odoo.github.io/iot/technical/structure/structure-iot-box.html)
- [RDC nº 15/2012 — Anvisa (texto oficial)](https://bvsms.saude.gov.br/bvs/saudelegis/anvisa/2012/rdc0015_15_03_2012.html)
- [Tiger Data — Como escolher um banco de dados IoT](https://www.tigerdata.com/learn/how-to-choose-an-iot-database)
- [QuestDB — Comparativo de bancos de série temporal](https://questdb.com/blog/best-time-series-databases/)
- [FTP vs SFTP — segurança](https://www.goanywhere.com/blog/ftp-vs-sftp-considerations-secure-file-transfer)
- [SFTPGo — Event Manager (webhooks pós-upload)](https://docs.sftpgo.com/2.6/eventmanager/)
- [ESP32-WROOM-32SE — módulo com secure element ATECC608A integrado](https://docs.espressif.com/projects/esp-idf/en/v5.2/esp32/api-reference/peripherals/secure_element.html)
- [Autenticação mTLS para dispositivos IoT](https://www.ssl.com/article/authenticating-users-and-iot-devices-with-mutual-tls/)
- [Habilitando UART no Raspberry Pi — PL011 vs Mini UART](https://raspberry.tips/en/raspberrypi-tutorials/enable-uart-raspberry-pi)
- [uPlot — biblioteca de gráfico de série temporal](https://github.com/leeoniya/uplot)
- [MQTT sobre WebSocket — EMQX](https://www.emqx.com/en/blog/connect-to-mqtt-broker-with-websocket)
- [Odoo OWL — comparação com Vue/React](https://github.com/odoo/owl/blob/master/doc/miscellaneous/comparison.md)
