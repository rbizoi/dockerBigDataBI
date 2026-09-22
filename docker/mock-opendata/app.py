import json
import os
from pathlib import Path
from fastapi import FastAPI

app = FastAPI(title="Training OpenData API", version="1.0")
DATA_FILE = Path(os.getenv("DATA_FILE", "/data/opendata/sample.json"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/events")
def events():
    with DATA_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)
