import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from confluent_kafka import Producer

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")
TOPIC = os.getenv("KAFKA_TOPIC", "web.logs.raw")
LOG_TOPIC = os.getenv("LOG_TOPIC", "application.logs")
DATA_DIR = Path(os.getenv("LOG_DATA_DIR", "/data/logs"))
DELAY_MS = int(os.getenv("LOG_DELAY_MS", "0"))
producer = Producer({
    "bootstrap.servers": BOOTSTRAP,
    "acks": "all",
    "enable.idempotence": True,
    "retries": 10,
})


def publish(topic, record, key=None):
    payload = json.dumps(record, ensure_ascii=False, default=str).encode("utf-8")
    while True:
        try:
            producer.produce(topic, key=key, value=payload)
            producer.poll(0)
            return
        except BufferError:
            producer.poll(0.2)


def publish_file(filename, log_type):
    path = DATA_DIR / filename
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            message = raw.rstrip("\r\n")
            if not message:
                continue
            publish(TOPIC, {
                "@timestamp": datetime.now(timezone.utc).isoformat(),
                "source_file": filename,
                "line_number": line_no,
                "log_type": log_type,
                "message": message,
            }, f"{filename}:{line_no}")
            count += 1
            if DELAY_MS > 0:
                time.sleep(DELAY_MS / 1000.0)
    return count


access_count = publish_file("access.log", "apache_access")
app_count = publish_file("application.log", "application")
publish(LOG_TOPIC, {
    "@timestamp": datetime.now(timezone.utc).isoformat(),
    "service": "web-log-producer",
    "level": "INFO",
    "message": "Training log files published to Kafka",
    "access_records": access_count,
    "application_records": app_count,
})

pending = producer.flush(60)
if pending:
    raise RuntimeError(f"Kafka flush left {pending} pending messages")
if access_count != 600 or app_count != 220:
    raise RuntimeError(f"Unexpected training log counts: access={access_count} application={app_count}")
print(f"WEB_LOG_PRODUCER_OK access={access_count} application={app_count} total={access_count + app_count}")
