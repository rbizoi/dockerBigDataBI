"""Offline contracts only. Does not claim that containers or images work."""
import ast, csv, json, re
from pathlib import Path
from decimal import Decimal
import yaml
ROOT=Path(__file__).resolve().parents[1]
compose=yaml.safe_load((ROOT/'compose.yaml').read_text())
services=compose['services']
for path in [*ROOT.glob('checks/*.py'), *ROOT.glob('dashboard/*.py'), *ROOT.glob('docker/**/*.py'), *ROOT.glob('spark/jobs/*.py'), *ROOT.glob('airflow/dags/*.py')]:
 ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
for name,service in services.items():
 for dependency in service.get('depends_on',{}):assert dependency in services,(name,dependency)
 for volume in service.get('volumes',[]):
  if isinstance(volume,str) and volume.startswith('./'):assert (ROOT/volume.split(':',1)[0]).exists(),(name,volume)
 if service.get('build'):
  build=service['build']; context=ROOT/build['context'];assert context.is_dir()
  assert (context/build.get('dockerfile','Dockerfile')).is_file()
 for port in service.get('ports',[]):assert port.startswith('127.0.0.1:'),(name,port)
# Dependencies must be acyclic; unknown volumes must not become accidental host paths.
visited=set()
def visit(name,stack):
 assert name not in stack,('dependency cycle',name,stack)
 if name in visited:return
 for dep in services[name].get('depends_on',{}):visit(dep,stack+[name])
 visited.add(name)
for name in services:visit(name,[])
assert not list(ROOT.rglob('*.ps1')) and not list(ROOT.rglob('*.cmd')) and not list(ROOT.rglob('*.sh'))
rows=list(csv.DictReader((ROOT/'data/input/sales.csv').open()))
assert len(rows)==2000 and len({r['sale_id'] for r in rows})==2000
assert all(Decimal(r['amount'])>=0 for r in rows)
assert len(json.loads((ROOT/'data/input/customers.json').read_text()))==100
access=(ROOT/'data/logs/access.log').read_text().splitlines();application=(ROOT/'data/logs/application.log').read_text().splitlines()
assert len(access)==600 and len(application)==220
assert all(re.match(r'^\S+ \S+ \S+ \[.+\] "\w+ .+ HTTP/[\d.]+" \d{3} \d+ ".*" ".*" \d+$',line) for line in access)
assert all(re.match(r'^\S+ \S+ service=\S+ trace_id=\S+ message=".*"$',line) for line in application)
assert 'druid' in services['objectstore-init']['environment']['REQUIRED_BUCKETS'].split(',')
assert all('full' in services[name]['profiles'] for name in ['druid-router','superset','airflow','kibana','api-producer'])
print('STATIC_CONTRACTS_OK services='+str(len(services))+' sales='+str(len(rows))+' logs='+str(len(access)+len(application)))
print('RUNTIME_NOT_EXECUTED: run integration-check and airflow-check on a Docker host')
