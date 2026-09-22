import json
import os
import time
from datetime import datetime, timezone

import requests
from confluent_kafka import Producer

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")
TOPIC = os.getenv("KAFKA_TOPIC", "opendata.raw")
LOG_TOPIC = os.getenv("LOG_TOPIC", "application.logs")
URL = os.getenv("OPENDATA_URL", "http://mock-opendata:8000/api/events")
POLL = int(os.getenv("POLL_SECONDS", "15"))

producer = Producer({
    "bootstrap.servers": BOOTSTRAP,
    "acks": "all",
    "enable.idempotence": True,
    "retries": 10,
    "linger.ms": 5,
})


def encode(value):
    return json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")


def publish(topic, value, key=None):
    while True:
        try:
            producer.produce(topic, key=key, value=encode(value))
            producer.poll(0)
            return
        except BufferError:
            producer.poll(0.2)


def app_log(level, message, **extra):
    publish(LOG_TOPIC, {
        "@timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "api-producer",
        "level": level,
        "message": message,
        **extra,
    })


while True:
    try:
        response = requests.get(URL, timeout=10)
        response.raise_for_status()
        payload = response.json()
        records = payload if isinstance(payload, list) else payload.get("records", [payload])
        for record in records:
            publish(TOPIC, {
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "source": URL,
                "payload": record,
            })
        app_log("INFO", "OpenData poll completed", record_count=len(records))
        if producer.flush(30) != 0:
            raise RuntimeError("Kafka flush timeout")
    except Exception as exc:
        app_log("ERROR", "OpenData poll failed", error=str(exc))
        producer.flush(30)
    time.sleep(POLL)
