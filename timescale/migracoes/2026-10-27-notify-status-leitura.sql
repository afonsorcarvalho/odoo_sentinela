-- Idempotente: so' substitui a funcao do trigger; nao toca dados.
CREATE OR REPLACE FUNCTION notify_sensor_reading() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify(
        'sensor_reading_new',
        json_build_object(
            'sensor_id', NEW.sensor_id,
            'site_id', NEW.site_id,
            'time', extract(epoch from NEW.time) * 1000,
            'valor', NEW.valor,
            'status_leitura', NEW.status_leitura
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
