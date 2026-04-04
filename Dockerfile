FROM python:3.13-slim

LABEL description="CFTV Dashboard - Simulador e Painel Web"
LABEL maintainer="SIMULA-O-CFTV"

WORKDIR /app

# Copiar arquivos do projeto
COPY requirements.txt .
COPY simulador_cftv.py .
COPY servidor_web_cftv.py .
COPY web/ ./web/
COPY tests/ ./tests/

# Instalar dependências
RUN pip install --no-cache-dir -q -r requirements.txt || true

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=2 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz', timeout=3)" || exit 1

# Ports
EXPOSE 8080

# Default command
CMD ["python", "servidor_web_cftv.py", "--host", "0.0.0.0", "--port", "8080"]
