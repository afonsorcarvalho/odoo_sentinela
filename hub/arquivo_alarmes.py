"""Escritor do .txt diário de ALARMES (eventos entrada/saida), no formato
congelado. Espelha ArquivoDiario (hash encadeado por dia, selagem diária,
recuperação no boot) mas para eventos esparsos de alarme. Reusa as funções de
módulo reconstruir_estado/_esta_selado de arquivo_diario.
"""
import base64
import glob
import os
from datetime import date
from pathlib import Path

from contrato import formato
from hub.arquivo_diario import _esta_selado, reconstruir_estado


class ArquivoAlarmes:
    def __init__(self, coletor_id, hub_id, firmware_version, timezone_offset,
                 caminho_dados, assinador, cliente_id='', site_id=''):
        self._coletor_id = coletor_id
        self._hub_id = hub_id
        self._firmware = firmware_version
        self._tz_offset = timezone_offset
        self._cliente_id = cliente_id
        self._site_id = site_id
        self._dir = Path(caminho_dados).expanduser() / coletor_id
        self._assinador = assinador
        self._data_atual = None
        self._hash = None
        self._seq = 1

    def caminho(self, data_referencia):
        nome = f"{data_referencia}_{self._hub_id}-{self._coletor_id}_alarmes.txt"
        return self._dir / nome

    def _abrir(self, data_referencia):
        self._dir.mkdir(parents=True, exist_ok=True)
        caminho = self.caminho(data_referencia)
        if caminho.exists():
            self._hash, self._seq = reconstruir_estado(caminho.read_text())
        else:
            cabecalho = formato.montar_cabecalho(
                "alarmes", self._coletor_id, self._hub_id,
                self._assinador.fingerprint(), data_referencia,
                self._tz_offset, self._firmware, self._cliente_id, self._site_id,
            )
            self._hash = formato.hash_seed(cabecalho)
            hdr_sig = base64.b64encode(self._assinador.assinar(self._hash.encode())).decode()
            caminho.write_text(cabecalho + f"# hdr_sig: {hdr_sig}\n")
            self._seq = 1
        self._data_atual = data_referencia

    def registrar_evento(self, evento):
        data_referencia = evento["timestamp"].date().isoformat()
        if self._data_atual is not None and data_referencia != self._data_atual:
            self.selar(self._data_atual)
            self._data_atual = None
        if self._data_atual is None:
            self._abrir(data_referencia)
        ts = evento["timestamp"].isoformat(timespec="seconds")
        linha, self._hash = formato.gerar_linha_alarme(
            self._hash, self._seq, ts, evento["sensor_id"], evento["area_id"],
            evento["tipo_medida"], evento["tipo_evento"], evento["tipo_violacao"],
            evento["valor"], evento["limite_min_vigente"], evento["limite_max_vigente"],
        )
        sig = base64.b64encode(self._assinador.assinar(self._hash.encode())).decode()
        with self.caminho(data_referencia).open("a") as fh:
            fh.write(linha + "|" + sig + "\n")
        self._seq += 1

    def selar(self, data_referencia=None, caminho=None):
        data_referencia = data_referencia or self._data_atual
        if data_referencia is None:
            return
        caminho = Path(caminho) if caminho is not None else self.caminho(data_referencia)
        if _esta_selado(caminho) or not caminho.exists():
            return
        hash_final, proximo_seq = reconstruir_estado(caminho.read_text())
        assinatura = base64.b64encode(self._assinador.assinar(hash_final.encode())).decode()
        rodape = formato.montar_rodape(proximo_seq - 1, hash_final, assinatura, "total_eventos")
        with caminho.open("a") as fh:
            fh.write(rodape)

    def recuperar_pendentes(self, hoje: date):
        for nome in glob.glob(str(self._dir / "*_alarmes.txt")):
            data_str = os.path.basename(nome)[:10]
            if date.fromisoformat(data_str) < hoje and not _esta_selado(Path(nome)):
                self.selar(data_str, caminho=Path(nome))
