from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Iterable

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError

MARKER_KEY = ".bigdata-init"
MARKER_BODY = b"bigdata-training-objectstore-init\n"
LAKEHOUSE_PREFIX_MARKERS = ("spark-events/", "spark-warehouse/")


def required_buckets(value: str | None = None) -> list[str]:
    raw = value if value is not None else os.getenv("REQUIRED_BUCKETS", "warehouse,lakehouse,checkpoints")
    buckets = [item.strip() for item in raw.split(",") if item.strip()]
    if not buckets:
        raise ValueError("No required buckets configured")
    return buckets


def make_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT", "http://objectstore:9000"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY", "bigdataadmin"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY", "bigdatasecret2026"),
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def bucket_names(client) -> set[str]:
    response = client.list_buckets()
    return {item["Name"] for item in response.get("Buckets", [])}


def create_bucket_if_missing(client, bucket: str) -> None:
    if bucket in bucket_names(client):
        return
    try:
        client.create_bucket(Bucket=bucket)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
            raise


def verify_bucket(client, bucket: str) -> None:
    client.head_bucket(Bucket=bucket)
    client.put_object(Bucket=bucket, Key=MARKER_KEY, Body=MARKER_BODY, ContentType="text/plain")
    client.head_object(Bucket=bucket, Key=MARKER_KEY)


def ensure_lakehouse_prefixes(client) -> None:
    for key in LAKEHOUSE_PREFIX_MARKERS:
        client.put_object(Bucket="lakehouse", Key=key, Body=b"", ContentType="application/x-directory")
        client.head_object(Bucket="lakehouse", Key=key)


def ensure_buckets(client, buckets: Iterable[str], attempts: int = 30, delay_seconds: float = 1.0) -> None:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            for bucket in buckets:
                create_bucket_if_missing(client, bucket)
                verify_bucket(client, bucket)
            if "lakehouse" in buckets:
                ensure_lakehouse_prefixes(client)
            return
        except (ClientError, EndpointConnectionError) as exc:
            last_error = exc
            print(f"[objectstore-init] attempt={attempt}/{attempts} error={exc}", file=sys.stderr)
            if attempt < attempts:
                time.sleep(delay_seconds)
    raise RuntimeError(f"Unable to initialize object storage after {attempts} attempts: {last_error}")


def verify_only(client, buckets: Iterable[str]) -> None:
    existing = bucket_names(client)
    missing = [bucket for bucket in buckets if bucket not in existing]
    if missing:
        raise RuntimeError(f"Missing buckets: {','.join(missing)}")
    for bucket in buckets:
        client.head_bucket(Bucket=bucket)
        client.head_object(Bucket=bucket, Key=MARKER_KEY)
    if "lakehouse" in buckets:
        for key in LAKEHOUSE_PREFIX_MARKERS:
            client.head_object(Bucket="lakehouse", Key=key)


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize and verify the training S3 buckets")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    buckets = required_buckets()
    client = make_client()

    if args.verify_only:
        verify_only(client, buckets)
        print("OBJECTSTORE_VERIFY_OK " + ",".join(buckets))
    else:
        ensure_buckets(client, buckets)
        verify_only(client, buckets)
        print("OBJECTSTORE_INIT_OK " + ",".join(buckets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
