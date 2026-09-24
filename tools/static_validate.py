#!/usr/bin/env python3
from __future__ import annotations

import ast
import csv
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import types
import xml.etree.ElementTree as ET
from pathlib import Path

import openpyxl
import yaml

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []
WARNINGS: list[str] = []
OK: list[str] = []


def ok(msg: str) -> None:
    OK.append(msg)
    print(f"[ OK ] {msg}")


def err(msg: str) -> None:
    ERRORS.append(msg)
    print(f"[ERR ] {msg}")


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print(f"[WARN] {msg}")


def check(cond: bool, msg: str) -> None:
    ok(msg) if cond else err(msg)


def read(rel: str, encoding: str = "utf-8") -> str:
    return (ROOT / rel).read_text(encoding=encoding)


# ---------------------------------------------------------------------------
# Compose structure
# ---------------------------------------------------------------------------
try:
    compose = yaml.safe_load(read("compose.yaml"))
    check(isinstance(compose, dict) and "services" in compose, "compose.yaml parses as YAML")
except Exception as exc:
    compose = {"services": {}}
    err(f"compose.yaml parse error: {exc}")

services = compose.get("services", {})
expected_services = {
    "postgres-source", "postgres-bootstrap", "kafka", "kafka-init",
    "objectstore-permissions", "objectstore", "objectstore-init",
    "iceberg-catalog-permissions", "iceberg-rest", "spark-master",
    "spark-worker-1", "spark-worker-2", "spark-history", "spark-jupyter", "trino", "mock-opendata",
    "api-producer", "file-producer", "postgres-producer", "web-log-producer",
    "airflow-db", "airflow", "elasticsearch", "kibana", "logstash",
}
check(set(services) == expected_services, f"exact service set present ({len(expected_services)} services)")

# depends_on resolution
bad_refs: list[str] = []
for name, svc in services.items():
    deps = svc.get("depends_on", {}) or {}
    names = deps.keys() if isinstance(deps, dict) else deps
    for dep in names:
        if dep not in services:
            bad_refs.append(f"{name}->{dep}")
check(not bad_refs, "all depends_on references resolve" + ("" if not bad_refs else f": {bad_refs}"))

# bind mounts
missing_mounts: list[str] = []
for name, svc in services.items():
    for item in svc.get("volumes", []) or []:
        if isinstance(item, str):
            source = item.split(":", 1)[0]
            if source.startswith("./"):
                p = ROOT / source[2:]
                if not p.exists():
                    missing_mounts.append(f"{name}:{source}")
check(not missing_mounts, "all local bind-mount sources exist" + ("" if not missing_mounts else f": {missing_mounts}"))

# Ports restricted to localhost
bad_ports: list[str] = []
for name, svc in services.items():
    for port in svc.get("ports", []) or []:
        value = str(port)
        if not value.startswith("127.0.0.1:"):
            bad_ports.append(f"{name}:{value}")
check(not bad_ports, "all published ports bind to 127.0.0.1" + ("" if not bad_ports else f": {bad_ports}"))

# Profiles
profile_map = {k: tuple(v.get("profiles", []) or []) for k, v in services.items()}
check(profile_map["airflow"] == ("orchestration",), "Airflow isolated in orchestration profile")
check(profile_map["elasticsearch"] == ("elastic",) and profile_map["logstash"] == ("elastic",), "Elastic Stack isolated in elastic profile")
check(profile_map["file-producer"] == ("seed",) and profile_map["web-log-producer"] == ("logs",), "training producers use seed/logs profiles")

# Images pinned
bad_images: list[str] = []
for name, svc in services.items():
    image = svc.get("image")
    if image and (image.endswith(":latest") or (":" not in image and "@sha256:" not in image)):
        bad_images.append(f"{name}:{image}")
check(not bad_images, "all Compose images are pinned")

# Kibana needs enough V8 heap for its first-start saved-object migrations.
kibana = services.get("kibana", {})
kibana_env = kibana.get("environment", {}) or {}
check(str(kibana.get("mem_limit")) == "1536m", "Kibana container memory limit is 1536 MiB")
check(str(kibana_env.get("NODE_OPTIONS")) == "--max-old-space-size=1024", "Kibana Node.js heap is 1024 MiB")

# Key healthchecks
for svc_name in ["postgres-source", "kafka", "objectstore", "iceberg-rest", "spark-master", "spark-worker-1", "spark-worker-2", "spark-history", "spark-jupyter", "trino", "airflow-db", "airflow", "elasticsearch"]:
    check("healthcheck" in services.get(svc_name, {}), f"{svc_name} has explicit healthcheck")

