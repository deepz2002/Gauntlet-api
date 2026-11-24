BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE scans (
    id UUID DEFAULT gen_random_uuid() NOT NULL,
    status VARCHAR(16) DEFAULT 'RUNNING' NOT NULL,
    account_ids JSONB NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    CONSTRAINT pk_scans PRIMARY KEY (id),
    CONSTRAINT ck_scans_status CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    CONSTRAINT ck_scans_account_ids CHECK (jsonb_typeof(account_ids) = 'array' AND jsonb_array_length(account_ids) > 0),
    CONSTRAINT ck_scans_lifecycle CHECK ((status = 'RUNNING' AND finished_at IS NULL) OR (status IN ('COMPLETED', 'FAILED') AND finished_at IS NOT NULL)),
    CONSTRAINT ck_scans_timestamps CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX ix_scans_started_at ON scans (started_at);

CREATE TABLE findings (
    id UUID DEFAULT gen_random_uuid() NOT NULL,
    scan_id UUID NOT NULL,
    check_id VARCHAR(64) NOT NULL,
    title TEXT NOT NULL,
    provider VARCHAR(16) NOT NULL,
    account_id TEXT NOT NULL,
    region TEXT,
    resource_id TEXT,
    status VARCHAR(16) NOT NULL,
    severity VARCHAR(16) NOT NULL,
    details TEXT NOT NULL,
    CONSTRAINT pk_findings PRIMARY KEY (id),
    CONSTRAINT ck_findings_status CHECK (status IN ('PASS', 'FAIL', 'CANNOT_SCAN')),
    CONSTRAINT ck_findings_severity CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    CONSTRAINT ck_findings_provider CHECK (provider IN ('aws', 'azure', 'gcp')),
    CONSTRAINT ck_findings_resource_id CHECK (resource_id IS NOT NULL OR status = 'CANNOT_SCAN'),
    CONSTRAINT fk_findings_scan_id_scans FOREIGN KEY(scan_id) REFERENCES scans (id) ON DELETE CASCADE
);

CREATE INDEX ix_findings_scan_status_severity ON findings (scan_id, status, severity);

CREATE INDEX ix_findings_scan_provider ON findings (scan_id, provider);

CREATE INDEX ix_findings_scan_account ON findings (scan_id, account_id);

CREATE INDEX ix_findings_scan_check ON findings (scan_id, check_id);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;
