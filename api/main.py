import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import auth, historico, live, live_listener, meta

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

app.include_router(auth.router)
app.include_router(meta.router)
app.include_router(historico.router)
app.include_router(live.router)


@app.on_event('startup')
async def _iniciar_live_listener():
    asyncio.create_task(live_listener.escutar())


@app.get('/health')
def health():
    return {'status': 'ok'}
