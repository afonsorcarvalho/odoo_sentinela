# Roadmap de Implementação — Plataforma de Monitoramento de Sensores

> Sequência de construção do sistema, com dependências, trilhas paralelas e marcos. Baseado nos quatro documentos de especificação. Escrito para orientar as sessões de implementação (Claude no WSL2): cada "work package" abaixo é escopo de uma ou mais sessões.

**Documentos de referência** (todos na pasta do projeto):
- `diretrizes_projeto.md` — visão geral e histórico de decisões (ler primeiro, sempre)
- `odoo_modelo_dados_spec.md` — backend / modelo de dados
- `esp32_coletor_spec.md` — firmware do coletor
- `frontend_spec.md` — dashboard

---

## Princípios que guiam a ordem

1. **Fatia fina de ponta a ponta primeiro**: fazer 1 sensor → arquivo assinado → ingestão → dashboard funcionar de verdade *antes* de adicionar largura (muitos sensores, muitos protocolos, muitos clientes). Prova a arquitetura cedo e barato.
2. **Simulador desacopla software de hardware**: um "coletor simulado" (script que gera arquivos assinados válidos no formato acordado + publica MQTT) permite construir e testar **todo o lado servidor sem esperar o ESP32 e o Raspberry Pi**. É um dos primeiros entregáveis, e o maior destravador do cronograma.
3. **Contratos antes de código**: os formatos de interface (arquivo, tópicos MQTT, claims do JWT, API Odoo↔ingestão) são congelados na Fase 0. São as fronteiras entre as peças — definir com precisão evita dor de integração depois.

## Mapa de dependências (resumo)

```
Fase 0 (contratos) ──► tudo
Fase 1 (Odoo model + Timescale schema) ──► Fase 2, 3, 5
Fase 2 (simulador + ingestão) ──► Fase 3, 4 (dados reais p/ testar)
Fase 3 (APIs: auth, leitura, tempo real) ──► Fase 4
Fase 4 (frontend) ────────────────────────► Marco M1 (piloto)
Fase 5 (control plane) ──► Fase 6, 7 (dispositivos consomem config)
Fase 6 (Hub) e Fase 7 (ESP32) ──► precisam de hardware; simulador cobre o contrato antes
Fase 8 (retenção, backup, HA, monitoramento) ──► gate pré-produção
```

---

## Fase 0 — Fundações e contratos de interface
**Objetivo**: congelar as fronteiras e montar o esqueleto. Bloqueia tudo.
**Entregáveis**:
- Esqueleto de repositório + **Docker Compose** com os serviços vazios/placeholder (reverse proxy, odoo, postgres-odoo, timescaledb, mosquitto, sftpgo, openvpn, serviços Python).
- **Documento de contratos** (curto, versionado no repo) fixando: formato exato do arquivo `.txt` (de `esp32_coletor_spec.md` §4/5), **estrutura de tópicos MQTT** (telemetria; config retido; comando não-retido; ack; report de `config_version`), **claims do JWT**, e o contrato da **API Odoo↔serviço de ingestão**.
**Depende de**: nada. **Faça primeiro.**

## Fase 1 — Núcleo do backend (data plane)
Duas trilhas **paralelas**:

**1A — Módulo Odoo** (`odoo_modelo_dados_spec.md`)
- Todos os modelos (site, área, hub, coletor, sensor, thresholds, alarm.event, file.ledger, os 4 modelos Modbus, campos de config_version e retenção/ciclo de vida).
- `ir.rule` multi-tenant, grupos, dados de referência RDC 15.
- Sub-decisão a confirmar no início: **versão do Odoo** (17/18/19).

**1B — Schema TimescaleDB**
- Hypertables (leituras, eventos de alarme), particionamento por tempo + `site_id`.
- Continuous aggregates (hora/dia: mín/máx/média).
- Políticas de compressão e a base da retenção em camadas (janela quente do cru).

**Depende de**: Fase 0.

