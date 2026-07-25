# Verificador de autenticidade de arquivos de leitura — design

**Data:** 2026-07-25
**Branch:** `worktree-verificador-autenticidade`

## Contexto e propósito

O arquivo diário de leituras é assinado criptograficamente (ECDSA): cada linha tem
hash encadeado com a anterior + assinatura; header (`hdr_sig`) e rodapé (`hash_final`
+ `assinatura`) também são assinados. A lógica de verificação já existe em
`ingestao/validador.py::validar_arquivo(caminho, registro_path)`.

O Sentinela será comercializado. O objetivo desta feature **não** é "um script CLI",
e sim o **núcleo de verificação do servidor** que dois consumidores vão usar:

1. **CLI** (agora) — operador/você, e para validar o desenho.
2. **Endpoint HTTP + página no browser** (futuro, fora de escopo) — cliente/perito
   sobe arquivos ou um zip e vê o veredito.

A decisão de desenho central: o núcleo é **desacoplado da fonte dos bytes**. Recebe
uma coleção de `(nome, bytes)` e devolve veredito estruturado. O CLI alimenta a
partir de um walk no disco; o futuro endpoint, a partir de uploads/zip. A lógica de
veredito é a mesma, testada uma vez.

## Trust model

Uma assinatura prova "isto foi assinado pela chave X", não "X é do coletor tal". O
segundo elo é o trust model — de onde vem a chave pública. Suportamos os dois públicos:

- **Modo A (interno):** pega `coletor_id` do header, busca a pública no registro
  local `coletores_conhecidos.json`. `fingerprint_conferido = None` (n/a).
- **Modo B (auditor externo):** o terceiro passa a chave pública por PEM
  (canal confiável fora de banda). O núcleo carrega a pública, calcula seu
  fingerprint e **compara com `coletor_pubkey_fingerprint` do header**:
  - bateu → valida com essa chave, `fingerprint_conferido = True`;
  - não bateu → item `invalido`, motivo "chave fornecida não corresponde ao
    fingerprint declarado no header", `fingerprint_conferido = False`.

## Arquitetura

Abordagem escolhida: núcleo em `ingestao/verificador.py`, refatorando `validador`
para separar `validar_texto`; CLI fina em `scripts/`. (Rejeitadas: CLI path-based sem
refactor — amarra ao filesystem e duplica lógica; núcleo em `api/` — acopla à camada
de API antes de existir endpoint.)

### 1. Boundary — núcleo

```python
verificar_itens(
    itens: Iterable[tuple[str, bytes]],
    *,
    registro_path: str | None = None,
    pem_bytes: bytes | None = None,
) -> VerificacaoLote
```

Nunca faz walk no disco nem sabe o que é zip — isso é dos adaptadores. Para cada
item: decodifica texto, resolve a chave (modo A ou B), roda a validação, classifica
o estado.

### 2. Estados por item

Distinguir adulteração de "não deu pra verificar":

- `valido` — tudo confere e arquivo fechado (footer presente e válido).
- `invalido` — autenticidade falhou: cadeia/hash/sig por linha/footer/fingerprint.
  **Este é o alarme de adulteração.**
- `incompleto` — sem rodapé (crash não-fechado): autêntico até a última sig válida,
  mas não selado. Não é adulteração.
- `indeterminado` — não foi possível verificar: coletor não registrado (modo A),
  PEM ausente/ilegível, texto não-parseável ou não é arquivo assinado.
  **Não grita "forjado" quando só falta a chave.**

> O `validador` hoje devolve `invalido` quando o coletor não está no registro. O
> núcleo mapeia esse caso para `indeterminado` — separar "não sei verificar" de
> "assinatura falhou" é o ponto do veredito.

### 3. Estruturas (JSON-serializáveis)

```python
@dataclass
class VerificacaoItem:
    nome: str
    estado: str                      # valido | invalido | incompleto | indeterminado
    motivo: str | None
    coletor_id: str | None
    data_referencia: str | None
    total_linhas: int
    hash_final: str | None
    fingerprint_conferido: bool | None   # True/False no modo B; None no modo A

@dataclass
class VerificacaoLote:
    itens: list[VerificacaoItem]
    total: int
    validos: int
    invalidos: int
    incompletos: int
    indeterminados: int
    todos_ok: bool                   # zero invalidos E zero incompletos E zero indeterminados (== validos == total)
```

O `--json` do CLI e o futuro endpoint devolvem `VerificacaoLote` direto.

### 4. Adaptador CLI — `scripts/verificar_autenticidade.py`

```
verificar_autenticidade <caminho> [--registro PATH] [--pem PATH] [--json]
```

- `<caminho>` arquivo → 1 item; diretório → walk recursivo dos `*.txt` assinados →
  N itens `(caminho_relativo, bytes)`.
- `--registro` default `ingestao/coletores_conhecidos.json` (modo A).
- `--pem PATH` ativa modo B.
- Saída humana: linha por arquivo (estado + coletor + data + nº linhas) + resumo
  agregado. `--json`: dumpa `VerificacaoLote`.

**Exit codes** (precedência 4 > 1 > 2 > 3 > 0):

- `0` — todos válidos.
- `1` — ≥1 inválido (adulteração).
- `2` — sem inválidos, mas ≥1 incompleto.
- `3` — sem inválidos/incompletos, mas ≥1 indeterminado.
- `4` — erro de uso (caminho inexistente, PEM ilegível).

### 5. Refactor em código existente (targeted)

- `ingestao/validador.py`: extrair `validar_texto(texto, chave_publica) -> ResultadoValidacao`
  do miolo. `validar_arquivo(caminho, registro_path)` vira wrapper: lê arquivo +
  resolve chave via registro + chama `validar_texto`. Suíte atual continua verde.
- `contrato/identidade.py`: adicionar `fingerprint_de_publica(chave_publica)`;
  `fingerprint_publica(chave_privada)` passa a delegar (`fingerprint_de_publica(chave_privada.public_key())`).

## Testes

- **Núcleo** (`ingestao/tests/test_verificador.py`): texto assinado fabricado (reusa
  helpers de `test_assinador`/fixtures) — válido; linha adulterada; header adulterado;
  sem footer → incompleto; PEM errado → invalido (fingerprint mismatch,
  `fingerprint_conferido=False`); PEM certo → válido com `fingerprint_conferido=True`;
  coletor não registrado (modo A) → indeterminado.
- **CLI**: arquivo único; diretório com mix (válido+inválido+incompleto) → agregado e
  exit code corretos; `--json` schema; caminho inexistente/PEM ilegível → exit 4.
- **Refactor**: suíte de `validador`/`confronto` continua verde.

## Não-escopo (backlog)

- Zip/compactado (o boundary `(nome, bytes)` já deixa plugável).
- Endpoint HTTP e página no browser.
- Verificador single-file distribuível (auditor externo usa a página web hospedada).
