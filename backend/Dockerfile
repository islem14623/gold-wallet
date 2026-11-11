FROM python:3.12-slim

WORKDIR /app 

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt 

COPY apps ./app
COPY alembic.ini .
COPY alembic ./alembic

RUN useradd --create-home appuser 
USER appuser 

EXPOSE 8000 

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

