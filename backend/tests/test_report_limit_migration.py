from __future__ import annotations

import sqlite3
from pathlib import Path

from app.infrastructure.migration_runner import run_migrations


def test_report_limit_migration_preserves_existing_details(tmp_path: Path) -> None:
    database = tmp_path / "fcc.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE alembic_version (
                version_num VARCHAR(32) NOT NULL PRIMARY KEY
            );
            INSERT INTO alembic_version (version_num) VALUES ('0009_run_reports');

            CREATE TABLE user (
                id VARCHAR(32) NOT NULL PRIMARY KEY,
                role VARCHAR(16) NOT NULL
            );
            INSERT INTO user (id, role) VALUES ('operator-user-0001', 'operator');
            INSERT INTO user (id, role) VALUES ('admin-user-0002', 'admin');

            CREATE TABLE run (
                request_id VARCHAR(32) NOT NULL PRIMARY KEY
            );
            INSERT INTO run (request_id) VALUES ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');

            CREATE TABLE run_report (
                run_request_id VARCHAR(32) NOT NULL PRIMARY KEY,
                title VARCHAR(120) NOT NULL,
                item_label VARCHAR(40) NOT NULL,
                schema_json TEXT NOT NULL,
                expected_total INTEGER,
                reported_total INTEGER NOT NULL,
                success_count INTEGER NOT NULL,
                failed_count INTEGER NOT NULL,
                no_data_count INTEGER NOT NULL,
                skipped_count INTEGER NOT NULL,
                unfinished_count INTEGER NOT NULL,
                validation_error_count INTEGER NOT NULL,
                status VARCHAR(16) NOT NULL,
                started_at INTEGER NOT NULL,
                completion_requested_at INTEGER,
                completed_at INTEGER,
                details_purged_at INTEGER,
                CONSTRAINT ck_run_report_status CHECK (status IN ('OPEN', 'COMPLETE', 'INCOMPLETE')),
                CONSTRAINT ck_run_report_expected_total CHECK (
                    expected_total IS NULL OR (expected_total >= 0 AND expected_total <= 5000)
                ),
                CONSTRAINT ck_run_report_reported_total CHECK (
                    reported_total >= 0 AND reported_total <= 5000
                ),
                CONSTRAINT ck_run_report_counts CHECK (
                    success_count >= 0 AND failed_count >= 0 AND no_data_count >= 0
                    AND skipped_count >= 0 AND unfinished_count >= 0
                ),
                CONSTRAINT ck_run_report_validation_errors CHECK (validation_error_count >= 0),
                FOREIGN KEY(run_request_id) REFERENCES run (request_id) ON DELETE CASCADE
            );
            INSERT INTO run_report VALUES (
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', '测试报表', '记录', '{}', 1, 1,
                1, 0, 0, 0, 0, 0, 'COMPLETE', 1800000000, 1800000000, 1800000000, NULL
            );

            CREATE TABLE run_report_item (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                run_request_id VARCHAR(32) NOT NULL,
                sequence INTEGER NOT NULL,
                status VARCHAR(16) NOT NULL,
                reason VARCHAR(1000) NOT NULL,
                reason_code VARCHAR(80),
                values_json TEXT NOT NULL,
                reported_at_ms INTEGER NOT NULL,
                CONSTRAINT ck_run_report_item_status CHECK (
                    status IN ('SUCCESS', 'FAILED', 'NO_DATA', 'SKIPPED', 'UNFINISHED')
                ),
                FOREIGN KEY(run_request_id) REFERENCES run_report (run_request_id) ON DELETE CASCADE,
                CONSTRAINT uq_run_report_item_sequence UNIQUE (run_request_id, sequence)
            );
            CREATE INDEX ix_run_report_item_run_sequence
                ON run_report_item (run_request_id, sequence);
            CREATE INDEX ix_run_report_item_run_status
                ON run_report_item (run_request_id, status, sequence);
            INSERT INTO run_report_item VALUES (
                7, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 1, 'SUCCESS', '完成', NULL,
                '{"recordId":"R-001"}', 1800000000000
            );
            """
        )

    run_migrations(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0011_menu_grants",
        )
        assert connection.execute(
            "SELECT menu_key FROM user_menu_grant WHERE user_id = 'operator-user-0001' ORDER BY menu_key"
        ).fetchall() == [("runs",), ("schedules",), ("workspace",)]
        assert connection.execute(
            "SELECT COUNT(*) FROM user_menu_grant WHERE user_id = 'admin-user-0002'"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT id, sequence, status, values_json FROM run_report_item"
        ).fetchone() == (7, 1, "SUCCESS", '{"recordId":"R-001"}')
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'run_report'"
        ).fetchone()[0]
        assert "1000000" in table_sql

        connection.execute(
            "INSERT INTO run (request_id) VALUES ('bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')"
        )
        connection.execute(
            """
            INSERT INTO run_report VALUES (
                'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', '五万条报表', '记录', '{}', 50000, 0,
                0, 0, 0, 0, 0, 0, 'OPEN', 1800000001, NULL, NULL, NULL
            )
            """
        )
