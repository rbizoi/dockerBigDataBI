"""Migrate metadata, create admin once, register analytical connections."""
import os
import subprocess
from urllib.parse import quote_plus
subprocess.run(['superset', 'db', 'upgrade'], check=True)
from superset.app import create_app
from superset import db, security_manager
app = create_app()
with app.app_context():
    # Superset model imports access current_app.config at import time.
    from superset.models.core import Database

    user = os.environ['SUPERSET_ADMIN_USER']
    if not security_manager.find_user(username=user):
        role = security_manager.find_role('Admin') or security_manager.add_role('Admin')
        assert security_manager.add_user(user, 'Formation', 'Admin', 'admin@formation.fr', role, os.environ['SUPERSET_ADMIN_PASSWORD']), 'Admin creation failed'
    databases = {
        'PostgreSQL formation': 'postgresql+psycopg2://' + quote_plus(os.environ['POSTGRES_USER']) + ':' + quote_plus(os.environ['POSTGRES_PASSWORD']) + '@postgres-source:5432/' + quote_plus(os.environ['POSTGRES_DB']),
        'Trino Lakehouse': 'trino://formation@trino:8080/iceberg/gold',
        'Apache Druid': 'druid://druid-router:8888/druid/v2/sql/',
    }
    for name, uri in databases.items():
        item = db.session.query(Database).filter_by(database_name=name).one_or_none()
        if item is None:
            item = Database(database_name=name)
            db.session.add(item)
        item.sqlalchemy_uri = uri
        item.allow_run_async = False
        item.expose_in_sqllab = True
    db.session.commit()
subprocess.run(['superset', 'init'], check=True)
print('SUPERSET_INIT_OK')
