import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import alarmes, auth, config, config_publish_router, historico, live, live_listener, meta

app = FastAPI(title='Sentinela API')

# Frontend (Vite dev) roda em origem diferente da API — sem isso o browser
# bloqueia a chamada por CORS. Portas fixas de dev (Vite tenta 5173 e sobe
# se ocupada); ajustar/restringir quando houver deploy real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f'http://localhost:{p}' for p in range(5173, 5180)],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(alarmes.router)
app.include_router(auth.router)
app.include_router(config.router)
app.include_router(config_publish_router.router)
app.include_router(meta.router)
app.include_router(historico.router)
app.include_router(live.router)


@app.on_event('startup')
async def _iniciar_live_listener():
    # Guarda a referência em app.state: o event loop só mantém uma
    # referência fraca à task (ver docs de asyncio.create_task) — sem isso
    # o GC recolhe a task quase imediatamente após o startup, matando o
    # listener de NOTIFY silenciosamente (confirmado na verificação real:
    # "Task was destroyed but it is pending!" logo após o startup).
    app.state.live_listener_task = asyncio.create_task(live_listener.escutar())


@app.get('/health')
def health():
    return {'status': 'ok'}
