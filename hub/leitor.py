"""Loop de varredura Modbus: lê dispositivos, escala (map) e normaliza.

Uma instância de driver por dispositivo configurado. Dispositivo que não
responde marca todos os seus canais como sensor_offline (varredura continua).
"""
from hub import modbus_backend as _backend_padrao


class _DispositivoLigado:
    def __init__(self, driver, canais, driver_nome, porta, endereco, recriar, n, m, k):
        self.driver = driver
        self.canais = canais  # list[CanalConfig]
        self.driver_nome = driver_nome
        self.porta = porta
        self.endereco = endereco
        self.recriar = recriar          # callable() -> novo driver
        self.n, self.m, self.k = n, m, k
        self.falhas_seguidas = 0
        self.reconexoes = 0
        self.cooldown = 0               # >0 = em cooldown, conta ciclos ate retry


class Leitor:
    def __init__(self, config, backend=_backend_padrao):
        self._config = config
        self._backend = backend
        self._dispositivos = []
        self._falhados = set()
        for bus in config.barramentos:
            for disp in bus.dispositivos:
                registros = [
                    {'ch': c.ch, **c.registro} for c in disp.canais if c.registro
                ] or None

                def _fazer_recriar(disp=disp, bus=bus, registros=registros):
                    return backend.criar_driver(
                        disp.driver, bus.porta, bus.baud, bus.paridade, bus.stop_bits,
                        disp.endereco, registros=registros,
                    )
                ligado = _DispositivoLigado(
                    None, disp.canais, disp.driver, bus.porta, disp.endereco,
                    recriar=_fazer_recriar,
                    n=disp.reconexao_n, m=disp.reconexao_m, k=disp.reconexao_k,
                )
                try:
                    ligado.driver = _fazer_recriar()
                except Exception as e:
                    # Degradado, mas não para sempre: a porta pode aparecer depois
                    # do boot (adaptador USB enumera tarde). cooldown=1 retenta no
                    # 1º ciclo; falhando, o caminho normal de recriar põe cooldown k.
                    print(f"[hub] dispositivo nao instanciou, degradado: "
                          f"driver={disp.driver!r} porta={bus.porta} endereco={disp.endereco} erro={e!r}")
                    ligado.cooldown = 1
                self._dispositivos.append(ligado)

    def _specs(self, canais):
        return [
            self._backend.MapSpec(
                channels={c.ch}, in_min=c.map_in[0], in_max=c.map_in[1],
                out_min=c.map_out[0], out_max=c.map_out[1], unit=c.unidade,
            )
            for c in canais
            if c.map_in is not None and c.map_out is not None
        ]

    def _normalizar(self, canal, valor, status, agora):
        cal = canal.calibracao or {'cert_ver': 0, 'ganho': 1.0, 'offset': 0.0}
        corrigido = cal['ganho'] * valor + cal['offset']
        return {
            "timestamp": agora, "sensor_id": canal.sensor_id, "area_id": canal.area_id,
            "tipo_medida": canal.tipo_medida, "valor": corrigido, "unidade": canal.unidade,
            "protocolo_origem": canal.protocolo_origem, "status_leitura": status,
            "cert_ver": cal['cert_ver'], "cal_ganho": cal['ganho'], "cal_offset": cal['offset'],
        }

    @staticmethod
    def _fora_da_faixa(canal, valor):
        if canal.faixa_min is not None and valor < canal.faixa_min:
            return True
        if canal.faixa_max is not None and valor > canal.faixa_max:
            return True
        return False

    def _ler_device(self, disp, agora):
        try:
            lidos = disp.driver.ler(maps=self._specs(disp.canais))
            por_canal = {e["channel"]: e for e in lidos}
            out, ruim = [], False
            for canal in disp.canais:
                entrada = por_canal.get(canal.ch)
                if entrada is None:
                    out.append(self._normalizar(canal, 0.0, "erro_leitura", agora)); ruim = True
                else:
                    norm = self._normalizar(canal, float(entrada["value"]), "ok", agora)
                    if self._fora_da_faixa(canal, norm["valor"]):
                        norm["status_leitura"] = "suspeito"; ruim = True
                    out.append(norm)
            chave = id(disp)
            if not ruim and chave in self._falhados:
                sensor_id = disp.canais[0].sensor_id if disp.canais else '?'
                print(f"[hub] leitura recuperada: "
                      f"driver={disp.driver_nome} porta={disp.porta} endereco={disp.endereco} "
                      f"sensor={sensor_id}")
                self._falhados.discard(chave)
            return out, ruim
        except Exception as e:
            chave = id(disp)
            sensor_id = disp.canais[0].sensor_id if disp.canais else '?'
            if chave not in self._falhados:
                self._falhados.add(chave)
                print(f"[hub] leitura falhou, dispositivo offline: "
                      f"driver={disp.driver_nome} porta={disp.porta} endereco={disp.endereco} "
                      f"sensor={sensor_id} erro={e!r}")
            return [self._normalizar(c, 0.0, "sensor_offline", agora) for c in disp.canais], True

    def _tentar_recriar(self, disp):
        try:
            disp.driver.close()
        except Exception:
            pass
        try:
            disp.driver = disp.recriar()
            print(f"[hub] serial reconectado: porta={disp.porta} endereco={disp.endereco}")
            return True
        except Exception as e:
            print(f"[hub] falha ao reconectar: porta={disp.porta} endereco={disp.endereco} erro={e!r}")
            return False

    def ler_todos(self, agora):
        leituras = []
        for disp in self._dispositivos:
            if disp.cooldown > 0:
                disp.cooldown -= 1
                if disp.cooldown > 0:
                    for canal in disp.canais:
                        leituras.append(self._normalizar(canal, 0.0, "sensor_offline", agora))
                    continue
                # cooldown expirou: tenta recriar antes de ler
                if not self._tentar_recriar(disp):
                    disp.cooldown = disp.k
                    for canal in disp.canais:
                        leituras.append(self._normalizar(canal, 0.0, "sensor_offline", agora))
                    continue

            leituras_disp, ciclo_ruim = self._ler_device(disp, agora)
            leituras.extend(leituras_disp)

            if ciclo_ruim:
                disp.falhas_seguidas += 1
                if disp.falhas_seguidas >= disp.n:
                    disp.falhas_seguidas = 0
                    disp.reconexoes += 1
                    if disp.reconexoes > disp.m:
                        disp.reconexoes = 0
                        disp.cooldown = disp.k
                        print(f"[hub] device em cooldown apos {disp.m} reconexoes: "
                              f"porta={disp.porta} endereco={disp.endereco}")
                    else:
                        self._tentar_recriar(disp)
            else:
                disp.falhas_seguidas = 0
                disp.reconexoes = 0
        return leituras

    def fechar(self):
        for disp in self._dispositivos:
            try:
                disp.driver.close()
            except Exception:
                pass
