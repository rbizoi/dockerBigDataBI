"""Create required topics idempotently using Kafka Admin API."""
import os
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka import KafkaException, KafkaError
admin = AdminClient({'bootstrap.servers': os.getenv('KAFKA_BOOTSTRAP_SERVER', 'kafka:19092')})
topics = ['sales.raw', 'customers.raw', 'catalog.raw', 'opendata.raw', 'application.logs', 'web.logs.raw', 'web.logs.dlq']
for name, future in admin.create_topics([NewTopic(t, 3, 1) for t in topics], request_timeout=60).items():
    try:
        future.result()
    except KafkaException as exc:
        if exc.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
            raise
actual = admin.list_topics(timeout=30).topics
assert all(t in actual and not actual[t].error for t in topics)
print('KAFKA_INIT_OK', ','.join(topics))
