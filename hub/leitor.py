"""Loop de varredura Modbus: lê dispositivos, escala (map) e normaliza.

Uma instância de driver por dispositivo configurado. Dispositivo que não
responde marca todos os seus canais como sensor_offline (varredura continua).
"""
from hub import modbus_backend as _backend_padrao


class _DispositivoLigado:
    def __init__(self, driver, canais):
        self.driver = driver
        self.canais = canais  # list[CanalConfig]


class Leitor:
    def __init__(self, config, backend=_backend_padrao):
        self._config = config
        self._backend = backend
        self._dispositivos = []
        for bus in config.barramentos:
            for disp in bus.dispositivos:
                driver = backend.criar_driver(
                    disp.driver, bus.porta, bus.baud, bus.paridade, bus.stop_bits, disp.endereco,
                )
                self._dispositivos.append(_DispositivoLigado(driver, disp.canais))

    def _specs(self, canais):
        return [
            self._backend.MapSpec(
                channels={c.ch}, in_min=c.map_in[0], in_max=c.map_in[1],
                out_min=c.map_out[0], out_max=c.map_out[1], unit=c.unidade,
            )
            for c in canais
        ]

    def _normalizar(self, canal, valor, status, agora):
        return {
            "timestamp": agora, "sensor_id": canal.sensor_id, "area_id": canal.area_id,
            "tipo_medida": canal.tipo_medida, "valor": valor, "unidade": canal.unidade,
            "protocolo_origem": canal.protocolo_origem, "status_leitura": status,
        }

    def ler_todos(self, agora):
        leituras = []
        for disp in self._dispositivos:
            try:
                lidos = disp.driver.read_channels(maps=self._specs(disp.canais))
                por_canal = {e["channel"]: e for e in lidos}
                for canal in disp.canais:
                    entrada = por_canal.get(canal.ch)
                    if entrada is None:
                        leituras.append(self._normalizar(canal, 0.0, "erro_leitura", agora))
                    else:
                        leituras.append(self._normalizar(canal, float(entrada["value"]), "ok", agora))
            except RuntimeError:
                for canal in disp.canais:
                    leituras.append(self._normalizar(canal, 0.0, "sensor_offline", agora))
        return leituras

    def fechar(self):
        for disp in self._dispositivos:
            try:
                disp.driver.close()
            except Exception:
                pass
