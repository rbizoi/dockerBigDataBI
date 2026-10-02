FROM python:3.12-slim
RUN pip install --no-cache-dir confluent-kafka==2.11.1 PyYAML==6.0.2
WORKDIR /app
COPY kafka_init.py /app/
ENTRYPOINT ["python", "/app/kafka_init.py"]
