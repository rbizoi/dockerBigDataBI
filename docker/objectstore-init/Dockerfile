FROM python:3.12.14-slim-bookworm
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && useradd --create-home --uid 10001 --user-group app
COPY init_s3.py /app/init_s3.py
USER app
ENTRYPOINT ["python", "/app/init_s3.py"]
