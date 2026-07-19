from fastapi import FastAPI

app = FastAPI(title='Sentinela API')


@app.get('/health')
def health():
    return {'status': 'ok'}
