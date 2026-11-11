# ACE — Agent Compliance Engine

**Autonomous certification platform for AgentGen Pro.**

ACE certifies AI agents and web applications before they are allowed to be published or imported.

---

## 1. Architectural Principles

- **90% Backend / 10% Frontend:** Focused on a rock-solid, production-grade certification and verification engine.
- **Strict Identity & Non-Cross-Contamination:** ACE enforces strong certification identity (`certification_id`, `application_id`, `application_version`, `commit_hash`, `submission_id`). ACE **never** accidentally mixes evidence, runs, or checks from different applications, versions, or external runs.
- **Deterministic Policy Engine:**
  - `READY_TO_PUBLISH` is awarded **only** when all mandatory checks and findings pass with verified evidence.
  - If any check or finding is `NOT_VERIFIED`, `FAIL`, `PARTIAL`, or `ERROR`, the status evaluates conservatively to `NOT_READY`.
  - **Forbidden terms:** ACE **never** uses `BLOCKED` or `REJECTED`. Instead, it provides actionable remediation answering the 5 key questions: What failed, Why, What evidence is missing, What exact action is required, and Which external system must be checked again.
- **Idempotency & Concurrency:** Controlled state transitions (`QUEUED` $\to$ `RUNNING` $\to$ `READY_TO_PUBLISH` / `NOT_READY` / `ERROR`) protect against race conditions and duplicate submission events.

---

## 2. Technology Stack

- **Python 3.12+**
- **FastAPI** (Async Web API & OpenAPI documentation)
- **Pydantic v2 & Pydantic-Settings** (Type validation and environment config)
- **SQLAlchemy 2.x & Alembic** (ORM and database migrations)
- **MySQL 8.x** (Primary relational database `ace_db`)
- **PyMySQL & Cryptography** (MySQL DBAPI client driver)
- **Redis 7.x & Celery 5.x** (Distributed asynchronous background tasks)
- **httpx** (Asynchronous HTTP integration client)
- **pytest & pytest-asyncio** (Comprehensive test suite with 35 tests)
- **Docker & Docker Compose** (Containerization and orchestration)

---

## 3. Project Structure

```
ace/
├── app/
│   ├── main.py                     # FastAPI application entrypoint, lifespan, and global exception handlers
│   ├── api/
│   │   ├── health.py               # Liveness (/health) and MySQL readiness (/health/ready)
│   │   ├── applications.py         # Application registration, versions, and status lookup
│   │   ├── certifications.py       # Certification initiation, checks, evidence, findings, audit, remediation
│   │   └── webhooks.py             # AgentGen Pro webhook receiver placeholders
│   ├── core/
│   │   ├── config.py               # Pydantic BaseSettings environment configuration
│   │   ├── context.py              # Strongly-typed immutable CertificationContext
│   │   ├── database.py             # SQLAlchemy engine, session maker, get_db dependency
│   │   ├── security.py             # Cryptographic ID generator and constant-time token comparison
│   │   ├── logging.py              # Structured JSON logging and sensitive credential masking
│   │   └── exceptions.py           # Domain exceptions and uniform JSON error envelopes
│   ├── models/
│   │   ├── application.py          # Application ORM model
│   │   ├── application_version.py  # ApplicationVersion ORM model (multi-version support)
│   │   ├── certification.py        # CertificationRun ORM model (version link, submission_id, triggers)
│   │   ├── certification_check.py  # CertificationCheck ORM model (individual verifications)
│   │   ├── requirement.py          # Requirement ORM model (governance requirements)
│   │   ├── finding.py              # CertificationFinding ORM model (linked to checks and requirements)
│   │   ├── evidence.py             # Structured JSON Evidence ORM model (with provenance)
│   │   ├── integration_run.py      # IntegrationRun ORM model (external run correlation)
│   │   └── audit_event.py          # Immutable AuditEvent ORM model
│   ├── schemas/
│   │   ├── application.py          # Application request/response schemas
│   │   ├── application_version.py  # Version request/response schemas
│   │   ├── certification.py        # Certification run schemas
│   │   ├── certification_check.py  # Check verification schemas
│   │   ├── finding.py              # Finding response schemas
│   │   ├── evidence.py             # Evidence schemas and list response
│   │   ├── requirement.py          # Requirement schemas
│   │   ├── remediation.py          # Actionable remediation report schema
│   │   └── audit_event.py          # Audit event and trail schemas
│   ├── services/
│   │   ├── application_service.py  # Application registration and version management
│   │   ├── certification_service.py# 10-stage certification pipeline orchestrator
│   │   ├── evidence_service.py     # Evidence recording, integration runs, and audit trail
│   │   ├── version_consistency_service.py # Cross-subsystem identity and version verifier
│   │   ├── policy_engine.py        # Conservative deterministic publication policy engine
│   │   └── remediation_service.py  # Structured actionable remediation generator
│   ├── workers/
│   │   ├── celery_app.py           # Celery application configuration
│   │   └── certification_worker.py # Background task for asynchronous certification execution
│   └── integrations/
│       ├── __init__.py             # Public export of integration protocols
│       └── contracts.py            # Interfaces for MyBlocks RAG, QA, and 9-rule engine
├── migrations/
│   ├── env.py                      # Alembic migration runner
│   ├── script.py.mako              # Migration template
│   └── versions/
│       ├── 0001_initial_ace_tables.py           # Initial 5 core tables
│       └── 0002_phase2_certification_models.py  # Phase 2 tables, alterations, and indexes
├── tests/
│   ├── conftest.py                 # Pytest fixtures, in-memory SQLite with StaticPool, mocked delay
│   ├── test_health.py              # Health and readiness probe tests
│   ├── test_applications.py        # Application registration, uniqueness, retrieval tests
│   ├── test_versions.py            # Application multiple versions tests
│   ├── test_certifications.py      # Certification workflow and findings tests
│   ├── test_checks_and_evidence.py # Checks, evidence provenance, integration runs, audit trail
│   ├── test_version_consistency.py # Cross-subsystem version matching and mismatch tests
│   ├── test_concurrency_and_idempotency.py # Idempotent submissions and controlled state transitions
│   ├── test_phase2_policy_and_remediation.py # Policy engine and 5-question remediation report
│   └── test_worker_and_pipeline.py # 10-stage pipeline execution tests
├── Dockerfile                      # Production container image
├── docker-compose.yml              # ACE API, MySQL, Redis, and Celery worker
├── requirements.txt                # Pinned production and test dependencies
├── alembic.ini                     # Alembic configuration
├── .env.example                    # Environment variables template
├── .gitignore                      # Git ignore file
└── README.md                       # Documentation
```