# No host RAM gate
ps_text = "\n".join(p.read_text(encoding="utf-8-sig", errors="ignore") for p in ROOT.rglob("*.ps1"))
check("MemTotal" not in ps_text and "dockerGiB" not in ps_text and "Minimum pour l'ensemble complet" not in ps_text, "no blocking host RAM preflight check")

# ---------------------------------------------------------------------------
# Dockerfiles / dependencies
# ---------------------------------------------------------------------------
bad_from: list[str] = []
for df in ROOT.rglob("Dockerfile"):
    for line in df.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.upper().startswith("FROM "):
            image = line.split()[1]
            if image.endswith(":latest") or (":" not in image and "@sha256:" not in image):
                bad_from.append(f"{df.relative_to(ROOT)}:{image}")
check(not bad_from, "all Dockerfile FROM images are pinned")

spark_defaults = read("spark/conf/spark-defaults.conf")
check("spark.jars.packages" not in spark_defaults, "Spark performs no Maven resolution at spark-submit runtime")
check("spark.sql.extensions" in spark_defaults and "DeltaSparkSessionExtension" in spark_defaults and "IcebergSparkSessionExtensions" in spark_defaults, "Delta + Iceberg Spark SQL extensions configured")
check("spark.hadoop.fs.s3a.path.style.access    true" in spark_defaults, "Spark S3A path-style access enabled")
check("spark.sql.catalog.iceberg.s3.path-style-access true" in spark_defaults, "Iceberg S3FileIO path-style access enabled")
for token in [
    "spark.serializer                         org.apache.spark.serializer.KryoSerializer",
    "spark.io.compression.lz4.blockSize       128k",
    "spark.driver.memory                      1g",
    "spark.executor.memory                    1g",
    "spark.deploy.defaultCores                4",
    "spark.sql.session.timeZone               UTC",
    "spark.sql.ansi.enabled                    false",
    "spark.sql.warehouse.dir                  s3a://lakehouse/spark-warehouse",
    "spark.eventLog.dir                        s3a://lakehouse/spark-events",
    "spark.history.fs.logDirectory             s3a://lakehouse/spark-events",
    "spark.history.fs.cleaner.interval         7d",
    "spark.history.fs.cleaner.maxAge           90d",
]:
    check(token in spark_defaults, f"adapted dockerBigData Spark setting present: {token.split()[0]}")
check("\npark.sql.ansi.enabled" not in spark_defaults, "legacy spark.sql.ansi.enabled typo is corrected")

log4j2 = read("spark/conf/log4j2.properties")
check("rootLogger.level = warn" in log4j2 and "org.apache.parquet" in log4j2 and "RetryingHMSHandler" in log4j2, "legacy Log4j configuration is translated to Spark 4 Log4j2")
spark_env = read("spark/conf/spark-env.sh")
check("SPARK_MASTER_PORT=7077" in spark_env and "SPARK_MASTER_WEBUI_PORT=8080" in spark_env and "SPARK_WORKER_WEBUI_PORT=8081" in spark_env, "Spark environment ports match Compose")

history = services["spark-history"]
check("org.apache.spark.deploy.history.HistoryServer" in history.get("command", []), "Spark History Server uses the Spark 4 runtime image")
check(any("18083" in str(p) and "18080" in str(p) for p in history.get("ports", [])), "Spark History Server UI is published on localhost port 18083")
for worker_name in ["spark-worker-1", "spark-worker-2"]:
    worker_command = services[worker_name].get("command", [])
    check("--cores" in worker_command and worker_command[worker_command.index("--cores") + 1] == "2", f"{worker_name} exposes two cores")

