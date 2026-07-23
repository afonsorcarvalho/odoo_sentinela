# Design — Organização de pastas dos arquivos de leitura

Data: 2026-07-23

## Problema

Os arquivos diários de leitura assinados são enviados ao servidor via SFTP com
nome baseado **apenas na data** (`AAAA-MM-DD_leituras.txt`) numa pasta remota
**plana** (`{remote_dir}/{nome}`). Isso causa três problemas:

1. **Colisão (bug de corretude).** Dois coletores — ou dois hubs — no mesmo dia
   produzem o mesmo nome `2026-07-23_leituras.txt`. Na pasta plana, um
   **sobrescreve o outro**. O `coletor_id`/`hub_id` só existe no cabeçalho
   interno, não no nome nem no caminho.
2. **Navegação.** Localizar manualmente um arquivo no SFTP/disco é difícil sem
   hierarquia.
3. **Escala.** Todos os arquivos de todos os coletores/hubs numa pasta só.

## Estado atual (referência)

- Nome do arquivo: `caminho()` em [hub/arquivo_diario.py:49-50](../../../hub/arquivo_diario.py#L49-L50)
  gera `{data}_leituras.txt`.
- Local no Hub: `dados/{coletor_id}/{data}_leituras.txt` — segregado por coletor,
  1 arquivo por dia, vários sensores por linha dentro (cadeia de hash encadeada
  por-coletor-por-dia).
- Remoto SFTP: **plano**. [hub/enviador_sftp.py:69](../../../hub/enviador_sftp.py#L69)
  faz `sftp.put(local, f"{remote_dir}/{nome_remoto}")` com `nome_remoto` = só o
  nome do arquivo.
- Ingestão: **push** pelo Event Manager do SFTPGo, recebe o caminho exato
  ([ingestao/receber_upload.py](../../../ingestao/receber_upload.py)). Não faz
  glob. `coletor_id` e tenant vêm do **cabeçalho**, não do nome/caminho.
- Identificadores validados apenas contra `|`, `\n`, `\r`
  ([contrato/formato.py:3-8](../../../contrato/formato.py#L3-L8)) — **não** contra
  `/` ou `..`.
- Config do Hub já expõe `cliente_id`, `site_id`, `hub_id`, `coletor_id`,
  `caminho_dados` ([hub/main.py:91-93,117](../../../hub/main.py#L91-L93)).

## Estrutura escolhida (remota)

```
{cliente}/AAAA/MM/DD/{site}/{hub}/{coletor}/AAAA-MM-DD_{hub}-{coletor}_leituras.txt
```

Decisões e razões:

- **Cliente no topo** — retenção/caducamento é **por contrato**. Cliente acima da
  data permite `rm -rf {cliente}/2024/` sem afetar outro cliente com retenção
  diferente. Também é a fronteira natural de isolamento multi-tenant.
- **Data (AAAA/MM/DD) antes de site/hub/coletor** — o ciclo de vida é
  calendário-dirigido. Permite:
  - Caducamento: `rm -rf {cliente}/2024/`.
  - Compactação: rotina que empacota meses/anos antigos (`tar czf
    {cliente}/2024/01.tar.gz {cliente}/2024/01/`). Segura: `tar` preserva bytes,
    então as assinaturas ECDSA continuam válidas; e a ingestão é push no momento
    do upload (já consumiu), então compactar pasta antiga não quebra nada.
- **Nome auto-descritivo** `AAAA-MM-DD_{hub}-{coletor}_leituras.txt` — o arquivo
  solto (baixado, anexado a laudo, enviado por e-mail) se explica fora da árvore.
  Redundância barata com o caminho; o cabeçalho interno continua sendo a verdade.
- **Colisão eliminada** pelo caminho completo único (cliente+data+site+hub+coletor).

Trade-off aceito: "todas as leituras do coletor X ao longo do tempo" fica
espalhado por N pastas de data. O ciclo de vida (retenção/compactação) foi
priorizado sobre esse padrão de navegação por dispositivo.

## Escopo da mudança

A árvore é uma preocupação de **transporte**. A cadeia criptográfica não é
tocada (o nome do arquivo não entra no lastro). Mudanças:

### 1. `contrato/formato.py`

Nova função `validar_segmento_path(valor)`: rejeita `valor` que contenha `/`,
`\`, seja `.` ou `..`, ou seja vazio. Usada para todo identificador que vira
segmento de diretório (cliente, site, hub, coletor), fechando a brecha de
**path traversal** (ex.: `cliente_id = "../../etc"`). `validar_identificador`
existente continua para o conteúdo do cabeçalho.

### 2. `hub/arquivo_diario.py`

- `caminho(data_referencia)` gera o nome auto-descritivo
  `f"{data_referencia}_{self._hub_id}-{self._coletor_id}_leituras.txt"`.
- `recuperar_pendentes` / `_esta_selado`: o parse de data a partir do nome precisa
  extrair `AAAA-MM-DD` do **prefixo** (o nome agora tem sufixo `_{hub}-{coletor}`),
  não mais `replace("_leituras.txt", "")`.
- Globs `*_leituras.txt` continuam válidos.
- **Selagem, reconstrução de estado e cadeia de hash inalteradas.**
- Local do Hub permanece `dados/{coletor}/{nome}.txt` (árvore só no remoto).

### 3. `hub/enviador_sftp.py`

- `EnviadorSftp.__init__` passa a receber `cliente_id`, `site_id`, `hub_id`
  (além de `coletor_id`, `caminho_dados`, `transporte`).
- Ao enviar, monta o sub-caminho remoto da árvore:
  `{cliente}/{AAAA}/{MM}/{DD}/{site}/{hub}/{coletor}/{nome}`, extraindo
  `AAAA/MM/DD` do prefixo do nome do arquivo e validando cada segmento com
  `validar_segmento_path`.
- `TransporteParamiko.enviar` cria os diretórios remotos (`mkdir -p` via SFTP —
  criar cada nível ignorando "já existe") **antes** do `put`, pois `sftp.put`
  não cria diretórios.
- Estado `_enviados.json` continua por-coletor no local (inalterado).

### 4. `hub/main.py`

Passa `cliente_id`, `site_id`, `hub_id` ao construir `EnviadorSftp`
([hub/main.py:117](../../../hub/main.py#L117)).

### 5. Ingestão — zero mudança

É push e lê identidade do cabeçalho. Não depende do nome nem do caminho.

## Migração

**Nenhuma.** Os arquivos antigos (planos) permanecem onde estão. O servidor
atual é ambiente de teste e será apagado; os arquivos já foram ingeridos e são
apenas lastro histórico local.

## Testes

- `validar_segmento_path`: rejeita `/`, `\`, `..`, `.`, vazio; aceita códigos
  normais. Path traversal (`cliente_id="../../etc"`) barrado.
- `arquivo_diario.caminho`: nome auto-descritivo correto.
- `recuperar_pendentes`: reconhece e sela arquivos pendentes com o nome novo.
- Regressão: selagem, reconstrução de estado e cadeia de hash idênticas ao
  comportamento atual (o nome mudou, o lastro não).
- `enviador_sftp`: monta o sub-caminho da árvore correto a partir do nome +
  config; chama `mkdir -p` remoto antes do `put` (via transporte fake que
  registra chamadas).

## Fora de escopo (YAGNI)

- Rotina de compactação automática de pastas antigas — a **estrutura** habilita,
  mas a automação é trabalho separado.
- Re-organização/migração de arquivos legados.
- Arquivo por-sensor (exigiria quebrar a cadeia de hash por sensor).
