# Airflow / PySpark dependency fix

The Airflow image no longer installs a Spark provider generation that pulls
`pyspark-client` on top of the full `pyspark` package. Both distributions share
the `pyspark` import namespace, which caused the `SparkExecutorInfo` import
failure seen during the Airflow image build.

The corrected image now:

- discovers the Airflow and Python versions already present in the base image;
- downloads the matching official Apache Airflow constraints file;
- keeps the Spark provider selected by that Airflow constraints set;
- derives the required PySpark version from `spark/runtime/pom.xml`;
- explicitly prevents `pyspark-client` from coexisting with full `pyspark`;
- runs `pip check` and Spark ML imports during the image build;
- leaves the PowerShell installer free of fixed Python/PySpark version gates.
## Iceberg S3 driver classpath

The Airflow image also resolves the AWS SDK v2 URLConnection HTTP client using
the `aws.sdk.version` property from the Spark runtime POM. This is required by
Iceberg S3FileIO when the Spark driver runs inside the Airflow container.

