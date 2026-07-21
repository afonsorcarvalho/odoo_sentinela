---
name: leitura-n4
description: >
  Faz leituras de teste do coletor analógico N4AIB16 (Modbus RTU sobre RS-485)
  do projeto Sentinela. Use SEMPRE que o usuário pedir para "fazer uma leitura",
  "ler o n4 / N4AIB16", "testar o coletor / o módulo / os canais", "ver os
  sinais / correntes / mA na USB", "watch" de um canal, ou avaliar ruído de um
  sinal — mesmo que ele não diga "n4" explicitamente, se o contexto for ler o
  módulo analógico na porta serial. Cobre leitura única, contínua (watch),
  estatística (média/desvio) e escala física (mA -> grandeza de engenharia),
  em qualquer endereço do barramento.
---

# Leitura de teste do coletor N4AIB16

O N4AIB16 é um módulo analógico → RS-485 (Modbus RTU): **CH1..CH15** são
entradas de corrente (0-20 / 4-20 mA), **CH16** é tensão (0-30 V). Uma
transação lê os 16 canais de uma vez. Ele responde por **FC04 (input
registers)** e o valor já vem em centésimos de mA (300 bruto = 3,00 mA).

Toda leitura passa pelo wrapper `scripts/ler_n4.sh`, que fixa o venv, o caminho
do driver e os defaults, e dá erros amigáveis de porta/permissão. **Prefira o
script** a chamar o driver na mão — assim porta/baud ficam num lugar só.

## Defaults

Porta `/dev/ttyUSB0`, endereço `1`, baud `9600`. São os valores da bancada de
teste; só passe flag quando o usuário indicar diferente.

## Escolha do modo

Rode a partir da raiz do projeto (`/home/fitadigital/odoo_sentinela`).

| O usuário quer… | Comando |
|---|---|
| uma leitura / "faz uma leitura" | `scripts/ler_n4.sh` |
| ler outro módulo do barramento | `scripts/ler_n4.sh -a 2` |
| acompanhar um sinal variando | `scripts/ler_n4.sh watch` (Ctrl+C p/ parar) |
| avaliar ruído / estabilidade | `scripts/ler_n4.sh stats` (20 amostras; `-n N` p/ mudar) |
| ver em unidade física | `scripts/ler_n4.sh map 1:4:20:-50:150:C` |
| saída para script/JSON | acrescente `--json` |

Flags: `-p PORTA` `-a ENDERECO` `-b BAUD` `-n AMOSTRAS`. A spec do `map` é
`CANAIS:IN_MIN:IN_MAX:OUT_MIN:OUT_MAX[:UNIDADE]` (ex.: `1,3:4:20:0:100:%` aplica
a CH1 e CH3). Tudo após `--` é repassado cru ao driver (`--current-mode 4-20`,
`--reject`, `--ewma`, etc.).

**`watch` não termina sozinho** — precisa de Ctrl+C. Não o rode de forma
bloqueante esperando que retorne; use `run_in_background` ou combine com um
limite, e avise o usuário que fica lendo até parar.

## Como ler o resultado

Reporte de forma enxuta, destacando o que importa em vez de despejar os 16
canais quando quase todos são zero:

- **Canais ativos** (valor ≠ 0) — é o sinal real presente. Numa bancada típica
  só um ou dois canais têm transmissor ligado.
- **Canais em 0.0** — sem transmissor / laço aberto. Normal; resuma como
  "CH3–CH16 em zero" em vez de listar um a um.
- **`stats`**: `s` é o desvio-padrão e `u` a incerteza do valor, na unidade do
  canal. `s` baixo (centésimos de mA) = sinal estável; `s` alto = ruído,
  vale investigar aterramento/blindagem ou usar `--reject`/`--ewma`.
- **`map`**: mostra o valor de engenharia e, entre parênteses, o mA físico
  preservado — confira se a conversão bate com o esperado.

## Quando algo falha

- **`porta … não existe`**: o script lista as portas e caminhos `by-id`. A USB
  pode ter reenumerado (`ttyUSB1`) — releia com `-p`, ou use o caminho estável
  `by-id` para não depender do número.
- **`sem permissão`**: o usuário precisa estar no grupo `dialout`
  (`sudo usermod -aG dialout $USER`, depois relogar).
- **`Falha ao ler … / sensor_offline`**: módulo não respondeu. Confira
  endereço (`-a`), fiação A/B do RS-485 e alimentação. Endereço errado é a
  causa mais comum quando há vários módulos no barramento.
- **Todos os canais em 0**: pode ser leitura boa (nada conectado) ou o módulo
  errado no endereço. Confirme com o usuário o que deveria estar ligado.
