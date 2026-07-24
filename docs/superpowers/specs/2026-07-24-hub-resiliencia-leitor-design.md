# Design — Resiliência do loop de leitura do Hub (Plano A)

> Fatia isolada e urgente extraída da discussão
> `docs/discussao-drivers-extensibilidade.md` (§A). Fix de crash de produção,
> independente do trabalho de registro de drivers (B/C/D). Merge antes de B/C/D.

## Problema

Um único sensor mal-configurado derruba o hub inteiro. Em produção, adicionar um
sensor com o driver errado (`n4aib16` num RS-WS-N01-2D) gerou um frame Modbus curto
→ `IndexError` no driver → processo do hub morto → dashboard congelado (sem hub, sem
MQTT, sem live).

Existem **dois** pontos únicos de falha em `hub/leitor.py`:

1. **`ler_todos` (linha ~58).** `except RuntimeError` não captura `IndexError`
   (nem `ValueError`, `struct.error`, etc.). Qualquer exceção fora de `RuntimeError`
   num dispositivo propaga e mata o loop — inclusive os sensores que funcionavam.
2. **Construtor `Leitor.__init__` (linhas ~20-25).** `criar_driver` estourando
   (driver desconhecido → `ValueError`; porta inexistente → erro de I/O) aborta a
   construção do `Leitor` inteiro no boot, antes de `ler_todos` rodar. Um dispositivo
   ruim impede o hub de subir.

## Objetivo

Falha de um dispositivo (na construção **ou** na leitura) degrada **só aquele
dispositivo**: seus canais viram `sensor_offline`, os demais seguem publicando, o hub
sobe e continua vivo. O operador vê o sensor offline no dashboard (não some
silenciosamente) e uma linha de log com o diagnóstico.

## Fix 1 — Isolamento na leitura (`ler_todos`)

Trocar `except RuntimeError` por `except Exception`. Dispositivo que estoura em
`read_channels` marca **todos os seus canais** como `sensor_offline` (status já
existente, sem novo valor, sem mudança no dashboard/ingestão) e a varredura segue
para o próximo dispositivo. Logar uma vez por falha (ver §Log).

## Fix 2 — Isolamento na construção (`Leitor.__init__`)

Envolver a criação por-dispositivo em try/except:

- Dispositivo que instancia OK → entra em `self._dispositivos` (como hoje).
- Dispositivo que falha ao instanciar → **não** entra em `_dispositivos`; seus canais
  são guardados em `self._degradados` (lista de `CanalConfig`). Logar a falha.

`ler_todos` emite `sensor_offline` para cada canal em `_degradados` a cada ciclo
(decisão do usuário: **emitir**, não omitir — sensor ruim fica visível como offline no
dashboard em vez de sumir).

## Log

Cada falha (construção ou leitura) loga com contexto para diagnóstico: `driver`,
`porta`, `endereco` e a exceção. Seguir o padrão já usado no hub — `print(f"[hub] ...")`
(ver `hub/main.py:38`, `hub/enviador_sftp.py:72`); o hub **não** usa `logging` stdlib,
e esta fatia não introduz essa dependência.

Para evitar spam a cada ciclo de leitura, a falha de **leitura** loga só quando o
dispositivo *entra* em falha (transição ok → falha) e quando se recupera (falha → ok),
não a cada varredura. A falha de **construção** loga uma vez, no boot.

## Fora de escopo (vai para C)

Reportar o erro de volta ao Odoo (status do sensor no servidor, alarme). Por ora é
**só** log local + status `sensor_offline` no dashboard via telemetria normal.

## Testes (TDD)

Usar o padrão existente em `hub/tests/test_leitor.py` (`_BackendFake.criar_driver`,
`_DriverFake`):

1. **Leitura estoura não-RuntimeError.** Driver cujo `read_channels` levanta
   `IndexError` → seus canais ficam `sensor_offline`; um 2º dispositivo bom no mesmo
   config publica normalmente (não é afetado).
2. **Construção falha (driver desconhecido).** `criar_driver` levanta `ValueError`
   para um dispositivo → `Leitor` **constrói** com sucesso; `ler_todos` emite
   `sensor_offline` para os canais desse dispositivo a cada ciclo.
3. **Construção falha + dispositivo bom.** Config com 2 dispositivos, um cuja criação
   estoura e um OK → hub sobe; o bom publica `ok`, o ruim publica `sensor_offline`.
4. **Regressão RuntimeError.** Driver que levanta `RuntimeError` na leitura continua
   marcando `sensor_offline` (comportamento atual preservado).

Rodar: `cd hub && python -m pytest tests/test_leitor.py -q` (confirmar comando real
na execução).

## Arquivos

- `hub/leitor.py` — Fix 1 + Fix 2.
- `hub/tests/test_leitor.py` — novos testes.

Nenhuma mudança no addon Odoo, serializer, ou submódulo nesta fatia.
