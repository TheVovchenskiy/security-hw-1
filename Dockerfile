FROM python:3.10-slim as builder

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY config.py .
COPY src/proxy.py src/proxy.py
COPY src/cert_utils.py src/cert_utils.py
COPY certs/ certs/
COPY serial_numbers/ serial_numbers/
COPY ca.crt ca.crt
COPY ca.key ca.key
COPY cert.key cert.key

RUN mkdir db

CMD [ "python3", "main.py" ]
