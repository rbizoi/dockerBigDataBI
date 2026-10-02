"""Assert actual existing training data across Spark, Kafka, S3, Delta and Iceberg."""
import csv, json, os
import psycopg2
import pandas as pd
from decimal import Decimal
from pathlib import Path
from pyspark.sql import SparkSession, functions as F
spark=SparkSession.builder.appName('verify-existing-training-data').getOrCreate()
spark.sparkContext.setLogLevel('WARN')
rows=list(csv.DictReader(Path('/opt/spark/data/input/sales.csv').open()))
expected=len(rows)
expected_amount=sum(Decimal(r['amount']) for r in rows)
bronze=spark.read.parquet('s3a://lakehouse/bronze/sales')
gold=spark.table('iceberg.gold.sales_detail')
for name,frame in [('bronze',bronze),('gold',gold)]:
 assert frame.count()==expected,(name,frame.count(),expected)
 amount=frame.agg(F.sum('amount')).first()[0]
 assert abs(Decimal(str(amount))-expected_amount)<Decimal('0.02'),(name,amount,expected_amount)
customers=json.loads(Path('/opt/spark/data/input/customers.json').read_text())
assert spark.read.parquet('s3a://lakehouse/bronze/customers').count()==len(customers)
kafka=spark.read.format('kafka').option('kafka.bootstrap.servers','kafka:19092').option('subscribe','sales.raw').option('startingOffsets','earliest').option('endingOffsets','latest').load()
ids=kafka.select(F.get_json_object(F.col('value').cast('string'),'$.sale_id').cast('long').alias('sale_id')).distinct()
assert gold.select('sale_id').join(ids,'sale_id','left_anti').count()==0
silver=spark.read.format('delta').load('s3a://lakehouse/delta/sales')
assert gold.select('sale_id').join(silver.select('sale_id'),'sale_id','left_anti').count()==0
with psycopg2.connect(host='postgres-source',dbname=os.getenv('POSTGRES_DB','formation'),user=os.getenv('POSTGRES_USER','formation'),password=os.getenv('POSTGRES_PASSWORD','formation')) as conn:
 with conn.cursor() as cursor:
  cursor.execute('SELECT (order_id * 1000 + product_id)::bigint FROM order_lines')
  pg_ids={row[0] for row in cursor.fetchall()}
kafka_ids={r[0] for r in ids.collect()}
delta_ids={r[0] for r in silver.select('sale_id').distinct().collect()}
assert pg_ids <= kafka_ids and pg_ids <= delta_ids,(pg_ids-kafka_ids,pg_ids-delta_ids)
raw_count=sum(1 for _ in Path('/opt/spark/data/logs/access.log').open())+sum(1 for _ in Path('/opt/spark/data/logs/application.log').open())
logs=spark.read.format('delta').load('s3a://lakehouse/delta/web_logs_silver')
assert logs.select('source_file','line_number','log_type').distinct().count()==raw_count
assert spark.table('iceberg.logs.events').count()==raw_count
# Verify auxiliary inputs reached the Kafka Bronze layer.
aux=spark.read.parquet('s3a://lakehouse/bronze/kafka_aux')
assert {'customers.raw','catalog.raw','opendata.raw'} <= {r[0] for r in aux.select('kafka_topic').distinct().collect()}
for topic,key,expected_ids in [
 ('customers.raw','customer_id',{int(r['customer_id']) for r in customers}),
 ('catalog.raw','product_id',{int(i) for i in pd.read_excel('/opt/spark/data/input/catalog.xlsx')['product_id']})
]:
 observed={int(r[0]) for r in aux.filter(F.col('kafka_topic')==topic).select(F.get_json_object('payload_json','$.'+key).alias('id')).filter('id IS NOT NULL').distinct().collect()}
 assert expected_ids <= observed,(topic,expected_ids-observed)
print('EXISTING_DATA_INTEGRATION_OK rows='+str(expected)+' amount='+str(expected_amount))
spark.stop()