jupyter = services["spark-jupyter"]
jupyter_env = jupyter.get("environment", {}) or {}
master_ports = services["spark-master"].get("ports", []) or []
check(not jupyter.get("profiles"), "JupyterLab is included in the standard installation")
check(str(jupyter.get("user")) == "spark", "Compose explicitly runs JupyterLab as the non-root spark user")
check(any("JUPYTER_PORT" in str(p) and "8888" in str(p) for p in jupyter.get("ports", [])), "JupyterLab UI is published on configurable localhost port 8888")
check(any("SPARK_JOBS_UI_PORT" in str(p) and "4040" in str(p) for p in jupyter.get("ports", [])), "Spark Jobs UI is published by spark-jupyter on configurable localhost port 4040")
check(not any("SPARK_JOBS_UI_PORT" in str(p) or str(p).endswith(":4040") or str(p).endswith(":14040") for p in master_ports), "Spark master does not own the Jupyter driver's live UI port")
check(jupyter_env.get("SPARK_MASTER_URL") == "spark://spark-master:7077", "JupyterLab targets the Spark Standalone master")
check("spark.driver.host=spark-jupyter" in str(jupyter_env.get("PYSPARK_SUBMIT_ARGS", "")), "Jupyter PySpark driver advertises its Compose hostname")
check("spark.ui.enabled=true" in str(jupyter_env.get("PYSPARK_SUBMIT_ARGS", "")) and "spark.ui.port=4040" in str(jupyter_env.get("PYSPARK_SUBMIT_ARGS", "")), "Jupyter driver explicitly enables its live UI on internal port 4040")
check(jupyter_env.get("PYSPARK_PYTHON") == "python3" and jupyter_env.get("PYSPARK_DRIVER_PYTHON") == "python3", "Jupyter driver and Spark workers use Python 3")
check(any("./spark/notebooks:/opt/spark/notebooks" in str(v) for v in jupyter.get("volumes", [])), "Jupyter notebooks are persisted with a host bind mount")
check("CHANGE_ME" in read(".env.example") and "JUPYTER_TOKEN" in read(".env.example"), "Jupyter token placeholder is declared for first-run generation")
check("SPARK_JOBS_UI_PORT=4040" in read(".env.example"), "Spark Jobs UI host port is declared in .env.example")
check(jupyter_env.get("HOME") == "/home/spark" and jupyter_env.get("JUPYTER_RUNTIME_DIR") == "/home/spark/.local/share/jupyter/runtime", "Jupyter uses an explicit writable Spark home and runtime directory")
check(jupyter_env.get("JUPYTER_DATA_DIR") == "/home/spark/.local/share/jupyter", "Jupyter data directory is explicit and inside the Spark home")
check(jupyter_env.get("PYTHONPATH") == "/opt/spark/python:/opt/spark/python/lib/py4j-src.zip", "Jupyter receives Spark's bundled PySpark and stable Py4J paths")

spark_tree_text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "spark").rglob("*") if p.is_file())
for forbidden in ["ROOT_PASSWORD", "SPARK_PASSWORD", "coursBigData", "jupiter.olimp.fr", "minerve.olimp.fr"]:
    check(forbidden not in spark_tree_text, f"legacy Spark secret/hostname excluded: {forbidden}")

pom = read("spark/runtime/pom.xml")
try:
    ET.fromstring(pom)
    ok("Spark runtime pom.xml is well-formed XML")
except Exception as exc:
    err(f"Spark runtime pom.xml XML error: {exc}")
for token in [
    "delta-spark_${scala.binary.version}", "4.0.0", "iceberg-spark-runtime-4.0_${scala.binary.version}", "1.11.0",
    "hadoop-aws", "3.4.1", "spark-sql-kafka-0-10_${scala.binary.version}", "4.0.4",
    "software.amazon.awssdk", "bundle", "2.44.4",
]:
    check(token in pom, f"Spark runtime POM contains {token}")
check("iceberg-aws-bundle" not in pom, "no second Iceberg AWS SDK bundle is introduced")
check("<artifactId>url-connection-client</artifactId>" not in pom, "url-connection-client is not resolved transitively by Maven POM")
check("<artifactId>bundle</artifactId>" in pom and "<aws.sdk.version>2.44.4</aws.sdk.version>" in pom, "single AWS SDK bundle is pinned to 2.44.4")
check("<exclusions>" in pom and "<artifactId>bundle</artifactId>" in pom, "hadoop-aws transitive AWS bundle is explicitly excluded")

spark_df = read("spark/runtime/Dockerfile")
check("dependency:copy-dependencies" in spark_df and "COPY --from=dependency-resolver /deps/ /opt/spark/jars/" in spark_df, "Spark JARs are baked into custom image")
check("maven-dependency-plugin:3.8.1:copy" in spark_df and "url-connection-client:2.44.4" in spark_df, "URL connection client is copied directly without Maven transitive resolution")
check("modular AWS SDK core jar detected" in spark_df, "Spark image build rejects modular AWS SDK core duplicates")
check("IoUtils.class" in spark_df and "test \"$(printf '%s\\n' \"$sources\" | sed '/^$/d' | wc -l)\" -eq 1" in spark_df, "Spark image build requires exactly one AWS IoUtils provider")
check("thirdparty.org.slf4j.Logger" in spark_df, "Spark image build verifies shaded AWS bundle IoUtils signature")
check("spark.sql.catalog.iceberg.http-client.type urlconnection" in spark_defaults, "Iceberg S3FileIO explicitly uses URLConnection HTTP client")