---

## 4. 10-Stage Certification Pipeline

Every certification run passes through an explicit, auditable 10-stage pipeline:

```
 1. Create CertificationContext (strongly-typed identity target)
 2. Create Certification Checks (DOCUMENT, QA, RULE, VERSION)
 3. Execute Verification Stages (interfaces & subsystem placeholders)
 4. Collect Structured Evidence (check_id, source provenance, hashes)
 5. Create Findings (linked to check_id and requirement_id)
 6. Verify Consistency (VersionConsistencyService cross-check)
 7. Evaluate Policy (PolicyEngine deterministic decision)
 8. Generate Remediation (RemediationService 5-point report)
 9. Persist Audit Trail (immutable audit event logging)
10. Complete Certification (controlled state transition)
```

---

## 5. Database Schema (MySQL 8.x)

Database Name: `ace_db`

### Core Tables:

1. **`applications`**: Registered AI agents and web applications.
2. **`application_versions`**: Multi-version support with `uq_application_versions_app_version` unique constraint.
3. **`certification_runs`**: Certification runs tracking `application_version_id`, `submission_id`, `trigger_type`, `policy_version`, and lifecycle timestamps.
4. **`certification_checks`**: Individual verifications (`DOCUMENT`, `QA`, `RULE`, `VERSION`, `SYSTEM`, `INTEGRATION`).
5. **`requirements`**: Catalog of governance requirements (`DOC-REQ-17`, `RULE-SET-9`, etc.).
6. **`certification_findings`**: Evaluation findings linked to checks and requirements.
7. **`evidence`**: Evidence artifacts with source version, run ID, timestamp, and payload hash.
8. **`integration_runs`**: Traceability records correlating external runs (e.g. MyBlocks QA run ID, 9-rule scan ID).
9. **`audit_events`**: Immutable audit logs of all lifecycle state transitions.

---

## 6. Quick Start with Docker Compose

```bash
# 1. Copy environment example
cp .env.example .env

# 2. Build and launch all containers
docker compose up -d --build

# 3. View logs
docker compose logs -f api
```

The services start on:
- **API & OpenAPI Docs:** `http://localhost:8000/docs`
- **Health check:** `http://localhost:8000/health`
- **Readiness check:** `http://localhost:8000/health/ready`
- **MySQL Database:** `localhost:3306` (`ace_db`)
- **Redis:** `localhost:6379`

---

## 7. Local Development Setup

