FROM python:3.10-slim as builder

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY src/ src/
COPY certs/ certs/
COPY serial_numbers/ serial_numbers/
COPY ca.crt ca.crt
COPY ca.key ca.key
COPY cert.key cert.key

CMD [ "python3", "main.py" ]
