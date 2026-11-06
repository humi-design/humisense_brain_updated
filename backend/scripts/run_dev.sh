#!/usr/bin/env bash
# Local run helper: backend on port 8000.
set -u
cd "$(dirname "$0")/.."

export HUMISENSE_DATABASE_URL="${HUMISENSE_DATABASE_URL:-sqlite+pysqlite:///$(pwd)/humisense_dev.db}"
if [ -z "${HUMISENSE_CREDENTIAL_ENCRYPTION_KEY:-}" ]; then
  export HUMISENSE_CREDENTIAL_ENCRYPTION_KEY="$(.venv/bin/python -c 'import secrets;print(secrets.token_hex(32))')"
fi
export HUMISENSE_ENVIRONMENT="${HUMISENSE_ENVIRONMENT:-development}"

.venv/bin/python - <<'PY'
from app.db.models import Base
from app.db.session import get_engine, get_session_factory
from app.connectors.bootstrap import persist_registry
from app.db import models

Base.metadata.create_all(bind=get_engine())
session = get_session_factory()()
persist_registry(session)
if not session.query(models.Tenant).filter_by(id="demo-tenant").first():
    session.add(models.Tenant(id="demo-tenant", name="Humisense Demo", slug="demo"))
    session.commit()
print("database ready")
PY

.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/humisense-backend.log 2>&1 &
echo "backend:  http://localhost:8000   (log: /tmp/humisense-backend.log)"
echo "frontend: cd ../frontend && npm run dev -- --host 0.0.0.0 --port 12000"