## Fase 2 — Simulador + Ingestão (a fatia fina)
**Objetivo**: primeiro dado real fluindo ponta a ponta no servidor.
**Entregáveis**:
- **Coletor simulado**: gera arquivos assinados válidos (cadeia de hash + assinatura de teste) e publica telemetria MQTT — no formato da Fase 0.
- **SFTPGo** configurado (isolamento por hub, só na interface da VPN).
- **Serviço de ingestão** (Python): recebe via SFTP → valida cadeia de hash + assinatura → `COPY` no Timescale → atualiza `file.ledger` → avalia alarmes → publica ack de validação via MQTT. Cria `alarm.event` no Odoo quando aplicável.
- Job de detecção de lacuna no ledger (cron Odoo).
**Depende de**: Fase 1 (model + schema).

## Fase 3 — Camada de serviço (APIs)
Três entregáveis, podem ser paralelos entre si (mas todos dependem da Fase 1/2):
- **Endpoint de auth/JWT** (Odoo como provedor de identidade).
- **API de leitura** (FastAPI sobre Timescale, downsampling por janela via continuous aggregates, filtro de tenant do JWT).
- **API de tempo real** (SSE; assina o broker interno; retransmite por tenant).
- **Mosquitto central** configurado (não exposto; bridge dos hubs).
**Depende de**: Fase 1, e dado da Fase 2 para testar.

## Fase 4 — Frontend (SPA React)
**Objetivo**: dashboard do cliente funcionando. (`frontend_spec.md`)
- Vite + React, TanStack Query, uPlot, Tailwind/shadcn.
- Telas: overview, site→área, detalhe do sensor (histórico + cauda ao vivo + linhas de limite), painel de alarmes.
- Consome as 3 APIs da Fase 3. Pode começar contra APIs mockadas em paralelo à Fase 3; integração real precisa da Fase 3 pronta.
- Telas administrativas ficam no Odoo nativo (já saem da Fase 1).
**Depende de**: Fase 3.

### ▶ MARCO M1 — Piloto de ponta a ponta
Fatia fina completa: simulador → arquivo assinado → ingestão → Timescale/Odoo → dashboard mostra ao vivo + histórico + alarmes. **Prova a arquitetura inteira do lado servidor sem hardware.** É a meta a perseguir primeiro; tudo até aqui é o caminho crítico.

## Fase 5 — Control plane (config + comandos remotos)
**Objetivo**: gerência remota de cada dispositivo (diretriz §10.1).
- Propagação de config: `write()` no Odoo → incrementa `config_version_desejada` → publica config em tópico MQTT **retido** por dispositivo.
- Report de volta: dispositivo reporta versão aplicada → Odoo mostra **drift**.
- Comandos remotos (reboot/force-sync/diagnóstico) por tópico **não-retido** com id+ack.
- Testável com o simulador (que passa a consumir config e reportar versão).
**Depende de**: Fase 1 + Mosquitto (Fase 3).

## Fase 6 — Edge: software do Hub (Raspberry Pi 3B)
**Precisa de hardware.** O contrato com o servidor já foi validado pelo simulador, então isto integra com um lado servidor já pronto.
- Cliente **OpenVPN**; **Mosquitto local** + bridge para o central.
- Store-and-forward dos arquivos dos coletores WiFi/Ethernet (preserva intactos) + **cliente SFTP** para o servidor.
- **Leitor RS-485/Modbus** (pymodbus): multi-bus, catálogo de perfis, o Hub como coletor-embutido que **gera e assina** os arquivos RS-485 (secure element ATECC608). Testável contra um simulador Modbus.
- Passo de setup: **desabilitar Bluetooth** para liberar a UART PL011.
- LCD + avaliação de alarme local; handler de config/comando; **gestão do modem 4G** (modo por site: 4G primário ou cabeado+failover) e **SMS de alarme crítico**.
**Depende de**: Fases 2, 5, e hardware.

