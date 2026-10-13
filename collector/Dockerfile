FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends iputils-ping snmp && rm -rf /var/lib/apt/lists/*
WORKDIR /collector
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent.py .
RUN useradd --uid 10001 --create-home nexo
USER nexo
CMD ["python", "agent.py"]
