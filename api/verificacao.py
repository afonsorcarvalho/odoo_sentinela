"""Verificação de upload: descompacta zip (com guards) e roda o verificador.
Camada sync + fila/worker assíncrona (Gestor) para desacoplar do event loop.
"""
import asyncio
import io
import time
import uuid
import zipfile
from dataclasses import dataclass
from typing import Callable, Optional

from ingestao import verificador

from .verificacao_chaves import chaves_do_odoo

UPLOAD_MAX = 25 * 1024 * 1024
DESCOMPRIMIDO_MAX = 200 * 1024 * 1024
ARQUIVOS_MAX = 500

FILA_MAX = 50
CONCORRENCIA_N = 2
TTL_RESULTADO_S = 600


class LimiteExcedido(Exception):
    pass


class FilaCheia(Exception):
    pass


def coletar(nome_upload, dados):
    if not nome_upload.lower().endswith('.zip'):
        return [(nome_upload, dados)]
    itens = []
    total = 0
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        infos = [i for i in z.infolist() if not i.is_dir()
                 and not i.filename.lower().endswith('.zip')]  # ignora aninhado
        if len(infos) > ARQUIVOS_MAX:
            raise LimiteExcedido(f'zip com mais de {ARQUIVOS_MAX} arquivos')
        for info in infos:
            restante = DESCOMPRIMIDO_MAX - total
            with z.open(info) as f:
                conteudo = f.read(restante + 1)  # leitura limitada: nunca decomprime alem do orcamento
            if len(conteudo) > restante:
                raise LimiteExcedido('conteúdo descomprimido excede o limite')
            total += len(conteudo)
            itens.append((info.filename, conteudo))
    return itens


def verificar_upload(nome_upload, dados, chaves_pem=None):
    itens = coletar(nome_upload, dados)
    return verificador.verificar_itens(itens, chaves_pem=chaves_pem or chaves_do_odoo())


@dataclass
class Job:
    id: str
    estado: str = 'fila'
    posicao: int = 0
    criado_em: float = 0.0
    expira_em: Optional[float] = None
    lote: object = None
    erro: Optional[str] = None


class Gestor:
    """Fila assíncrona: worker pool com concorrência N (Semaphore), backpressure
    via profundidade máxima (FilaCheia) e sweep de TTL para resultados prontos/erro.
    Verificação CPU-bound roda fora do event loop via asyncio.to_thread.
    """

    def __init__(self, agora: Callable[[], float] = time.monotonic):
        self._agora = agora
        self._jobs = {}
        self._fila = asyncio.Queue()
        self._sem = asyncio.Semaphore(CONCORRENCIA_N)
        self._tarefas = []
        self._rodando = False

    def enfileirar(self, nome, dados):
        pendentes = sum(1 for j in self._jobs.values() if j.estado == 'fila')
        if pendentes >= FILA_MAX:
            raise FilaCheia('fila cheia')
        job = Job(id=uuid.uuid4().hex, criado_em=self._agora(), posicao=pendentes + 1)
        self._jobs[job.id] = job
        self._fila.put_nowait((job, nome, dados))
        return job

    def obter(self, job_id):
        return self._jobs.get(job_id)

    def varrer_expirados(self):
        agora = self._agora()
        for jid in [j.id for j in self._jobs.values()
                    if j.expira_em is not None and j.expira_em <= agora]:
            del self._jobs[jid]

    async def start(self):
        self._rodando = True
        self._tarefas = [asyncio.create_task(self._loop()) for _ in range(CONCORRENCIA_N)]

    async def stop(self):
        self._rodando = False
        for t in self._tarefas:
            t.cancel()
        self._tarefas = []

    async def _loop(self):
        while self._rodando:
            try:
                job, nome, dados = await asyncio.wait_for(self._fila.get(), timeout=0.2)
            except asyncio.TimeoutError:
                self.varrer_expirados()
                continue
            async with self._sem:
                job.estado = 'processando'
                try:
                    job.lote = await asyncio.to_thread(verificar_upload, nome, dados)
                    job.estado = 'pronto'
                except Exception as exc:  # LimiteExcedido, BadZipFile, etc.
                    job.estado = 'erro'
                    job.erro = str(exc)
                job.expira_em = self._agora() + TTL_RESULTADO_S
