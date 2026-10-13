FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --uid 10001 --create-home nexo && chown -R nexo:nexo /app
USER nexo
EXPOSE 8000
CMD ["sh", "entrypoint.sh"]
