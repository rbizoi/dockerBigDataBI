"""Verify DAG parsing and the real Airflow driver -> distributed Spark data path."""
import json, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone
from airflow.models.dagbag import DagBag
result={'finished_at':None,'status':'FAIL','checks':[]}
try:
 bag=DagBag('/opt/airflow/dags',include_examples=False)
 assert not bag.import_errors,bag.import_errors
 assert {'bigdata_training_pipeline','web_logs_training_pipeline'} <= set(bag.dags)
 result['checks'].append('DAG imports OK')
 with Path('/reports/airflow-spark.log').open('w') as log:
  for job in ['00_runtime_smoke.py','09_verify_existing_data.py']:
   subprocess.run(['spark-submit','--conf','spark.driver.host=airflow-check','--conf','spark.driver.bindAddress=0.0.0.0','/opt/spark/jobs/'+job],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=900)
 result['checks'].append('Airflow image -> Spark workers -> existing Kafka/S3/Delta/Iceberg data OK')
 result['status']='PASS'
except Exception as exc:
 result['error']=str(exc)
finally:
 result['finished_at']=datetime.now(timezone.utc).isoformat()
 Path('/reports/airflow-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps(result,ensure_ascii=False))
sys.exit(0 if result['status']=='PASS' else 1)
