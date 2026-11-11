"""Version Consistency Verification Service.

Ensures ACE never correlates or accepts results from mismatched
applications, versions, or commit hashes across external systems.
"""

from typing import List, Optional
from dataclasses import dataclass
from app.core.context import CertificationContext
from app.models.finding import FindingCategoryEnum, FindingStatusEnum, FindingSeverityEnum


@dataclass
class ConsistencyCheckReport:
    is_consistent: bool
    status: FindingStatusEnum
    discrepancies: List[str]
    title: str
    description: str
    remediation: Optional[str] = None


class VersionConsistencyService:
    """Validates that external evidence matches ACE certification identity."""

    @staticmethod
    def verify_consistency(
        context: CertificationContext,
        external_reports: List[dict],
    ) -> ConsistencyCheckReport:
        """Verify reported external application identities match ACE context.

        external_reports format:
        [
            {"source_system": "MYBLOCKS_RAG", "application_id": "APP-1001", "version": "1.4.2", "commit_hash": "..."},
            ...
        ]
        """
        discrepancies = []

        for report in external_reports:
            source = report.get("source_system", "UNKNOWN")
            ext_app = report.get("application_id")
            ext_ver = report.get("version")
            ext_commit = report.get("commit_hash")

            if ext_app and ext_app != context.application_id:
                discrepancies.append(
                    f"[{source}] Application ID mismatch: expected '{context.application_id}', received '{ext_app}'"
                )

            if ext_ver and ext_ver != context.application_version:
                discrepancies.append(
                    f"[{source}] Version mismatch: expected '{context.application_version}', received '{ext_ver}'"
                )

            if ext_commit and context.commit_hash and ext_commit != context.commit_hash:
                discrepancies.append(
                    f"[{source}] Commit hash mismatch: expected '{context.commit_hash}', received '{ext_commit}'"
                )

        if discrepancies:
            return ConsistencyCheckReport(
                is_consistent=False,
                status=FindingStatusEnum.NOT_VERIFIED,
                discrepancies=discrepancies,
                title="Identity & Version Consistency Discrepancy",
                description=(
                    f"Mismatched application identity detected for '{context.application_id}' (v{context.application_version}). "
                    f"Details: {'; '.join(discrepancies)}"
                ),
                remediation=(
                    "Ensure upstream systems (RAG, QA, Rule Scanner) are triggered for the exact "
                    f"application_id '{context.application_id}' and version '{context.application_version}'."
                ),
            )

        return ConsistencyCheckReport(
            is_consistent=True,
            status=FindingStatusEnum.PASS,
            discrepancies=[],
            title="Application & Version Identity Consistent",
            description=(
                f"Application '{context.application_id}' (v{context.application_version}) "
                "identity verified consistently across all reporting subsystems."
            ),
            remediation=None,
        )
