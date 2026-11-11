from sqlalchemy import create_engine, text
from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.DATABASE_URL)
with engine.connect() as conn:
    # Check if column exists
    res = conn.execute(text("SHOW COLUMNS FROM certification_findings LIKE 'remediation_status'")).fetchone()
    if not res:
        print("Adding column remediation_status to certification_findings...")
        conn.execute(text("ALTER TABLE certification_findings ADD COLUMN remediation_status VARCHAR(32) NOT NULL DEFAULT 'OPEN', ADD INDEX ix_certification_findings_remediation_status (remediation_status)"))
        conn.commit()
        print("Column added successfully!")
    else:
        print("Column remediation_status already exists.")
