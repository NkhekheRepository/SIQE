FROM python:3.11-slim

RUN useradd -m -u 1000 siqe

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R siqe:siqe /app

USER siqe

ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=0

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python3", "main.py"]