ml_req = read("spark/runtime/requirements-ml.txt")
check(any(line.strip() == "numpy" for line in ml_req.splitlines()), "Spark ML Python requirements include NumPy without an exact version gate")
check("python3 -m pip install --no-cache-dir -r /tmp/requirements-ml.txt" in spark_df, "Spark image installs ML Python requirements")
check("python3 -m pip install --no-cache-dir -r /tmp/requirements-jupyter.txt" in spark_df, "Spark image installs JupyterLab requirements")
jupyter_req = read("spark/runtime/requirements-jupyter.txt")
check(any(line.strip() == "jupyterlab==4.4.10" for line in jupyter_req.splitlines()), "JupyterLab dependency is exactly pinned")
check("python3 -m jupyter lab --version" in spark_df, "Spark image validates the JupyterLab executable at build time")
check("python3-cairo" in spark_df and '"cairo"' in read("spark/runtime/validate_python_dependencies.py"), "Spark image satisfies and imports PyGObject's pycairo dependency")
check("validate_python_dependencies.py" in spark_df and "python3 -m pip check" in spark_df, "Spark image validates requested Python imports and dependency consistency")
check("install -d -m 0755 -o spark -g spark /home/spark" in spark_df and "chown -R spark:spark /home/spark" in spark_df, "Spark image recursively assigns the complete Jupyter home to spark")
check("find /home/spark \\( ! -user spark -o ! -group spark \\) -print -quit" in spark_df and "chmod 0700" in spark_df, "Spark image verifies ownership and private permissions for all Jupyter home paths")
check("ENV HOME=/home/spark" in spark_df and "JUPYTER_RUNTIME_DIR=/home/spark/.local/share/jupyter/runtime" in spark_df, "Spark image exports writable Jupyter/XDG paths")
check("find /opt/spark/python/lib" in spark_df and "py4j-*-src.zip" in spark_df and "py4j-src.zip" in spark_df, "Spark image creates a version-independent Py4J archive alias")
check("JUPYTER_PYSPARK_IMPORT_OK" in spark_df and "import py4j, pyspark" in spark_df, "Spark image validates plain Python PySpark/Py4J imports at build time")
check("from pyspark.ml.clustering import KMeans" in spark_df, "Spark image build imports KMeans")
check("StandardScaler, VectorAssembler" in spark_df, "Spark image build imports ML feature classes")
check(spark_df.count("SPARK_ML_PYTHON_OK") >= 1 and "FINAL_SPARK_ML_PYTHON_OK" in spark_df, "Spark image performs ML Python import checks before and after finalization")
check("bigdata-training/spark-runtime:local" in read("compose.yaml"), "Compose uses local Spark runtime image tag")


# S3 initializer
s3_init = read("docker/objectstore-init/init_s3.py")
for token in ["addressing_style\": \"path", "create_bucket", "head_bucket", "put_object", "head_object", "warehouse,lakehouse,checkpoints", "spark-events/", "spark-warehouse/"]:
    check(token in s3_init, f"S3 initializer contract contains {token}")
check("rustfs/rc" not in read("compose.yaml"), "RustFS CLI rc is not used for bucket initialization")

iceberg_env = services["iceberg-rest"].get("environment", {})
check(iceberg_env.get("CATALOG_URI") == "jdbc:sqlite:/var/lib/iceberg/catalog.db", "Iceberg REST uses persistent SQLite catalog")
check(str(iceberg_env.get("CATALOG_CLIENTS")) == "1", "Iceberg REST JDBC pool is limited to one client")
check(str(iceberg_env.get("CATALOG_S3_PATH__STYLE__ACCESS")).lower() == "true", "Iceberg REST path-style S3 enabled")

# Trino
trino_ice = read("trino/catalog/iceberg.properties")
for token in ["iceberg.catalog.type=rest", "iceberg.rest-catalog.uri=http://iceberg-rest:8181", "fs.s3.enabled=true", "s3.endpoint=http://objectstore:9000", "s3.path-style-access=true"]:
    check(token in trino_ice, f"Trino Iceberg catalog contains {token}")
check("-Xmx1400M" in read("trino/etc/jvm.config"), "Trino JVM heap is bounded for Docker Desktop")

