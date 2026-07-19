from fastapi import FastAPI

from . import auth, meta

app = FastAPI(title='Sentinela API')
app.include_router(auth.router)
app.include_router(meta.router)


@app.get('/health')
def health():
    return {'status': 'ok'}
