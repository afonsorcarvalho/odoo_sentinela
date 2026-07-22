"""Split identidade local (identity.yaml) vs operacional baixado, e merge -> config.yaml efetivo."""
from pathlib import Path

import yaml


def carregar_identidade(caminho):
    return yaml.safe_load(Path(caminho).expanduser().read_text())


def fundir(identidade, operacional):
    merged = dict(identidade)
    merged['intervalo_leitura_s'] = operacional['intervalo_leitura_s']
    merged['barramentos'] = operacional['barramentos']
    return merged


def escrever_config_efetivo(merged, caminho):
    Path(caminho).expanduser().write_text(
        yaml.safe_dump(merged, sort_keys=False, allow_unicode=True))
