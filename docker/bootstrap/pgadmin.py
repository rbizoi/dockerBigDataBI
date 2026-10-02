import json, os
from pathlib import Path
Path('/config/servers.json').write_text(json.dumps({'Servers':{'1':{'Name':'PostgreSQL formation','Group':'Formation','Host':'postgres-source','Port':5432,'MaintenanceDB':os.environ['POSTGRES_DB'],'Username':os.environ['POSTGRES_USER'],'SSLMode':'prefer'}}}))