## Fase 7 — Edge: firmware do coletor ESP32
**Precisa de hardware.** Fica por último porque o simulador já cobriu seu contrato voltado ao servidor desde a Fase 2. (`esp32_coletor_spec.md`)
- ESP-IDF; leitura 4-20mA (ADS1115)/I2C/serial; arquivo de leituras + arquivo de alarme, ambos assinados (ATECC608A); MQTT + SFTP; cache de config + report de versão; fail-safe de limiar regulatório.
- Sub-itens delegados: provisionamento, OTA, biblioteca FTP, retry/backoff.
**Depende de**: Fases 2, 5, e hardware.

## Fase 8 — Retenção, backup e operação (gate pré-produção)
- **Serviço de retenção**: drop de linhas cruas fora da janela quente no Timescale (mantendo agregados) + lifecycle/tiering no object storage; expurgo só após object-lock expirar.
- **⚠ GATE PRÉ-PRODUÇÃO — backup off-box**: object storage S3 com object-lock no Brasil (a contratar). **Não subir com dado real de cliente sem isto.** (diretriz §9.2)
- **Réplica de HA** (streaming) — estagiada, pode ser pós-lançamento do piloto.
- **Monitoramento** (saúde do banco, dos hubs, drift de config, lacunas no ledger).
- Fluxo de **offboarding** (export + retenção do piso + expurgo).

---

## Trilhas paralelas (para dividir esforço)
- **Trilha servidor** (crítica): Fase 0 → 1 → 2 → 3 → 4 → M1. É o caminho crítico; priorizar.
- **Trilha edge** (pode começar em paralelo após Fase 0/contratos): prototipagem de hardware, desabilitar BT no Pi, testes de RS-485/Modbus com simulador, testes de cobertura 4G nos sites-piloto. Integração formal nas Fases 6/7.
- **Trilha frontend**: começa contra mocks em paralelo à Fase 3.

## Trilha "tier regulado" (opcional — desbloqueia farma, dispositivos, laboratórios)
Não é necessária para o mercado hospitalar base (RDC 15), mas fecha a aderência plena a 21 CFR Part 11 / ALCOA+ / RDC 658-665-945 e abre um tier de clientes muito mais valioso. Detalhamento e status em `matriz_conformidade.html`. Três frentes:
1. **Módulo de assinatura eletrônica humana** (molde Part 11): aprovação/revisão com manifestação (nome, data/hora, significado), vínculo e não-repúdio.
2. **Assinatura da configuração no control plane** (reclassificada de "candidato v2" para requisito deste tier): servidor assina, dispositivo verifica antes de aplicar.
3. **Pacote de suporte à validação (CSV / GAMP 5)**: especificações, categorização GAMP 5, roteiros IQ/OQ/PQ, revisão de trilha de auditoria.
> Lembrete honesto: conformidade Part 11/BPF é alcançada pelo cliente via validação + POPs; o produto entrega "projetado para integridade de dados e pronto para validação", não certificação.

## Marcos
- **M1 — Piloto ponta a ponta (servidor)**: fim da Fase 4. Simulador prova tudo sem hardware.
- **M2 — Piloto real em 1 site**: Fases 6/7 num hardware real + 1 CME piloto, com backup off-box (gate) ativo. Primeira validação de campo.
- **M3 — SaaS multi-cliente endurecido**: retenção/tiering, HA por réplica, monitoramento completo, control plane com comandos, e (candidato) assinatura de config (endurecimento v2).

## Gates e decisões pendentes que afetam o roadmap
- **Pré-produção (bloqueante)**: backup off-box configurado (Fase 8).
- **A confirmar no início da Fase 1**: versão do Odoo.
- **A confirmar cedo**: desenho fino da API Odoo↔ingestão (Fase 0/2); se o cliente final terá portal Odoo próprio ou só a SPA (afeta Fase 4).
- **Candidatos a v2 (não bloqueiam v1)**: LED/buzzer no coletor; app mobile nativo com push; OTA do ESP32.
- **Trilha tier regulado (opcional, ver acima)**: assinatura eletrônica humana, assinatura de config, pacote de validação CSV/GAMP 5. A assinatura de config saiu de "candidato v2 genérico" para requisito deste tier.
