from pathlib import Path
import importlib.util

MODULE_PATH = Path(__file__).parents[1] / "docker" / "objectstore-init" / "init_s3.py"
spec = importlib.util.spec_from_file_location("init_s3", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class FakeS3:
    def __init__(self):
        self.buckets = {}

    def list_buckets(self):
        return {"Buckets": [{"Name": name} for name in sorted(self.buckets)]}

    def create_bucket(self, Bucket):
        self.buckets.setdefault(Bucket, {})
        return {}

    def head_bucket(self, Bucket):
        if Bucket not in self.buckets:
            raise AssertionError(f"bucket missing: {Bucket}")
        return {}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.buckets[Bucket][Key] = Body
        return {}

    def head_object(self, Bucket, Key):
        if Key not in self.buckets.get(Bucket, {}):
            raise AssertionError(f"object missing: {Bucket}/{Key}")
        return {"ContentLength": len(self.buckets[Bucket][Key])}


def test_required_bucket_defaults():
    assert module.required_buckets("warehouse,lakehouse,checkpoints") == [
        "warehouse", "lakehouse", "checkpoints"
    ]


def test_ensure_and_verify_buckets():
    client = FakeS3()
    buckets = ["warehouse", "lakehouse", "checkpoints"]
    module.ensure_buckets(client, buckets, attempts=1, delay_seconds=0)
    module.verify_only(client, buckets)
    assert set(client.buckets) == set(buckets)
    for bucket in buckets:
        assert module.MARKER_KEY in client.buckets[bucket]
    for key in module.LAKEHOUSE_PREFIX_MARKERS:
        assert key in client.buckets["lakehouse"]
