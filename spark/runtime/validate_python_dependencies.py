"""Fail the Spark image build if a requested notebook dependency is unusable."""

from importlib import import_module


MODULES = (
    "cairo",
    "jupyterlab",
    "sql",
    "psycopg2",
    "cx_Oracle",
    "pydot",
    "yaml",
    "pyarrow",
    "colour",
    "matplotlib",
    "seaborn",
    "plotly",
    "pygraphviz",
    "numpy",
    "pandas",
    "skimage",
    "sklearn",
    "yellowbrick",
    "lightgbm",
    "xgboost",
    "catboost",
    "optuna",
    "kneed",
    "imblearn",
    "py4j",
    "pyspark",
)


for module_name in MODULES:
    import_module(module_name)

from pyspark.ml.clustering import KMeans  # noqa: E402,F401
from pyspark.ml.feature import StandardScaler, VectorAssembler  # noqa: E402,F401

print(f"SPARK_ML_JUPYTER_PYTHON_OK imports={len(MODULES)}")
