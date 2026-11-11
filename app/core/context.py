"""Certification Context for strong identity and complete traceability."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CertificationContext:
    """Strongly typed immutable context identifying the exact execution target.

    Ensures ACE never accidentally mixes evidence or results across
    different applications, versions, commits, or submissions.
    """
    certification_id: str
    application_id: str
    application_version: str
    commit_hash: Optional[str] = None
    submission_id: Optional[str] = None
    trigger_type: str = "MANUAL"
    policy_version: str = "v1.0"
    application_version_id: Optional[int] = None

    def matches_target(
        self,
        application_id: str,
        version: str,
        commit_hash: Optional[str] = None,
    ) -> bool:
        """Verify if reported external identifiers match this certification target."""
        if self.application_id != application_id:
            return False
        if self.application_version != version:
            return False
        if commit_hash and self.commit_hash and commit_hash != self.commit_hash:
            return False
        return True
