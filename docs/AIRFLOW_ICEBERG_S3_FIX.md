# Airflow / Iceberg / S3 classpath fix

The Airflow -> Spark runtime smoke test reached the Iceberg table write and then
failed with:

```text
java.lang.NoClassDefFoundError:
software/amazon/awssdk/http/urlconnection/UrlConnectionHttpClient$Builder
```

The Spark runtime image already copied the AWS SDK v2 `url-connection-client`
JAR explicitly, but the Airflow image only copied the normal Maven runtime
dependencies from `spark/runtime/pom.xml`.  Because Iceberg's S3 client is
configured to use the URLConnection implementation, the Spark driver running
inside Airflow also needs this JAR.

The corrected Airflow dependency-resolver stage now:

- reads `aws.sdk.version` from `spark/runtime/pom.xml`;
- copies only `software.amazon.awssdk:url-connection-client` for that SDK version;
- avoids resolving a second modular AWS SDK dependency tree;
- verifies that the JAR contains
  `UrlConnectionHttpClient$Builder.class`;
- copies the resulting JAR set into `/opt/spark-extra-jars`, which is exposed to
  PySpark through `SPARK_DIST_CLASSPATH`.

This keeps the Airflow driver and Spark workers on the same Iceberg/S3 runtime
contract without adding another fixed version gate to the PowerShell installer.
