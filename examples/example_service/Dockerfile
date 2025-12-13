FROM python:3.11-slim

ARG VERSION=dev
ENV VERSION=${VERSION}

WORKDIR /app
COPY app.py /app/app.py

RUN pip install --no-cache-dir fastapi==0.115.5 uvicorn==0.32.1

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
