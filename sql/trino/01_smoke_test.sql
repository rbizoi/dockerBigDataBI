SHOW CATALOGS;
SHOW SCHEMAS FROM postgresql;
SELECT count(*) AS customers FROM postgresql.public.customers;
SELECT count(*) AS orders FROM postgresql.public.orders;
SHOW SCHEMAS FROM iceberg;
