"""ACE MCP Server - Exposing ACE capabilities to external applications.

Implements bidirectional MCP architecture (Direction B: ACE as a Provider).
Enables external agents/orchestrators (such as AgentGen Pro) to safely invoke
compliance certification operations without accessing internal databases directly.
"""

import json
import sys
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.exceptions import ACEException, CertificationNotFoundError, ApplicationNotFoundError
from app.models.certification import CertificationRun, CertificationStatusEnum, TriggerTypeEnum
from app.services.application_service import ApplicationService
from app.services.evidence_service import EvidenceService
from app.services.remediation_service import RemediationService

logger = get_logger("ace.mcp.server")


class ACEMCPServer:
    """Capability-oriented MCP Server for ACE Agent Compliance Engine."""

    # Authoritative tool definitions following MCP specifications
    TOOLS: List[Dict[str, Any]] = [
        {
            "name": "start_certification",
            "description": "Trigger or queue a compliance certification run for an application and version.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "application_id": {
                        "type": "string",
                        "description": "Unique identifier of the application to certify (e.g., APP-1001)",
                    },
                    "version": {
                        "type": "string",
                        "description": "Specific semantic version to certify (e.g., 1.4.2). Defaults to current registered version.",
                    },
                    "commit_hash": {
                        "type": "string",
                        "description": "Source commit hash associated with this release.",
                    },
                    "submission_id": {
                        "type": "string",
                        "description": "Upstream submission identifier from AgentGen Pro for idempotency correlation.",
                    },
                    "trigger_type": {
                        "type": "string",
                        "description": "Trigger category: MANUAL, AGENT_SUBMISSION, VERSION_UPDATE, WEBHOOK, RE_CERTIFICATION, POLICY_CHANGE.",
                        "default": "AGENT_SUBMISSION",
                    },
                    "policy_version": {
                        "type": "string",
                        "description": "Policy version against which to evaluate compliance.",
                        "default": "v1.0",
                    },
                },
                "required": ["application_id"],
            },
        },
        {
            "name": "get_certification_status",
            "description": "Retrieve current certification lifecycle status and summary for a given certification ID.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "certification_id": {
                        "type": "string",
                        "description": "Unique certification identifier (e.g., CERT-2026-000001)",
                    },
                },
                "required": ["certification_id"],
            },
        },
        {
            "name": "get_publication_status",
            "description": "Evaluate if an exact application version is verified and eligible for AgentGen Pro publication. Returns READY_TO_PUBLISH, NOT_READY, or ERROR.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "application_id": {
                        "type": "string",
                        "description": "Unique application identifier.",
                    },
                    "version": {
                        "type": "string",
                        "description": "Specific application version to query. Defaults to current version.",
                    },
                },
                "required": ["application_id"],
            },
        },
        {
            "name": "get_certification_findings",
            "description": "Retrieve structured compliance findings for a certification run across all verified categories.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "certification_id": {
                        "type": "string",
                        "description": "Unique certification run ID.",
                    },
                },
                "required": ["certification_id"],
            },
        },
        {
            "name": "get_certification_evidence",
            "description": "Retrieve collected evidence records and provenance hashes for a certification run.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "certification_id": {
                        "type": "string",
                        "description": "Unique certification run ID.",
                    },
                },
                "required": ["certification_id"],
            },
        },
        {
            "name": "get_remediation",
            "description": "Retrieve structured 5-point actionable remediation report detailing exact corrective actions for any non-passing requirements.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "certification_id": {
                        "type": "string",
                        "description": "Unique certification run ID.",
                    },
                },
                "required": ["certification_id"],
            },
        },
        {
            "name": "update_remediation_status",
            "description": "Update remediation lifecycle state for a specific finding (OPEN -> IN_PROGRESS -> RESOLVED).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "certification_id": {
                        "type": "string",
                        "description": "Unique certification run ID containing the finding.",
                    },
                    "finding_id": {
                        "type": "integer",
                        "description": "Internal finding ID to update.",
                    },
                    "finding_code": {
                        "type": "string",
                        "description": "Finding correlation code (e.g. FINDING-DOC-BRD) to update.",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["OPEN", "IN_PROGRESS", "RESOLVED"],
                        "description": "New remediation status.",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional progress notes or resolution rationale.",
                    },
                },
                "required": ["certification_id", "status"],
            },
        },
        {
            "name": "request_recertification",
            "description": "Trigger an explicit distinct re-certification run for an application after updating documentation or code.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "application_id": {
                        "type": "string",
                        "description": "Unique application ID to re-certify.",
                    },
                    "certification_id": {
                        "type": "string",
                        "description": "Optional prior certification ID to reference for metadata.",
                    },
                    "version": {
                        "type": "string",
                        "description": "Specific semantic version to certify.",
                    },
                    "submission_id": {
                        "type": "string",
                        "description": "Optional updated submission ID.",
                    },
                    "commit_hash": {
                        "type": "string",
                        "description": "Optional updated commit hash.",
                    },
                },
                "required": ["application_id"],
            },
        },
        {
            "name": "request_publication",
            "description": "Request publication of an eligible certified application version to AgentGen Pro. Revalidates policy eligibility before submitting.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "application_id": {
                        "type": "string",
                        "description": "Unique identifier of the application to publish.",
                    },
                    "version": {
                        "type": "string",
                        "description": "Specific semantic version to publish. Defaults to current version.",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional publication notes or release metadata.",
                    },
                },
                "required": ["application_id"],
            },
        },
        {
            "name": "get_publication_failure_details",
            "description": "Retrieve actionable failure details for a failed AgentGen Pro publication attempt.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "application_id": {
                        "type": "string",
                        "description": "Unique application identifier.",
                    },
                    "version": {
                        "type": "string",
                        "description": "Specific application version.",
                    },
                    "publication_id": {
                        "type": "string",
                        "description": "Optional specific publication ID.",
                    },
                },
                "required": ["application_id"],
            },
        },
        {
            "name": "verify_external_publication",
            "description": "Reconcile and authoritatively verify publication status with AgentGen Pro for in-flight or unknown publications.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "application_id": {
                        "type": "string",
                        "description": "Unique application identifier.",
                    },
                    "version": {
                        "type": "string",
                        "description": "Specific application version.",
                    },
                    "publication_id": {
                        "type": "string",
                        "description": "Optional specific publication ID.",
                    },
                },
                "required": ["application_id"],
            },
        },
    ]

    @classmethod
    def list_tools(cls) -> List[Dict[str, Any]]:
        """Return all available MCP tools supported by ACE."""
        return cls.TOOLS

    @classmethod
    def call_tool(cls, tool_name: str, arguments: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Execute a capability tool against existing core services."""
        logger.info(
            f"MCP tool call received: {tool_name}",
            extra={"event": "mcp_tool_called", "tool_name": tool_name, "arguments": arguments},
        )

        handler = getattr(cls, f"_tool_{tool_name}", None)
        if not handler:
            raise ACEException(
                message=f"MCP tool '{tool_name}' is not recognized or supported by ACE.",
                code="MCP_TOOL_NOT_FOUND",
                status_code=404,
                details={"tool_name": tool_name},
            )

        return handler(arguments, db)

    # -------------------------------------------------------------------------
    # Tool Handlers (Reusing existing service layer)
    # -------------------------------------------------------------------------

    @classmethod
    def _tool_start_certification(cls, args: Dict[str, Any], db: Session) -> Dict[str, Any]:
        from app.schemas.certification import CertificationCreate
        from app.services.certification_service import CertificationService

        app_id = args.get("application_id")
        if not app_id:
            raise ACEException("application_id is required", code="INVALID_ARGUMENT", status_code=400)

        trigger_raw = args.get("trigger_type", "AGENT_SUBMISSION")
        try:
            trigger_type = TriggerTypeEnum(trigger_raw)
        except ValueError:
            trigger_type = TriggerTypeEnum.AGENT_SUBMISSION

        cert_in = CertificationCreate(
            application_id=app_id,
            version=args.get("version"),
            commit_hash=args.get("commit_hash"),
            submission_id=args.get("submission_id"),
            trigger_type=trigger_type,
            policy_version=args.get("policy_version", "v1.0"),
        )

        service = CertificationService()
        run = service.create_certification_run(db, cert_in)

        return {
            "certification_id": run.certification_id,
            "application_id": run.application_id,
            "version": run.application_version,
            "commit_hash": run.commit_hash,
            "submission_id": run.submission_id,
            "status": run.status,
            "trigger_type": run.trigger_type,
            "policy_version": run.policy_version,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }

    @classmethod
    def _tool_get_certification_status(cls, args: Dict[str, Any], db: Session) -> Dict[str, Any]:
        from app.services.certification_service import CertificationService

        cert_id = args.get("certification_id")
        if not cert_id:
            raise ACEException("certification_id is required", code="INVALID_ARGUMENT", status_code=400)

        run, summary = CertificationService.get_certification(db, cert_id)

        return {
            "certification_id": run.certification_id,
            "application_id": run.application_id,
            "version": run.application_version,
            "status": run.status,
            "policy_version": run.policy_version,
            "submission_id": run.submission_id,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "findings_summary": {
                "total": summary.total,
                "passed": summary.passed,
                "failed": summary.failed,
                "not_verified": summary.not_verified,
                "partial": summary.partial,
            },
        }

    @classmethod
    def _tool_get_publication_status(cls, args: Dict[str, Any], db: Session) -> Dict[str, Any]:
        from app.services.publication_service import PublicationService

        app_id = args.get("application_id")
        if not app_id:
            raise ACEException("application_id is required", code="INVALID_ARGUMENT", status_code=400)

        app = ApplicationService.get_application(db, app_id)
        target_version = args.get("version") or app.current_version

        service = PublicationService()
        stat = service.get_publication_status(db, app_id, target_version)

        # Fetch latest completed or active certification run for this exact version
        latest_run = (
            db.query(CertificationRun)
            .filter(
                CertificationRun.application_id == app.application_id,
                CertificationRun.application_version == target_version,
            )
            .order_by(CertificationRun.created_at.desc(), CertificationRun.id.desc())
            .first()
        )

        if latest_run and latest_run.status == CertificationStatusEnum.READY_TO_PUBLISH.value:
            status_val = CertificationStatusEnum.READY_TO_PUBLISH.value
            is_ready = True
        elif latest_run and latest_run.status == CertificationStatusEnum.ERROR.value:
            status_val = CertificationStatusEnum.ERROR.value
            is_ready = False
        else:
            status_val = CertificationStatusEnum.NOT_READY.value
            is_ready = False

        return {
            "application_id": app.application_id,
            "application_name": app.name,
            "version": target_version,
            "latest_certification_id": latest_run.certification_id if latest_run else None,
            "publication_status": status_val,
            "is_ready_to_publish": is_ready,
            "evaluated_at": latest_run.completed_at.isoformat() if latest_run and latest_run.completed_at else None,
            "is_eligible_for_publication": stat["is_eligible_for_publication"],
            "publication_record_status": stat["publication_status"],
            "is_published": stat["is_published"],
            "latest_publication_id": stat["latest_publication_id"],
            "external_publication_id": stat["external_publication_id"],
            "last_published_at": stat["last_published_at"],
        }

    @classmethod
    def _tool_get_certification_findings(cls, args: Dict[str, Any], db: Session) -> Dict[str, Any]:
        from app.services.certification_service import CertificationService

        cert_id = args.get("certification_id")
        if not cert_id:
            raise ACEException("certification_id is required", code="INVALID_ARGUMENT", status_code=400)

        findings = CertificationService.get_findings(db, cert_id)

        return {
            "certification_id": cert_id,
            "total_findings": len(findings),
            "findings": [
                {
                    "id": f.id,
                    "check_id": f.check_id,
                    "requirement_id": f.requirement_id,
                    "finding_code": f.finding_code,
                    "category": f.category,
                    "status": f.status,
                    "remediation_status": getattr(f, "remediation_status", "OPEN"),
                    "severity": f.severity,
                    "title": f.title,
                    "description": f.description,
                    "remediation": f.remediation,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
                for f in findings
            ],
        }

    @classmethod
    def _tool_get_certification_evidence(cls, args: Dict[str, Any], db: Session) -> Dict[str, Any]:
        cert_id = args.get("certification_id")
        if not cert_id:
            raise ACEException("certification_id is required", code="INVALID_ARGUMENT", status_code=400)

        evidence_list = EvidenceService.get_evidence_for_certification(db, cert_id)

        return {
            "certification_id": cert_id,
            "total_evidence": len(evidence_list),
            "evidence": [
                {
                    "id": ev.id,
                    "check_id": ev.check_id,
                    "finding_id": ev.finding_id,
                    "source_system": ev.source_system,
                    "source_reference": ev.source_reference,
                    "evidence_type": ev.evidence_type,
                    "evidence_data": ev.evidence_data,
                    "source_version": ev.source_version,
                    "source_run_id": ev.source_run_id,
                    "hash": ev.hash,
                    "confidence": ev.confidence,
                    "collected_at": ev.collected_at.isoformat() if ev.collected_at else None,
                }
                for ev in evidence_list
            ],
        }

    @classmethod
    def _tool_get_remediation(cls, args: Dict[str, Any], db: Session) -> Dict[str, Any]:
        from app.services.certification_service import CertificationService

        cert_id = args.get("certification_id")
        if not cert_id:
            raise ACEException("certification_id is required", code="INVALID_ARGUMENT", status_code=400)

        run, _ = CertificationService.get_certification(db, cert_id)
        findings = CertificationService.get_findings(db, cert_id)

        report = RemediationService.generate_remediation_report(
            certification_id=run.certification_id,
            application_id=run.application_id,
            application_version=run.application_version,
            overall_status=run.status,
            findings=findings,
        )

        return {
            "certification_id": report.certification_id,
            "application_id": report.application_id,
            "application_version": report.application_version,
            "overall_status": report.overall_status,
            "actionable_items_count": report.actionable_items_count,
            "items": [
                {
                    "finding_id": item.finding_id,
                    "requirement": item.requirement,
                    "finding_code": item.finding_code,
                    "check_id": item.check_id,
                    "status": item.status,
                    "remediation_status": item.remediation_status,
                    "severity": item.severity,
                    "reason": item.reason,
                    "missing_or_failed_evidence": item.missing_or_failed_evidence,
                    "required_action": item.required_action,
                    "target_system": item.target_system,
                }
                for item in report.items
            ],
        }

    @classmethod
    def _tool_update_remediation_status(cls, args: Dict[str, Any], db: Session) -> Dict[str, Any]:
        cert_id = args.get("certification_id")
        if not cert_id:
            raise ACEException("certification_id is required", code="INVALID_ARGUMENT", status_code=400)
        status_val = args.get("status") or args.get("remediation_status")
        if not status_val:
            raise ACEException("status is required", code="INVALID_ARGUMENT", status_code=400)

        finding = RemediationService.update_remediation_status(
            db=db,
            certification_id=cert_id,
            status=status_val,
            finding_id=args.get("finding_id"),
            finding_code=args.get("finding_code"),
            notes=args.get("notes"),
            actor="mcp_client",
        )

        return {
            "certification_id": cert_id,
            "finding_id": finding.id,
            "finding_code": finding.finding_code,
            "requirement_id": finding.requirement_id,
            "remediation_status": finding.remediation_status,
            "updated_at": finding.updated_at.isoformat() if finding.updated_at else None,
            "message": f"Remediation status updated to {finding.remediation_status}",
        }

    @classmethod
    def _tool_request_recertification(cls, args: Dict[str, Any], db: Session) -> Dict[str, Any]:
        from app.services.certification_service import CertificationService

        app_id = args.get("application_id")
        if not app_id:
            raise ACEException("application_id is required", code="INVALID_ARGUMENT", status_code=400)

        service = CertificationService()
        new_run = service.request_recertification(
            db=db,
            application_id=app_id,
            certification_id=args.get("certification_id"),
            version=args.get("version"),
            submission_id=args.get("submission_id"),
            commit_hash=args.get("commit_hash"),
            actor="mcp_client",
        )

        return {
            "certification_id": new_run.certification_id,
            "application_id": new_run.application_id,
            "version": new_run.application_version,
            "submission_id": new_run.submission_id,
            "trigger_type": new_run.trigger_type,
            "status": new_run.status,
            "created_at": new_run.created_at.isoformat() if new_run.created_at else None,
            "message": "Re-certification run queued successfully",
        }

    @classmethod
    def _tool_request_publication(cls, args: Dict[str, Any], db: Session) -> Dict[str, Any]:
        from app.services.publication_service import PublicationService

        app_id = args.get("application_id")
        if not app_id:
            raise ACEException("application_id is required", code="INVALID_ARGUMENT", status_code=400)

        service = PublicationService()
        record = service.request_publication(
            db=db,
            application_id=app_id,
            version=args.get("version"),
            notes=args.get("notes"),
            actor="mcp_client",
        )

        return {
            "publication_id": record.publication_id,
            "application_id": record.application_id,
            "version": record.application_version,
            "certification_id": record.certification_id,
            "submission_id": record.submission_id,
            "status": record.status,
            "external_publication_id": record.external_publication_id,
            "external_status": record.external_status,
            "error_code": record.error_code,
            "error_message": record.error_message,
            "is_published": record.status == "PUBLISHED",
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "confirmed_at": record.confirmed_at.isoformat() if record.confirmed_at else None,
            "message": f"Publication request processed: status is {record.status}",
        }

    @classmethod
    def _tool_get_publication_failure_details(cls, args: Dict[str, Any], db: Session) -> Dict[str, Any]:
        from app.services.publication_service import PublicationService

        app_id = args.get("application_id")
        if not app_id:
            raise ACEException("application_id is required", code="INVALID_ARGUMENT", status_code=400)

        service = PublicationService()
        rec = service.get_failure_details(
            db=db,
            application_id=app_id,
            version=args.get("version"),
            publication_id=args.get("publication_id"),
        )
        if not rec:
            raise ACEException(
                f"No failure records found for {app_id}",
                code="PUBLICATION_NOT_FOUND",
                status_code=404,
            )

        return {
            "publication_id": rec.publication_id,
            "application_id": rec.application_id,
            "version": rec.application_version,
            "certification_id": rec.certification_id,
            "status": rec.status,
            "error_code": rec.error_code,
            "error_message": rec.error_message,
            "last_attempt_at": (rec.updated_at or rec.created_at).isoformat(),
            "retry_permitted": True,
            "retry_count": rec.retry_count,
        }

    @classmethod
    def _tool_verify_external_publication(cls, args: Dict[str, Any], db: Session) -> Dict[str, Any]:
        from app.services.publication_service import PublicationService

        app_id = args.get("application_id")
        if not app_id:
            raise ACEException("application_id is required", code="INVALID_ARGUMENT", status_code=400)

        service = PublicationService()
        rec = service.verify_external_publication(
            db=db,
            application_id=app_id,
            version=args.get("version"),
            publication_id=args.get("publication_id"),
            actor="mcp_client",
        )

        return {
            "publication_id": rec.publication_id,
            "application_id": rec.application_id,
            "version": rec.application_version,
            "status": rec.status,
            "external_publication_id": rec.external_publication_id,
            "is_published": rec.status == "PUBLISHED",
            "confirmed_at": rec.confirmed_at.isoformat() if rec.confirmed_at else None,
            "error_message": rec.error_message,
        }

    # -------------------------------------------------------------------------
    # JSON-RPC 2.0 Dispatcher
    # -------------------------------------------------------------------------

    @classmethod
    def handle_jsonrpc(cls, request_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Dispatch standard MCP JSON-RPC 2.0 requests."""
        req_id = request_data.get("id")
        method = request_data.get("method")
        params = request_data.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "ace-compliance-engine",
                        "version": "0.1.0",
                    },
                    "capabilities": {
                        "tools": {},
                    },
                },
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": cls.list_tools(),
                },
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            try:
                result_data = cls.call_tool(tool_name, arguments, db)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result_data, indent=2),
                            }
                        ],
                        "structuredContent": result_data,
                        "isError": False,
                    },
                }
            except ACEException as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({
                                    "error": exc.code,
                                    "message": exc.message,
                                    "details": exc.details,
                                }),
                            }
                        ],
                        "isError": True,
                    },
                }
            except Exception as exc:
                logger.error(f"Unexpected error in MCP tool call: {exc}", exc_info=True)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32603,
                        "message": f"Internal tool execution error: {str(exc)}",
                    },
                }

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method '{method}' not found or unsupported by ACE MCP server.",
                },
            }


def run_stdio() -> None:
    """Run ACE MCP server using standard I/O for MCP CLI host integration."""
    from app.core.database import SessionLocal

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            db = SessionLocal()
            try:
                resp = ACEMCPServer.handle_jsonrpc(req, db)
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
            finally:
                db.close()
        except Exception as exc:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {str(exc)}"},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio()
