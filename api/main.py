from fastapi import FastAPI

from . import auth

app = FastAPI(title='Sentinela API')
app.include_router(auth.router)


@app.get('/health')
def health():
    return {'status': 'ok'}
