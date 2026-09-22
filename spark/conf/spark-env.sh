#!/usr/bin/env bash

export SPARK_MASTER_PORT=7077
export SPARK_MASTER_WEBUI_PORT=8080
export SPARK_WORKER_WEBUI_PORT=8081
export SPARK_LOG_DIR=/tmp/spark-logs
export SPARK_PID_DIR=/tmp/spark-pids
export SPARK_DAEMON_MEMORY=512m
export PYSPARK_PYTHON=python3
export PYSPARK_DRIVER_PYTHON=python3