# Airflow consistency
airflow_df = read("docker/airflow/Dockerfile")
check("constraints-${AIRFLOW_VERSION}" in airflow_df and "apache-airflow-providers-apache-spark" in airflow_df and '"pyspark==${SPARK_VERSION}"' in airflow_df, "Airflow uses release constraints and derives PySpark from the Spark runtime")
check("pyspark-client must not coexist" in airflow_df, "Airflow build rejects pyspark-client/full-pyspark namespace collision")
check("python3 -m pip check" in airflow_df, "Airflow build validates Python dependency consistency")
check("help:evaluate -Dexpression=aws.sdk.version" in airflow_df and 'url-connection-client:${AWS_SDK_VERSION}' in airflow_df, "Airflow resolves the AWS URLConnection client from the POM SDK version")
check("UrlConnectionHttpClient$Builder.class" in airflow_df, "Airflow build verifies the AWS URLConnection HTTP client class")
for dag in (ROOT / "airflow/dags").glob("*.py"):
    text = dag.read_text(encoding="utf-8")
    check("/opt/spark/jobs/" in text, f"{dag.name} uses canonical Spark job path")

# ---------------------------------------------------------------------------
# Code syntax
# ---------------------------------------------------------------------------
py_files = [p for p in ROOT.rglob("*.py") if "__pycache__" not in p.parts]
py_errors: list[str] = []
for p in py_files:
    try:
        source = p.read_text(encoding="utf-8")
        compile(source, str(p), "exec")
    except Exception as exc:
        py_errors.append(f"{p.relative_to(ROOT)}: {exc}")
check(not py_errors, f"Python syntax validated ({len(py_files)} files)")
if py_errors:
    for x in py_errors: err(x)

sh_files = list(ROOT.rglob("*.sh"))
sh_errors: list[str] = []
for p in sh_files:
    r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
    if r.returncode:
        sh_errors.append(f"{p.relative_to(ROOT)}: {r.stderr.strip()}")
check(not sh_errors, f"Bash syntax validated ({len(sh_files)} files)")
if sh_errors:
    for x in sh_errors: err(x)

# PowerShell static checks (native Parser runs on target Windows during preflight)
smart = set("‘’“”")
ambiguous = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*):")
allowed_scopes = {"env", "script", "global", "local", "private", "using"}
ps_errors: list[str] = []
ps_files = list(ROOT.rglob("*.ps1"))
for p in ps_files:
    raw = p.read_bytes()
    text = p.read_text(encoding="utf-8-sig", errors="strict")
    rel = p.relative_to(ROOT)
    if not raw.startswith(b"\xef\xbb\xbf"):
        ps_errors.append(f"{rel}: missing UTF-8 BOM")
    if any(c in text for c in smart):
        ps_errors.append(f"{rel}: smart quote")
    if "\\nparam" in text[:400] or "\\r\\nparam" in text[:400]:
        ps_errors.append(f"{rel}: literal newline escape in header")
    for lineno, line in enumerate(text.splitlines(), 1):
        for m in ambiguous.finditer(line):
            if m.group(1).lower() not in allowed_scopes:
                ps_errors.append(f"{rel}:{lineno}: ambiguous interpolation {m.group(0)}")
check(not ps_errors, f"PowerShell 5.1 structural checks passed ({len(ps_files)} scripts)")

common_ps = (ROOT / "scripts/windows/Common.ps1").read_text(encoding="utf-8-sig")
check("$state.Health" not in common_ps, "Common.ps1 does not access optional Docker State.Health directly")
check("PSObject.Properties[$Name]" in common_ps, "Common.ps1 uses StrictMode-safe optional property lookup")
check("HasHealthcheck" in common_ps, "service state exposes HasHealthcheck")
check("Wait-ServiceHealthy requires an explicit healthcheck" in common_ps, "healthy wait rejects missing healthchecks")

check("Assert-OneShotSucceeded" in common_ps, "functional validator uses one-shot service contracts")
check("PostgreSQL unexpected customer count" not in common_ps, "host-side PostgreSQL numeric stdout parsing removed")
check("kafka-topics.sh --bootstrap-server kafka:19092 --list" not in common_ps, "host-side Kafka topic-list parsing removed from functional validation")
check("$s3.Code -ne 0 -or $s3.Text -notmatch" not in common_ps, "S3 verification trusts exit code instead of stdout marker parsing")
check("POSTGRES_FEDERATION_OK" in common_ps and "count(*) >= 5" in common_ps, "Trino PostgreSQL validation uses stable marker and >=5 contract")
check("ICEBERG_QUERY_OK" in common_ps and "count(*) = 3" in common_ps, "Trino Iceberg validation uses stable marker")


