"""Detector de alarme na borda: por sensor, com histerese, avalia cruzamento
de limiar SÓ em leitura "ok" (gate de plausibilidade fica no leitor). Estado
por sensor persistido em disco para sobreviver a restart sem re-emitir entrada.
"""
import json
from pathlib import Path


class DetectorAlarme:
    def __init__(self, limites, n=3, margem=0.0, estado_path=None):
        self._limites = limites or {}
        self._n = n
        self._margem = margem
        self._estado_path = estado_path
        # estado[sensor_id] = {"em_alarme": bool, "tipo_violacao": str|None, "contador": int}
        self._estado = {}
        self._carregar()

    def _carregar(self):
        if not self._estado_path:
            return
        p = Path(self._estado_path).expanduser()
        if p.exists():
            try:
                self._estado = json.loads(p.read_text())
            except (ValueError, OSError):
                self._estado = {}

    def _salvar(self):
        if not self._estado_path:
            return
        p = Path(self._estado_path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self._estado))

    def _st(self, sensor_id):
        return self._estado.setdefault(
            sensor_id, {"em_alarme": False, "tipo_violacao": None, "contador": 0})

    def avaliar(self, leitura):
        sensor_id = leitura["sensor_id"]
        limite = self._limites.get(sensor_id)
        if limite is None:
            return []
        if leitura.get("status_leitura") != "ok":
            return []  # gate de plausibilidade: leitura suspeita não carrega info

        lmin, lmax = limite.get("min"), limite.get("max")
        valor = leitura["valor"]
        st = self._st(sensor_id)

        if st["em_alarme"]:
            dentro_com_folga = (
                (lmax is None or valor < lmax - self._margem)
                and (lmin is None or valor > lmin + self._margem)
            )
            if dentro_com_folga:
                st["em_alarme"] = False
                tipo_violacao = st["tipo_violacao"]
                st["tipo_violacao"] = None
                st["contador"] = 0
                self._salvar()
                return [self._evento(leitura, "saida_alarme", tipo_violacao, lmin, lmax)]
            return []

        acima = lmax is not None and valor > lmax
        abaixo = lmin is not None and valor < lmin
        if not (acima or abaixo):
            st["contador"] = 0
            return []
        st["contador"] += 1
        if st["contador"] < self._n:
            return []
        st["em_alarme"] = True
        st["tipo_violacao"] = "acima_limite" if acima else "abaixo_limite"
        st["contador"] = 0
        self._salvar()
        return [self._evento(leitura, "entrada_alarme", st["tipo_violacao"], lmin, lmax)]

    @staticmethod
    def _evento(leitura, tipo_evento, tipo_violacao, lmin, lmax):
        return {
            "sensor_id": leitura["sensor_id"], "area_id": leitura["area_id"],
            "tipo_medida": leitura["tipo_medida"], "timestamp": leitura["timestamp"],
            "tipo_evento": tipo_evento, "tipo_violacao": tipo_violacao,
            "valor": leitura["valor"], "limite_min_vigente": lmin, "limite_max_vigente": lmax,
        }
