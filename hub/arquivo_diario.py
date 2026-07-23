"""Escritor do arquivo .txt diário de leituras, no formato congelado.

Uma linha por leitura, hash encadeado interno ao dia; selagem diária assina
o hash_final. Cadeia reinicia a cada dia. Recupera no boot dias passados que
ficaram sem rodapé (crash antes de selar).
"""
import base64
import glob
import os
from datetime import date
from pathlib import Path

from contrato import formato


def reconstruir_estado(texto):
    """A partir do conteúdo (cabeçalho + hdr_sig + N linhas, sem rodapé),
    devolve (hash_atual, proximo_seq)."""
    linhas = [l for l in texto.split("\n") if l != ""]
    cabecalho = [l for l in linhas
                 if l.startswith("#") and not l.startswith("# hdr_sig:")]
    corpo = [l for l in linhas if not l.startswith("#")]
    hash_atual = formato.hash_seed("\n".join(cabecalho) + "\n")
    for linha in corpo:
        sem_hash = linha.rsplit("|", 2)[0]  # tira hash E sig
        hash_atual = formato.hash_linha(hash_atual, sem_hash)
    return hash_atual, len(corpo) + 1


def _esta_selado(caminho):
    return caminho.exists() and "\n# assinatura:" in caminho.read_text()


class ArquivoDiario:
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
        # O segmento {hub}-{coletor} do nome é redundância LEGÍVEL (conveniência
        # de operador ao olhar um diretório), não metadado: hub_id e coletor_id
        # podem conter '-', então o nome não é reversível sem ambiguidade. O
        # cabeçalho interno, assinado, é a única verdade — não escreva parser
        # reverso em cima deste segmento.
        nome = f"{data_referencia}_{self._hub_id}-{self._coletor_id}_leituras.txt"
        return self._dir / nome

    def _abrir(self, data_referencia):
        self._dir.mkdir(parents=True, exist_ok=True)
        caminho = self.caminho(data_referencia)
        if caminho.exists():                       # retoma arquivo do dia corrente
            self._hash, self._seq = reconstruir_estado(caminho.read_text())
        else:
            cabecalho = formato.montar_cabecalho(
                "leituras", self._coletor_id, self._hub_id,
                self._assinador.fingerprint(), data_referencia,
                self._tz_offset, self._firmware, self._cliente_id, self._site_id,
            )
            self._hash = formato.hash_seed(cabecalho)
            hdr_sig = base64.b64encode(self._assinador.assinar(self._hash.encode())).decode()
            caminho.write_text(cabecalho + f"# hdr_sig: {hdr_sig}\n")
            self._seq = 1
        self._data_atual = data_referencia

    def registrar(self, leitura):
        data_referencia = leitura["timestamp"].date().isoformat()
        if self._data_atual is not None and data_referencia != self._data_atual:
            self.selar(self._data_atual)
            self._data_atual = None
        if self._data_atual is None:
            self._abrir(data_referencia)
        ts = leitura["timestamp"].isoformat(timespec="seconds")
        linha, self._hash = formato.gerar_linha_leitura(
            self._hash, self._seq, ts, leitura["sensor_id"], leitura["area_id"],
            leitura["tipo_medida"], leitura["valor"], leitura["unidade"],
            leitura["protocolo_origem"], leitura["status_leitura"],
            leitura["cert_ver"], leitura["cal_ganho"], leitura["cal_offset"],
        )
        sig = base64.b64encode(self._assinador.assinar(self._hash.encode())).decode()
        with self.caminho(data_referencia).open("a") as fh:
            fh.write(linha + "|" + sig + "\n")
        self._seq += 1

    def selar(self, data_referencia=None, caminho=None):
        # `caminho` explícito: quem JÁ localizou o arquivo em disco (ex.
        # recuperar_pendentes, que faz glob) passa o caminho real. Reconstruir
        # via self.caminho() descartaria essa informação e erraria o alvo em
        # qualquer arquivo cujo nome não seja o formato corrente (acervo legado),
        # selando nada e em silêncio. Sem `caminho`, mantém o comportamento
        # anterior (dia corrente / virada de dia / shutdown).
        data_referencia = data_referencia or self._data_atual
        if data_referencia is None:
            return
        caminho = Path(caminho) if caminho is not None else self.caminho(data_referencia)
        if _esta_selado(caminho) or not caminho.exists():
            return
        hash_final, proximo_seq = reconstruir_estado(caminho.read_text())
        assinatura = base64.b64encode(self._assinador.assinar(hash_final.encode())).decode()
        rodape = formato.montar_rodape(proximo_seq - 1, hash_final, assinatura, "total_linhas")
        with caminho.open("a") as fh:
            fh.write(rodape)

    def recuperar_pendentes(self, hoje: date):
        for nome in glob.glob(str(self._dir / "*_leituras.txt")):
            data_str = os.path.basename(nome)[:10]
            if date.fromisoformat(data_str) < hoje and not _esta_selado(Path(nome)):
                self.selar(data_str, caminho=Path(nome))
