"""One-off: locked_predictions PRIMARY KEY (fixture_id) -> (fixture_id, stage)
so a fixture can hold an initial and a final lock. Copies existing rows.
Idempotent: exits quietly if the composite key is already in place.

    python3 src/migrate_locked_stage.py
"""

import config
import db


def main() -> None:
    conn = db.get_connection()
    pk_cols = [r[1] for r in conn.execute("PRAGMA table_info(locked_predictions)") if r[5]]
    if pk_cols == ["fixture_id", "stage"]:
        print("locked_predictions already keyed by (fixture_id, stage)")
    else:
        schema = config.SCHEMA_PATH.read_text()
        i = schema.index("CREATE TABLE IF NOT EXISTS locked_predictions")
        create = schema[i:schema.index(");", i) + 2].replace("locked_predictions", "locked_predictions_new", 1)
        n = conn.execute("SELECT COUNT(*) FROM locked_predictions").fetchone()[0]
        conn.executescript(f"""
            BEGIN;
            DROP VIEW IF EXISTS locked_effective;
            {create}
            INSERT INTO locked_predictions_new SELECT * FROM locked_predictions;
            DROP TABLE locked_predictions;
            ALTER TABLE locked_predictions_new RENAME TO locked_predictions;
            COMMIT;
        """)
        print(f"migrated locked_predictions ({n} rows) to PRIMARY KEY (fixture_id, stage)")
    db.init_db(conn)  # (re)creates the locked_effective view
    conn.commit()
    print("locked_effective view:", conn.execute("SELECT COUNT(*) FROM locked_effective").fetchone()[0], "rows")


if __name__ == "__main__":
    main()
