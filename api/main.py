from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import alarmes, auth, historico, meta

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
app.include_router(meta.router)
app.include_router(historico.router)


@app.get('/health')
def health():
    return {'status': 'ok'}
