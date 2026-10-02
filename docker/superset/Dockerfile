FROM apache/superset:5.0.0
USER root
RUN uv pip install --python /app/.venv/bin/python --no-cache psycopg2-binary==2.9.10 trino[sqlalchemy]==0.336.0 pydruid==0.6.9
RUN /app/.venv/bin/python -c "from sqlalchemy.dialects import registry; registry.load('postgresql.psycopg2'); registry.load('trino'); registry.load('druid')"
COPY . /app/lab/
USER superset