if ps_errors:
    for x in ps_errors: err(x)

# ---------------------------------------------------------------------------
# Airflow / Spark Python runtime parity contract
# ---------------------------------------------------------------------------
compose_text = read("compose.yaml")
airflow_dockerfile = read("docker/airflow/Dockerfile")
spark_dockerfile = read("spark/runtime/Dockerfile")
spark_defaults = read("spark/conf/spark-defaults.conf")
smoke = read("spark/jobs/00_runtime_smoke.py")
installer = read("Install-BigDataLab.ps1", encoding="utf-8-sig")
check("FROM apache/airflow:" in airflow_dockerfile, "Airflow image base is explicit")
check("SPARK_VERSION=" in airflow_dockerfile and "/tmp/spark-version.txt" in airflow_dockerfile, "Airflow derives PySpark version from Spark runtime metadata")
check("COPY --chown=airflow:root --from=dependency-resolver /spark-version.txt /tmp/spark-version.txt" in airflow_dockerfile, "Airflow Spark version metadata is owned by airflow")
check("requirements-ml.txt" in airflow_dockerfile, "Airflow installs Spark ML Python requirements")
check("AIRFLOW_PYSPARK_OK=" in airflow_dockerfile, "Airflow image build validates PySpark against Spark runtime")
check("AIRFLOW_PYSPARK_CLIENT_ABSENT=OK" in airflow_dockerfile, "Airflow image build excludes pyspark-client collision")
check('url-connection-client:${AWS_SDK_VERSION}' in airflow_dockerfile, "Airflow driver receives the Iceberg S3 URLConnection HTTP client")
check("SPARK_PYTHON_OK=" in spark_dockerfile, "Spark image build reports its Python runtime")
check("spark.pyspark.python" in spark_defaults and "python3" in spark_defaults, "Spark explicitly configures PySpark Python")
check("spark.pyspark.driver.python" in spark_defaults, "Spark explicitly configures driver Python")
check("PYSPARK_PYTHON: python3" in compose_text, "Compose fixes Spark worker Python command")
check("PYSPARK_DRIVER_PYTHON: python3" in compose_text, "Compose fixes Airflow driver Python command")
check("bigdata-training/airflow:local" in compose_text, "Compose uses local Airflow image tag")
check("PYTHON_RUNTIME_PARITY_OK" in smoke, "Spark smoke validates distributed Python parity")
check("_python_runtime_probe" in smoke and "mapPartitions" in smoke, "Python parity probe executes inside workers")
check("SPARK_IMPORTED_CONFIG_OK" in smoke and "spark.eventLog.dir" in smoke and "spark.io.compression.lz4.blockSize" in smoke, "Spark smoke validates imported configuration at runtime")
check("Test-AirflowSparkPythonParity" in common_ps, "PowerShell checks Airflow/Spark Python parity")
check("AIRFLOW_ML_RUNTIME_OK" in installer, "Installer validates Airflow ML runtime")
check("assert sys.version_info[:2]" not in installer and "assert pyspark.__version__" not in installer, "Installer has no fixed Python/PySpark version gate")
check("PYTHON_RUNTIME_PARITY_OK" in installer, "Installer requires distributed Python parity")
check("JupyterLab access token generated in .env" in installer, "Installer generates a Jupyter access token on first run")
check("JUPYTER_SPARK_RUNTIME_OK" in installer, "Installer validates JupyterLab and PySpark imports")
check("pwd.getpwuid(os.geteuid()).pw_name" in installer and "assert user == 'spark'" in installer and "/opt/spark/notebooks/.write-test" in installer and "/home/spark/.local/share/jupyter/.write-test" in installer, "Installer validates non-root identity and real Jupyter/notebook writes")
intermediate_artifacts=[p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and (p.name.startswith("MANIFEST_V6_") or (p.parent.name=="docs" and re.match(r"V6_\d+_",p.name)) or "HOTFIX" in p.name.upper())]
check(not intermediate_artifacts, "no intermediate V6 repair/hotfix artifacts remain")

# ---------------------------------------------------------------------------
# Requirements and producer APIs
# ---------------------------------------------------------------------------
req_files = list((ROOT / "docker").glob("*/requirements.txt"))
req_errors: list[str] = []
for p in req_files:
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            req_errors.append(f"{p.relative_to(ROOT)}:{line}")
check(not req_errors, "all Python requirements files are exactly pinned")

