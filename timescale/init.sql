CREATE TABLE sensor_reading (
    time            TIMESTAMPTZ NOT NULL,
    site_id         TEXT NOT NULL,
    coletor_id      TEXT NOT NULL,
    sensor_id       TEXT NOT NULL,
    area_id         TEXT NOT NULL,
    tipo_medida     TEXT NOT NULL,
    valor           DOUBLE PRECISION NOT NULL,
    unidade         TEXT NOT NULL,
    protocolo_origem TEXT NOT NULL,
    status_leitura  TEXT NOT NULL
);

SELECT create_hypertable('sensor_reading', by_range('time'));
SELECT add_dimension('sensor_reading', by_hash('site_id', 4));

CREATE INDEX idx_sensor_reading_sensor_time ON sensor_reading (sensor_id, time DESC);

ALTER TABLE sensor_reading SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'sensor_id',
    timescaledb.compress_orderby = 'time DESC'
);
SELECT add_compression_policy('sensor_reading', INTERVAL '7 days');

CREATE MATERIALIZED VIEW sensor_reading_hourly
WITH (timescaledb.continuous) AS
SELECT
    sensor_id,
    time_bucket('1 hour', time) AS bucket,
    min(valor) AS valor_min,
    max(valor) AS valor_max,
    avg(valor) AS valor_avg
FROM sensor_reading
GROUP BY sensor_id, bucket
WITH NO DATA;

SELECT add_continuous_aggregate_policy('sensor_reading_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

CREATE MATERIALIZED VIEW sensor_reading_daily
WITH (timescaledb.continuous) AS
SELECT
    sensor_id,
    time_bucket('1 day', time) AS bucket,
    min(valor) AS valor_min,
    max(valor) AS valor_max,
    avg(valor) AS valor_avg
FROM sensor_reading
GROUP BY sensor_id, bucket
WITH NO DATA;

SELECT add_continuous_aggregate_policy('sensor_reading_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day');

CREATE OR REPLACE FUNCTION notify_sensor_reading() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify(
        'sensor_reading_new',
        json_build_object(
            'sensor_id', NEW.sensor_id,
            'time', extract(epoch from NEW.time) * 1000,
            'valor', NEW.valor
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS sensor_reading_notify ON sensor_reading;
CREATE TRIGGER sensor_reading_notify
    AFTER INSERT ON sensor_reading
    FOR EACH ROW EXECUTE FUNCTION notify_sensor_reading();
