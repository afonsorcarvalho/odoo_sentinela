# Hub — Fatia 2 / Transporte T1: Espinha de arquivo (SFTP Hub→servidor)

**Data:** 2026-07-21
**Autor:** Afonso Carvalho + Claude (sessão de brainstorming)
**Fase do roadmap:** 6 (Edge — software do Hub), sub-fatia de transporte
**Referências:** `diretrizes_projeto.md` (§6, §8, §11), `roadmap_implementacao.md` (Fase 6), Fatia 1 (`hub/` já entregue: leitor → arquivo assinado + MQTT local), `ingestao/ingestor.py` (`ingerir_arquivo`), `ingestao/validador.py`, `ingestao/registro_coletores.py`

---

## 1. Contexto e objetivo

A Fatia 1 do Hub gera arquivos `.txt` diários assinados, mas eles **ficam parados no Pi** — nada chega ao servidor. Esta fatia entrega a **espinha de arquivo (T1)**: o Hub envia os arquivos selados ao servidor via **SFTP** (SFTPGo), e o servidor **ingere** cada upload (valida hash + assinatura → grava no TimescaleDB, atualiza o `file.ledger` no Odoo). Fecha o caminho "arquivo assinado sobe e é ingerido".

A decisão maior de transporte (`diretrizes §8`) é: túnel OpenVPN + SFTP via SFTPGo restrito à interface da VPN + confirmação de validação via MQTT. Esta fatia constrói **só o SFTP + ingestão pós-upload**. **OpenVPN é a fatia T3; o ack de validação via MQTT é a fatia T2** — ambos fora daqui.

### 1.1 Realidade de topologia (decidido)
- O **servidor (Odoo/Timescale + SFTPGo novo) roda em outra máquina no LAN** (PC/WSL2 do Afonso). Este Pi (o Hub) o alcança por IP. **Não há docker no Pi.**
- Divisão de trabalho: **lado-Hub** construído e testado neste Pi; **lado-servidor** escrito como código + runbook, **implantado/testado pelo Afonso no LAN** ("construir agora, testar depois"). O teste cross-machine é um passo final conjunto.

### 1.2 Objetivos
- Cliente SFTP no Hub que envia arquivos selados ainda-não-enviados, com auth por **chave SSH ed25519** por hub.
- Rastreio de envio por **arquivo de índice de estado** (`_enviados.json`) — o arquivo permanece no lugar; retry natural no próximo ciclo em caso de falha; nunca reenvia o que já subiu; nunca derruba o loop.
- Provisionamento da identidade SSH do Hub (par ed25519, separado da chave EC de assinatura).
- Lado-servidor: serviço **SFTPGo** no `docker-compose.yml` (isolamento por hub, auth por chave) + **fiação da ingestão pós-upload** (SFTPGo Event Manager → `ingerir_arquivo`).
- Runbook de deploy/verificação do lado-servidor e do teste cross-machine.

### 1.3 Não-objetivos (fatias seguintes)
Ack de validação de volta ao Hub via MQTT (T2), bridge MQTT local→central (T2), OpenVPN + PKI (T3). Rotação/limpeza de `_enviados.json`, compressão de arquivo, e retomada de upload parcial (arquivos são pequenos; re-upload inteiro no retry) ficam fora.

---

## 2. Decisões desta sessão

1. **Começar por T1 (SFTP)**, decompondo "Transporte" em T1 (arquivo) / T2 (MQTT bridge + ack) / T3 (OpenVPN).
2. **Auth SFTP por chave SSH ed25519 por hub** (sem senha em disco); isolamento por usuário/pasta no SFTPGo.
3. **Estado de envio via arquivo de índice** (`_enviados.json`) — não move o arquivo original.
4. **`paramiko`** como cliente SFTP no Hub.
5. **T1 sem ack MQTT** — no T1 a ingestão só processa e grava no ledger; o feedback de volta é o T2.
6. **Construir agora, testar o servidor depois** — lado-servidor entra como código + runbook.

---

## 3. Arquitetura e decomposição

### 3.1 Lado-Hub (este Pi — TDD aqui)
| Módulo | Responsabilidade |
|---|---|
| `hub/enviador_sftp.py` | `EnviadorSftp` (lógica: varre selados não-enviados, envia, grava estado, retry, idempotência) + `TransporteParamiko` (impl real SFTP/paramiko, auth por chave). |
| `hub/identidade_ssh.py` | Gera/carrega o par ed25519 do Hub; expõe a pubkey (OpenSSH) para registro no SFTPGo. |
| `hub/config.py` (modificar) | Adiciona o bloco `sftp` (host/port/username/ssh_key_path/remote_dir). |
| `hub/main.py` (modificar) | Constrói o enviador; chama `enviador.varrer()` a cada ciclo e no encerramento. |

