-- 013: contadores distribuidos de rate limiting con ventanas fijas.
-- Solo almacena un identificador SHA-256 derivado; no guardar IP/email en claro.
CREATE TABLE auth_rate_limit_buckets (
    bucket_key CHAR(64) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    hit_count INTEGER NOT NULL CHECK (hit_count >= 0),
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (bucket_key, window_start),
    CHECK (expires_at > window_start)
);
CREATE INDEX idx_auth_rate_limit_expiry
    ON auth_rate_limit_buckets(expires_at);
