-- Validation / BI queries for the web-log training project.

SELECT count(*) AS total_log_events
FROM iceberg.logs.events;

SELECT log_type, count(*) AS events
FROM iceberg.logs.events
GROUP BY log_type
ORDER BY events DESC;

SELECT *
FROM iceberg.logs.traffic_hourly
ORDER BY event_hour;

SELECT event_date, path, method, requests, errors, error_rate_pct, avg_response_ms, p95_response_ms
FROM iceberg.logs.path_daily
ORDER BY errors DESC, requests DESC
LIMIT 20;

SELECT event_date, app_service, app_level, events
FROM iceberg.logs.application_daily
ORDER BY event_date, app_service, app_level;

SELECT *
FROM iceberg.ml.web_path_clusters
ORDER BY behavior_cluster, requests DESC;
