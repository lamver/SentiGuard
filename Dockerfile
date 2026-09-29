FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TLDEXTRACT_CACHE=/opt/tldcache
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -U "pip>=24.3" \
 && pip install --no-cache-dir -r requirements.txt \
 && python -m spacy download en_core_web_sm \
 && python -c "import tldextract; tldextract.extract('a.example.com')"
COPY main.py ./
COPY sentiguard ./sentiguard
COPY tests ./tests
RUN useradd -r -u 10001 app && chown -R app /opt/tldcache
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