```bash
# 1. Activate Python virtual environment
.venv\Scripts\activate

# 2. Apply database migrations
alembic upgrade head

# 3. Start Celery worker
celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=2

# 4. Start FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

---

## 8. MyBlocks RAG Integration (Phase 3)

ACE integrates with MyBlocks RAG to semantically verify all 17 mandatory document categories:
`BRD`, `TRD`, `SCOPE`, `SLA`, `SOW`, `MARKET_RESEARCH`, `FRD`, `USER_STORIES`, `USE_CASES`, `BUSINESS_LOGIC`, `TEST_PLAN`, `TEST_CASES`, `API_DOCUMENTATION`, `AGENT_SPEC`, `CR`, `PR`, `OTHER`.

### Environment Configuration
```env
# Authoritative MyBlocks RAG endpoint
MYBLOCKS_RAG_BASE_URL=https://myblocks.in/myblock_private
MYBLOCKS_RAG_API_KEY=your_rag_api_key_here
MYBLOCKS_RAG_TIMEOUT=10.0
```
*Note: If `MYBLOCKS_RAG_API_KEY` is not provided or the endpoint is unauthenticated, ACE returns deterministic `NOT_VERIFIED` for the 17 categories. Cross-version evidence is rejected.*

---

## 9. MCP Integration (Bidirectional)

ACE operates as both an **MCP Provider (Server)** and **MCP Consumer (Client)**.

### Direction B — ACE as Provider (Exposing MCP)
External systems (e.g. AgentGen Pro) can call ACE MCP tools via HTTP POST (`/api/v1/mcp` or `/mcp`) or standard I/O:
```bash
# Start ACE MCP server via stdio
python -m app.mcp.server
```
Exposed Tools:
- `start_certification`
- `get_certification_status`
- `get_publication_status`
- `get_certification_findings`
- `get_certification_evidence`
- `get_remediation`

### Direction A — ACE as Consumer (Calling External MCP)
ACE queries external MCP servers (such as MyBlocks RAG MCP) using `ExternalMCPClient`.
Configure via environment:
```env
MYBLOCKS_RAG_MCP_URL=https://myblocks.in/mcp
MYBLOCKS_RAG_MCP_AUTH_TOKEN=your_token_here
```

---

## 10. MyBlocks QA Integration (Phase 4)

ACE integrates with MyBlocks QA (`https://myblocks.in/qa_app/`) to verify authoritative QA status for the exact certified application/version:

### Environment Configuration
```env
# MyBlocks QA MCP Endpoint (Preferred)
MYBLOCKS_QA_MCP_URL=https://myblocks.in/qa/mcp
MYBLOCKS_QA_MCP_AUTH_TOKEN=your_qa_mcp_token_here
MYBLOCKS_QA_MCP_TIMEOUT=15.0

# MyBlocks QA HTTP API Endpoint (Fallback)
MYBLOCKS_QA_BASE_URL=https://myblocks.in/qa_app
MYBLOCKS_QA_API_KEY=your_qa_api_key_here
MYBLOCKS_QA_TIMEOUT=10.0
```
*Note: If unconfigured or unreachable, QA returns `NOT_VERIFIED` resulting in `NOT_READY`. Cross-version evidence is strictly rejected.*

---

## 11. 9-Rule Agent Evaluation Integration (Phase 5)

ACE connects to the external AgentGen / Agent Rule Evaluation application via MCP to evaluate the 9 mandatory rules for the exact certified application/version:
1. Goal/objective
2. AI/LLM reasoning
3. Ability to take actions
4. Tool/function calling
5. Autonomous decision making
6. Execution/agent loop
7. Environment/context
8. Observation of results
9. Adaptation/re-planning

### Environment Configuration
```env
# 9-Rule Agent Evaluation MCP Endpoint (Preferred)
RULE_ENGINE_MCP_URL=https://<rule-engine-host>/mcp
RULE_ENGINE_MCP_AUTH_TOKEN=your_rule_mcp_token_here
RULE_ENGINE_MCP_TIMEOUT=15.0

# 9-Rule Agent Evaluation HTTP API Endpoint (Fallback)
RULE_ENGINE_BASE_URL=https://<rule-engine-api-host>
RULE_ENGINE_API_KEY=your_rule_api_key_here
RULE_ENGINE_TIMEOUT=10.0
```
*Note: If unconfigured, unreachable, incomplete (<9 rules), or version-mismatched, rule check evaluates to `NOT_VERIFIED` resulting in deterministic `NOT_READY`. If any rule fails, status is `FAIL` resulting in `NOT_READY`.*

---

## 12. Running Tests

```bash
# Run complete test suite (53 tests)
pytest tests -v
```

---

## 11. API Reference

Interactive OpenAPI documentation is live at [`/docs`](http://localhost:8000/docs) and [`/redoc`](http://localhost:8000/redoc).

### Health & Readiness
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe returning app name, environment, and version |
| `GET` | `/health/ready` | Readiness probe verifying live MySQL database connectivity |

### Applications & Versions
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/applications` | Register a new application and its initial version |
| `GET` | `/api/v1/applications/{application_id}` | Retrieve application metadata |
| `GET` | `/api/v1/applications/{application_id}/status` | Get latest certification status for application |
| `GET` | `/api/v1/applications` | List registered applications (paginated) |
| `POST` | `/api/v1/applications/{application_id}/versions` | Register a new application version |
| `GET` | `/api/v1/applications/{application_id}/versions` | List all registered versions for an application |

### Certifications
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/certifications` | Queue background certification run (idempotent for duplicate submissions) |
| `GET` | `/api/v1/certifications/{certification_id}` | Retrieve run status, timestamps, and findings summary |
| `GET` | `/api/v1/certifications/{certification_id}/findings` | Retrieve all findings and remediation instructions |
| `GET` | `/api/v1/certifications/{certification_id}/checks` | Retrieve all checks executed during certification |
| `GET` | `/api/v1/certifications/{certification_id}/evidence` | Retrieve all collected evidence records |
| `GET` | `/api/v1/certifications/{certification_id}/audit` | Retrieve complete immutable audit trail |
| `GET` | `/api/v1/certifications/{certification_id}/remediation` | Retrieve structured 5-point remediation report |

### Webhooks
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/webhooks/agentgen` | Webhook receiver placeholder for AgentGen Pro |