**Fronteira de teste:** `EnviadorSftp` recebe um `Transporte` injetável (Protocol com `enviar(caminho_local, nome_remoto)`). A lógica é testada com um transporte fake; `TransporteParamiko` (wrapper fino sobre paramiko) é testado dirigindo um `SFTPClient` **mockado** — confirma que carrega a chave ed25519, conecta em host/port, autentica pela chave e chama `put(local, remote)`. **A validação SFTP real fica no runbook cross-machine** contra o SFTPGo de verdade (paramiko não traz um `SFTPServerInterface` pronto; um servidor in-process seria pesado e frágil, e o valor real está no teste contra o SFTPGo).

### 3.2 Estado de envio
`dados/{coletor_id}/_enviados.json` — `{ "2026-07-21_leituras.txt": {"enviado_em": "2026-07-21T04:50:00-03:00"} }`. `varrer()`:
1. lista `dados/{coletor_id}/*_leituras.txt`;
2. mantém só os **selados** (`arquivo_diario._esta_selado`) e **ausentes** do índice;
3. para cada, `transporte.enviar(...)`; em sucesso, registra no índice e persiste; em falha, loga e segue (fica pendente).

### 3.3 Lado-servidor (código + runbook — Afonso implanta)
- `docker-compose.yml`: serviço `sftpgo` (imagem `drakkan/sftpgo`), volumes para config e homes por hub, porta exposta no dev (ex. `2022`), auth por chave pública.
- `ingestao/receber_upload.py`: entrypoint chamado pelo Event Manager do SFTPGo com o caminho do arquivo recém-enviado → chama `ingerir_arquivo(caminho, registro_path, dsn, cliente_odoo)`. Lê config de ambiente (DSN Timescale, URL/credenciais Odoo, caminho do registro de coletores).
- **Provisionamento no servidor:** (a) registrar a **pubkey EC de assinatura** do Hub via `registro_coletores.registrar_coletor` (para validar o arquivo); (b) registrar a **pubkey SSH** do Hub no SFTPGo (para autenticar o upload).
- `docs/runbooks/transporte-sftp-servidor.md`: passo a passo de subir o sftpgo, registrar as duas chaves, e verificar a ingestão.

---

## 4. Config (adições ao YAML do Hub)

```yaml
sftp:
  host: 192.168.0.10        # IP do servidor no LAN
  port: 2022
  username: hub-0001A2F3
  ssh_key_path: ~/sentinela-hub/chaves/ssh_hub    # par ed25519 (privada); .pub ao lado
  remote_dir: /uploads
```
Ausência do bloco `sftp` → o enviador fica desligado (a Fatia 1 continua funcionando sozinha). Validação: se presente, `host`/`username`/`ssh_key_path` obrigatórios.

---

## 5. Estratégia de testes

- **Pi (TDD, roda aqui):**
  - `identidade_ssh`: gera par ed25519, pubkey em formato OpenSSH, idempotência (recarrega a mesma chave).
  - `EnviadorSftp` com **transporte fake**: envia selado não-enviado; ignora não-selado; não reenvia o que está no índice; falha do transporte deixa pendente (retry no próximo `varrer`); estado persiste entre instâncias.
  - `TransporteParamiko`: dirige um `SFTPClient` **mockado** — carrega a chave ed25519, conecta em host/port, autentica pela chave, chama `put(local, remote)` e fecha. (SFTP real → runbook cross-machine.)
  - `config`: parse/validação do bloco `sftp`; ausência → desligado.
- **Servidor (runbook, Afonso roda):** subir sftpgo no compose, registrar as duas chaves, enviar um arquivo real do Hub → confirmar linha no Timescale + entrada no `file.ledger` do Odoo.
- **Cross-machine (conjunto):** apontar o `sftp.host` do Hub para o IP do servidor, rodar `hub.main`, e verificar a ingestão no servidor.

---

## 6. Pendências deixadas explícitas (não bloqueiam o T1)

- Interface exata do Event Manager do SFTPGo (comando vs. webhook HTTP) — decidir na implementação do lado-servidor, documentar no runbook.
- DSN/credenciais Odoo do `receber_upload` — via variáveis de ambiente no serviço; valores reais são config de deploy do servidor.
- Restrição do SFTPGo à interface da VPN — só quando o T3 (OpenVPN) existir; no T1 fica exposto numa porta do LAN.
- Rotação/limpeza do `_enviados.json` e retomada de upload parcial — arquivos pequenos, re-upload inteiro no retry; revisitar se o volume crescer.
