from fastapi import FastAPI

from . import auth, historico, meta

app = FastAPI(title='Sentinela API')
app.include_router(auth.router)
app.include_router(meta.router)
app.include_router(historico.router)


@app.get('/health')
def health():
    return {'status': 'ok'}