producer_files = [ROOT / "docker/file-producer/producer.py", ROOT / "docker/postgres-producer/producer.py", ROOT / "docker/web-log-producer/producer.py", ROOT / "docker/api-producer/producer.py"]
check(all("confluent_kafka" in p.read_text(encoding="utf-8") for p in producer_files), "all Kafka producers use confluent-kafka")
check(all("kafka-python" not in p.read_text(encoding="utf-8") for p in producer_files), "kafka-python removed from producers")

# ---------------------------------------------------------------------------
# Training datasets
# ---------------------------------------------------------------------------
sales_path = ROOT / "data/input/sales.csv"
with sales_path.open(newline="", encoding="utf-8") as f:
    sales_count = sum(1 for _ in csv.DictReader(f))
check(sales_count == 2000, "sales.csv contains 2000 records")

customers = json.loads((ROOT / "data/input/customers.json").read_text(encoding="utf-8"))
check(isinstance(customers, list) and len(customers) == 100, "customers.json contains 100 records")

wb = openpyxl.load_workbook(ROOT / "data/input/catalog.xlsx", read_only=True, data_only=True)
ws = wb.active
catalog_count = max(ws.max_row - 1, 0)
wb.close()
check(catalog_count == 7, "catalog.xlsx contains 7 product rows")

access_lines = (ROOT / "data/logs/access.log").read_text(encoding="utf-8").splitlines()
app_lines = (ROOT / "data/logs/application.log").read_text(encoding="utf-8").splitlines()
check(len(access_lines) == 600, "access.log contains 600 lines")
check(len(app_lines) == 220, "application.log contains 220 lines")

access_re = re.compile(r'^(\S+) \S+ (\S+) \[([^]]+)\] "(\S+) ([^ ]+) HTTP/([^"]+)" (\d{3}) (\d+) "([^"]*)" "([^"]*)" (\d+)$')
app_re = re.compile(r'^(\S+) (INFO|WARN|ERROR) service=([^ ]+) trace_id=([^ ]+) message="(.*)"$')
check(sum(bool(access_re.match(x)) for x in access_lines) == 600, "all 600 access logs match Spark parser regex")
check(sum(bool(app_re.match(x)) for x in app_lines) == 220, "all 220 application logs match Spark parser regex")

# ---------------------------------------------------------------------------
# Job and installer contracts
# ---------------------------------------------------------------------------
job_names = {p.name for p in (ROOT / "spark/jobs").glob("*.py")}
expected_jobs = {f"0{i}_" for i in range(9)}
check(len(job_names) == 9 and all(any(name.startswith(prefix) for name in job_names) for prefix in expected_jobs), "all nine Spark training jobs 00..08 are present")
installer = read("Install-BigDataLab.ps1", encoding="utf-8-sig")
for name in sorted(job_names):
    check(name in installer or name == "00_runtime_smoke.py", f"installer references Spark job {name}")
check("INSTALLATION VALIDATED SUCCESSFULLY" in installer, "installer has explicit final success gate")
check("Test-CoreFunctional" in installer and "SMOKE_RUNTIME_OK" in installer, "installer gates success on functional core and Spark smoke")
check("spark-history" in installer and "api/v1/applications?limit=1" in installer and "Spark S3 event log visible in History Server" in installer, "installer validates Spark History Server and S3 event logs")
check("spark-jupyter" in installer and "Wait-ServiceHealthy 'spark-jupyter'" in installer and "JupyterLab user, write permissions and PySpark runtime validated" in installer, "installer starts and validates JupyterLab")
check("docker compose port spark-jupyter 4040" in installer and "Spark Jobs UI mapping validated" in installer, "installer validates the Spark Jobs UI mapping on the driver service")
check("-Service 'kibana'" in installer and "JavaScript heap out of memory" in ps_text, "installer detects Kibana heap exhaustion during HTTP readiness")
check("$json | docker compose exec -T kafka /opt/kafka/bin/kafka-console-producer.sh" in installer, "Elastic validation JSON is piped directly to the Kafka producer")
check("$producerCommand" not in installer and "/bin/bash -lc $producerCommand" not in installer, "Elastic validation avoids nested PowerShell/Bash JSON quoting")
check("training-logs-*/_search" in installer and "'validation_id.keyword' = $validationId" in installer and "-Method Post" in installer, "Elastic validation uses an exact JSON term query")

# no patch-history artifacts in filenames
forbidden_names = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and ("V5" in p.name or p.name.startswith("Repair-") or p.name.startswith("Diagnose-"))]
check(not forbidden_names, "no V5/Repair/Diagnose patch artifacts remain")

