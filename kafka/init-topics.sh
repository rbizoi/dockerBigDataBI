#!/usr/bin/env bash
set -Eeuo pipefail

BOOTSTRAP_SERVER="${KAFKA_BOOTSTRAP_SERVER:-kafka:19092}"
PARTITIONS="${KAFKA_TOPIC_PARTITIONS:-3}"
REPLICATION_FACTOR="${KAFKA_REPLICATION_FACTOR:-1}"
MAX_ATTEMPTS="${KAFKA_INIT_MAX_ATTEMPTS:-30}"
SLEEP_SECONDS="${KAFKA_INIT_RETRY_SECONDS:-2}"

TOPICS=(
  sales.raw
  customers.raw
  catalog.raw
  opendata.raw
  application.logs
  web.logs.raw
  web.logs.dlq
)

KAFKA_TOPICS=/opt/kafka/bin/kafka-topics.sh

log() { printf '[kafka-init] %s\n' "$*"; }

log "Waiting for Kafka Admin API on ${BOOTSTRAP_SERVER}..."
ready=0
for ((attempt=1; attempt<=MAX_ATTEMPTS; attempt++)); do
  if "${KAFKA_TOPICS}" --bootstrap-server "${BOOTSTRAP_SERVER}" --list >/tmp/topics.txt 2>/tmp/kafka-init.err; then
    ready=1
    break
  fi
  log "Kafka not ready (attempt ${attempt}/${MAX_ATTEMPTS}); retrying in ${SLEEP_SECONDS}s"
  sleep "${SLEEP_SECONDS}"
done

if [[ "${ready}" -ne 1 ]]; then
  log "ERROR: Kafka did not become ready. Last CLI error:"
  cat /tmp/kafka-init.err >&2 || true
  exit 10
fi

for topic in "${TOPICS[@]}"; do
  # Avoid relying on --if-not-exists. Listing first makes the init idempotent
  # and gives deterministic behavior across Kafka CLI releases.
  if "${KAFKA_TOPICS}" --bootstrap-server "${BOOTSTRAP_SERVER}" --list | grep -Fxq "${topic}"; then
    log "Topic already exists: ${topic}"
    continue
  fi

  created=0
  for ((attempt=1; attempt<=10; attempt++)); do
    log "Creating topic ${topic} (attempt ${attempt}/10)..."
    if "${KAFKA_TOPICS}" \
      --bootstrap-server "${BOOTSTRAP_SERVER}" \
      --create \
      --topic "${topic}" \
      --partitions "${PARTITIONS}" \
      --replication-factor "${REPLICATION_FACTOR}"; then
      created=1
      break
    fi

    # A concurrent creation may have succeeded even if the command returned non-zero.
    if "${KAFKA_TOPICS}" --bootstrap-server "${BOOTSTRAP_SERVER}" --list | grep -Fxq "${topic}"; then
      created=1
      break
    fi
    sleep 2
  done

  if [[ "${created}" -ne 1 ]]; then
    log "ERROR: failed to create topic ${topic}"
    exit 20
  fi
done

log "Kafka topics ready:"
"${KAFKA_TOPICS}" --bootstrap-server "${BOOTSTRAP_SERVER}" --list | sort

# Final verification: the init container succeeds only if every required topic exists.
missing=0
for topic in "${TOPICS[@]}"; do
  if ! "${KAFKA_TOPICS}" --bootstrap-server "${BOOTSTRAP_SERVER}" --list | grep -Fxq "${topic}"; then
    log "ERROR: topic missing after initialization: ${topic}"
    missing=1
  fi
done
if [[ "${missing}" -ne 0 ]]; then
  exit 21
fi
log "Validation OK: all ${#TOPICS[@]} required topics exist."
