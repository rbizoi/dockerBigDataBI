import json
import os
from datetime import datetime, timezone

import psycopg
from confluent_kafka import Producer

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")
PG = {
    "host": os.getenv("PGHOST", "postgres-source"),
    "port": int(os.getenv("PGPORT", "5432")),
    "dbname": os.getenv("PGDATABASE", "training"),
    "user": os.getenv("PGUSER", "training"),
    "password": os.getenv("PGPASSWORD", "training"),
}
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


sql = """
SELECT
  (o.order_id * 1000 + ol.product_id)::bigint AS sale_id,
  o.customer_id, c.country, p.product_id, p.product_name, p.category,
  ol.quantity, ol.unit_price::double precision,
  0.0::double precision AS discount,
  (ol.quantity * ol.unit_price)::double precision AS amount,
  o.order_ts AS event_ts
FROM orders o
JOIN order_lines ol ON ol.order_id = o.order_id
JOIN customers c ON c.customer_id = o.customer_id
JOIN products p ON p.product_id = ol.product_id
ORDER BY o.order_id, p.product_id
"""

with psycopg.connect(**PG) as conn, conn.cursor() as cur:
    cur.execute(sql)
    columns = [desc.name for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]

for row in rows:
    row["ingested_at"] = datetime.now(timezone.utc).isoformat()
    row["source_format"] = "postgresql"
    publish("sales.raw", row, str(row["sale_id"]))

publish("application.logs", {
    "@timestamp": datetime.now(timezone.utc).isoformat(),
    "service": "postgres-producer",
    "level": "INFO",
    "message": "PostgreSQL orders published to Kafka",
    "record_count": len(rows),
})

pending = producer.flush(60)
if pending:
    raise RuntimeError(f"Kafka flush left {pending} pending messages")
print(f"POSTGRES_PRODUCER_OK records={len(rows)}")
