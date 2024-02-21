FROM python:3.10-slim as builder

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY src/ src/

# EXPOSE 8080

CMD [ "python3", "main.py" ]
