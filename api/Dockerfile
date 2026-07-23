# API FastAPI do Sentinela (rota de config-publish + histórico + live).
# Deps instaladas no build; código montado via compose (dev) em /app.
FROM python:3.11-slim
WORKDIR /app
COPY api/requirements.txt /tmp/api-requirements.txt
COPY ingestao/requirements.txt /tmp/ingestao-requirements.txt
RUN pip install --no-cache-dir \
      -r /tmp/api-requirements.txt \
      -r /tmp/ingestao-requirements.txt \
      pyyaml
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