cache_artifacts = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.name == "__pycache__" or p.suffix == ".pyc"]
check(not cache_artifacts, "no __pycache__ or .pyc artifacts in distribution")

checksum_entries: dict[str, str] = {}
for line in read("CHECKSUMS_SHA256.txt").splitlines():
    if not line.strip():
        continue
    digest, rel = line.split(None, 1)
    checksum_entries[rel.strip()] = digest
checksum_files = {
    p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in ROOT.rglob("*")
    if p.is_file() and p.name != "CHECKSUMS_SHA256.txt" and ".git" not in p.relative_to(ROOT).parts
}
check(checksum_entries == checksum_files, "SHA-256 manifest covers every distribution file exactly")

notebook = json.loads(read("spark/notebooks/01_demarrage_spark.ipynb"))
notebook_source = "\n".join("".join(cell.get("source", [])) for cell in notebook.get("cells", []))
check(notebook.get("nbformat") == 4 and len(notebook.get("cells", [])) >= 3, "starter Jupyter notebook is valid nbformat 4")
check("SparkSession.builder" in notebook_source and "spark.range" in notebook_source, "starter notebook creates and exercises a distributed Spark session")
check("OPEN_JUPYTER.cmd" in {p.name for p in ROOT.glob("*.cmd")}, "Windows Jupyter launcher is included")
check("spark.sparkContext.uiWebUrl" in notebook_source and "http://127.0.0.1:4040" in notebook_source, "starter notebook reports both internal and Windows Spark UI addresses")
spark_jobs_launcher = read("OPEN_SPARK_JOBS.cmd")
check("spark-jupyter" in spark_jobs_launcher and "127.0.0.1:%SPARK_JOBS_UI_PORT_VALUE%" in spark_jobs_launcher and "connect_ex(('127.0.0.1',4040))" in spark_jobs_launcher, "Windows Spark Jobs launcher validates an active driver UI before opening it")
check("jupiter.olimp.fr" not in spark_tree_text and "spark-jupyter:14040" not in spark_tree_text, "notebooks contain no obsolete or Docker-internal Spark UI browser links")

# ---------------------------------------------------------------------------
# Unit test of objectstore bootstrap without network
# ---------------------------------------------------------------------------
try:
    class StubClientError(Exception):
        response: dict = {}

    class StubEndpointConnectionError(Exception):
        pass

    boto3_stub = types.ModuleType("boto3")
    boto3_stub.client = lambda *args, **kwargs: None
    botocore_stub = types.ModuleType("botocore")
    botocore_client_stub = types.ModuleType("botocore.client")
    botocore_client_stub.Config = lambda *args, **kwargs: object()
    botocore_exceptions_stub = types.ModuleType("botocore.exceptions")
    botocore_exceptions_stub.ClientError = StubClientError
    botocore_exceptions_stub.EndpointConnectionError = StubEndpointConnectionError
    stub_modules = {
        "boto3": boto3_stub,
        "botocore": botocore_stub,
        "botocore.client": botocore_client_stub,
        "botocore.exceptions": botocore_exceptions_stub,
    }
    previous_modules = {name: sys.modules.get(name) for name in stub_modules}
    sys.modules.update(stub_modules)

    namespace = {"__name__": "init_s3_under_test"}
    init_path = ROOT / "docker/objectstore-init/init_s3.py"
    exec(compile(init_path.read_text(encoding="utf-8"), str(init_path), "exec"), namespace)

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

    buckets = ["warehouse", "lakehouse", "checkpoints"]
    client = FakeS3()
    namespace["ensure_buckets"](client, buckets, attempts=1, delay_seconds=0)
    namespace["verify_only"](client, buckets)
    assert set(client.buckets) == set(buckets)
    assert all(namespace["MARKER_KEY"] in client.buckets[b] for b in buckets)
    ok("objectstore bootstrap unit tests passed")
except Exception as exc:
    err(f"objectstore bootstrap unit tests failed: {exc}")
finally:
    for name, previous in previous_modules.items():
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous

# Docker availability disclosure
if subprocess.run(["bash", "-lc", "command -v docker >/dev/null 2>&1"], capture_output=True).returncode != 0:
    warn("Docker CLI/daemon unavailable in authoring environment; container runtime validation must run on target Docker Desktop")
else:
    ok("Docker CLI available in authoring environment")

print()
print(f"Result: {len(ERRORS)} error(s), {len(WARNINGS)} warning(s), {len(OK)} passed checks")
if ERRORS:
    sys.exit(1)
