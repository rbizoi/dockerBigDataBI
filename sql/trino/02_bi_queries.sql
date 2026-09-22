-- Query PostgreSQL directly through Trino.
SELECT c.country,
       count(DISTINCT o.order_id) AS orders,
       round(sum(ol.quantity * ol.unit_price), 2) AS revenue
FROM postgresql.public.customers c
JOIN postgresql.public.orders o ON o.customer_id = c.customer_id
JOIN postgresql.public.order_lines ol ON ol.order_id = o.order_id
GROUP BY c.country
ORDER BY revenue DESC;

-- Once Spark job 03 has created iceberg.gold.sales_summary:
SELECT *
FROM iceberg.gold.sales_summary
ORDER BY total_revenue DESC;

-- Federation example: relational dimension + Lakehouse aggregate.
SELECT c.country,
       count(*) AS source_customers,
       coalesce(sum(g.total_revenue), 0) AS lakehouse_revenue
FROM postgresql.public.customers c
LEFT JOIN iceberg.gold.sales_summary g
  ON g.country = c.country
GROUP BY c.country
ORDER BY lakehouse_revenue DESC;
