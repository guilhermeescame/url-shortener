FROM python:3.12-slim

WORKDIR /app

# Dependencies before code: preserves the layer cache when only main.py changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# App middleware provides structured access logs; uvicorn's plain ones are disabled
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
