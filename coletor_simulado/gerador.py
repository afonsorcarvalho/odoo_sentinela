import argparse
import base64
import random
from datetime import date as date_cls, datetime, timedelta
from pathlib import Path

from contrato import formato, identidade

SENSORES = [
    {'sensor_id': 'SNR-SIM-TEMP-01', 'tipo_medida': 'temperatura', 'unidade': 'C'},
    {'sensor_id': 'SNR-SIM-PRES-01', 'tipo_medida': 'pressao_diferencial', 'unidade': 'Pa'},
]
AREA_ID = 'EXPURGO'
COLETOR_ID = 'COL-SIM-0001'
HUB_ID = 'HUB-SIM-0001'
PROTOCOLO_ORIGEM = '4-20mA'
FIRMWARE_VERSION = '0.1.0-sim'
TIMEZONE_OFFSET = '-03:00'
LIMITE_MIN_PRESSAO_VIGENTE = None
LIMITE_MAX_PRESSAO_VIGENTE = -2.5
MINUTO_INICIO_ALARME = 120  # 02:00
MINUTO_FIM_ALARME = 127  # 02:07 (primeiro minuto de volta ao normal)


def _timestamp(data, minuto):
    dt = datetime.combine(data, datetime.min.time()) + timedelta(minutes=minuto)
    return dt.strftime('%Y-%m-%dT%H:%M:%S') + TIMEZONE_OFFSET


def _valor_para_sensor(sensor, minuto, injetar_alarme):
    if sensor['tipo_medida'] == 'temperatura':
        return round(random.gauss(20.0, 0.6), 1)
    if injetar_alarme and MINUTO_INICIO_ALARME <= minuto < MINUTO_FIM_ALARME:
        return round(random.gauss(1.0, 0.1), 1)
    return round(random.gauss(-3.5, 0.3), 1)


def montar_corpo_leituras(cabecalho, data, injetar_alarme=False):
    hash_atual = formato.hash_seed(cabecalho)
    linhas = []
    seq = 1
    for minuto in range(24 * 60):
        timestamp = _timestamp(data, minuto)
        for sensor in SENSORES:
            valor = _valor_para_sensor(sensor, minuto, injetar_alarme)
            linha, hash_atual = formato.gerar_linha_leitura(
                hash_atual, seq, timestamp, sensor['sensor_id'], AREA_ID,
                sensor['tipo_medida'], valor, sensor['unidade'], PROTOCOLO_ORIGEM, 'ok',
            )
            linhas.append(linha)
            seq += 1
    return linhas, hash_atual


def montar_corpo_alarmes(cabecalho, data, injetar_alarme=False):
    hash_atual = formato.hash_seed(cabecalho)
    linhas = []
    if not injetar_alarme:
        return linhas, hash_atual
    sensor_pressao = SENSORES[1]
    linha1, hash_atual = formato.gerar_linha_alarme(
        hash_atual, 1, _timestamp(data, MINUTO_INICIO_ALARME), sensor_pressao['sensor_id'], AREA_ID,
        sensor_pressao['tipo_medida'], 'entrada_alarme', 'acima_limite', 1.0,
        LIMITE_MIN_PRESSAO_VIGENTE, LIMITE_MAX_PRESSAO_VIGENTE,
    )
    linhas.append(linha1)
    linha2, hash_atual = formato.gerar_linha_alarme(
        hash_atual, 2, _timestamp(data, MINUTO_FIM_ALARME), sensor_pressao['sensor_id'], AREA_ID,
        sensor_pressao['tipo_medida'], 'saida_alarme', 'acima_limite', -3.5,
        LIMITE_MIN_PRESSAO_VIGENTE, LIMITE_MAX_PRESSAO_VIGENTE,
    )
    linhas.append(linha2)
    return linhas, hash_atual


def gerar_dia(data, output_dir, injetar_alarme=False, chave_path=None):
    chave_path = Path(chave_path) if chave_path else Path(__file__).parent / 'identidade' / 'coletor_privkey.pem'
    chave = identidade.carregar_ou_criar_chave(chave_path)
    fingerprint = identidade.fingerprint_publica(chave)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    geradores_de_corpo = (
        ('leituras', montar_corpo_leituras, 'total_linhas'),
        ('alarmes', montar_corpo_alarmes, 'total_eventos'),
    )
    for tipo_arquivo, montar_corpo, campo_total in geradores_de_corpo:
        cabecalho = formato.montar_cabecalho(
            tipo_arquivo, COLETOR_ID, HUB_ID, fingerprint,
            data.isoformat(), TIMEZONE_OFFSET, FIRMWARE_VERSION,
        )
        linhas, hash_final = montar_corpo(cabecalho, data, injetar_alarme)
        assinatura = identidade.assinar(chave, hash_final.encode())
        assinatura_b64 = base64.b64encode(assinatura).decode()
        rodape = formato.montar_rodape(len(linhas), hash_final, assinatura_b64, campo_total)
        corpo = '\n'.join(linhas) + ('\n' if linhas else '')
        conteudo = cabecalho + corpo + rodape
        nome_arquivo = f"{COLETOR_ID}_{tipo_arquivo}_{data.isoformat()}.txt"
        (output_dir / nome_arquivo).write_text(conteudo)
    return output_dir


def main():
    parser = argparse.ArgumentParser(description='Coletor simulado — gera arquivos assinados de leituras/alarmes')
    parser.add_argument('--data', type=str, default=None, help='YYYY-MM-DD (default: hoje)')
    parser.add_argument('--output-dir', type=str, default='./output')
    parser.add_argument('--injetar-alarme', action='store_true')
    args = parser.parse_args()
    data = date_cls.fromisoformat(args.data) if args.data else date_cls.today()
    chave_path = Path(__file__).parent / 'identidade' / 'coletor_privkey.pem'
    chave = identidade.carregar_ou_criar_chave(chave_path)
    fingerprint = identidade.fingerprint_publica(chave)
    output_dir = gerar_dia(data, args.output_dir, args.injetar_alarme, chave_path=chave_path)
    print(f"Fingerprint da chave pública: {fingerprint}")
    print(f"Arquivos gerados em {output_dir}")


if __name__ == '__main__':
    main()
