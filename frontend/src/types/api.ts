export type CertificationStatus = 'QUEUED' | 'RUNNING' | 'READY_TO_PUBLISH' | 'NOT_READY' | 'ERROR';
export type CheckStatus = 'PENDING' | 'RUNNING' | 'PASSED' | 'FAILED' | 'UNVERIFIED';
export type FindingSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
export type FindingStatus = 'PASS' | 'FAIL' | 'UNVERIFIED';
export type RemediationStatus = 'OPEN' | 'IN_PROGRESS' | 'RESOLVED';
export type PublicationRecordStatus = 'CERTIFIED' | 'PUBLICATION_REQUESTED' | 'PUBLISHED' | 'PUBLICATION_FAILED' | 'PUBLICATION_STATUS_UNKNOWN';

export interface HealthResponse {
  status: string;
  version: string;
  environment: string;
  timestamp: string;
}

export interface Application {
  id: number;
  application_id: string;
  name: string;
  description?: string | null;
  application_type: 'AI_AGENT' | 'WEB_APP' | 'OTHER';
  current_version: string;
  repository_url?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApplicationCreatePayload {
  application_id: string;
  name: string;
  description?: string;
  application_type?: string;
  version?: string;
  repository_url?: string;
}

export interface FindingsSummary {
  total: number;
  passed: number;
  failed: number;
  not_verified: number;
  partial: number;
}

export interface CertificationRun {
  id: number;
  certification_id: string;
  application_id: string;
  application_version: string;
  application_version_id?: number | null;
  commit_hash?: string | null;
  submission_id?: string | null;
  trigger_type?: string | null;
  policy_version?: string | null;
  status: CertificationStatus;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  findings_summary?: FindingsSummary | null;
}

export interface ApplicationLatestStatus {
  application_id: string;
  name: string;
  application_type: string;
  current_version: string;
  latest_certification?: {
    certification_id: string;
    application_version: string;
    commit_hash?: string | null;
    status: CertificationStatus;
    started_at?: string | null;
    completed_at?: string | null;
    created_at: string;
    findings_summary?: FindingsSummary | null;
  } | null;
}

export interface PublicationStatus {
  application_id: string;
  application_name: string;
  version: string;
  latest_certification_id?: string | null;
  publication_status: CertificationStatus;
  is_ready_to_publish: boolean;
  is_eligible_for_publication: boolean;
  publication_record_status?: PublicationRecordStatus | null;
  is_published: boolean;
  latest_publication_id?: string | null;
  external_publication_id?: string | null;
  evaluated_at?: string | null;
}

export interface CheckItem {
  id: number;
  certification_id: string;
  check_id: string;
  check_type: string;
  check_name: string;
  status: CheckStatus;
  source_system: string;
  started_at?: string | null;
  completed_at?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
}

export interface ChecksListResponse {
  certification_id: string;
  total_checks: number;
  checks: CheckItem[];
}

export interface FindingItem {
  id: number;
  certification_id: string;
  finding_id: string;
  finding_category: string;
  check_type: string;
  rule_id?: string | null;
  requirement_id?: string | null;
  status: FindingStatus;
  severity: FindingSeverity;
  title: string;
  description: string;
  failure_reason?: string | null;
  remediation_guidance?: string | null;
  remediation_status: RemediationStatus;
  remediation_notes?: string | null;
  created_at: string;
}

export interface FindingsListResponse {
  certification_id: string;
  total_findings: number;
  findings: FindingItem[];
}

export interface EvidenceItem {
  id: number;
  certification_id: string;
  source_system: string;
  evidence_type: string;
  evidence_hash: string;
  payload: Record<string, any>;
  verified: boolean;
  collected_at: string;
}

export interface EvidenceListResponse {
  certification_id: string;
  total_evidence: number;
  evidence: EvidenceItem[];
}

export interface RemediationActionItem {
  finding_id: string;
  category: string;
  affected_requirement: string;
  failure_reason: string;
  corrective_action: string;
  responsible_system: string;
  status: RemediationStatus;
}

export interface RemediationReport {
  certification_id: string;
  application_id: string;
  application_version: string;
  overall_status: CertificationStatus;
  total_remediation_items: number;
  unresolved_items: number;
  actions: RemediationActionItem[];
}

export interface PublicationResponse {
  publication_id: string;
  application_id: string;
  application_version: string;
  certification_id: string;
  submission_id?: string | null;
  status: PublicationRecordStatus;
  external_publication_id?: string | null;
  external_status?: string | null;
  external_confirmation?: Record<string, any> | null;
  error_code?: string | null;
  error_message?: string | null;
  requested_by: string;
  retry_count: number;
  created_at: string;
  confirmed_at?: string | null;
  is_published: boolean;
}

export interface PublicationFailureDetails {
  publication_id: string;
  application_id: string;
  version: string;
  certification_id: string;
  error_code?: string | null;
  error_message?: string | null;
  last_attempt_at: string;
  retry_permitted: boolean;
  retry_count: number;
}

export interface IntegrationItem {
  id: string;
  name: string;
  description: string;
  service_type: string;
  mcp_url: string;
  mcp_auth_token?: string | null;
  base_url: string;
  api_key?: string | null;
  is_configured: boolean;
  expected_tools: string[];
}

export interface IntegrationsResponse {
  integrations: IntegrationItem[];
  ace_mcp_server: {
    endpoint: string;
    full_url: string;
    protocol_version: string;
    auth_required: boolean;
    exposed_tools_count: number;
    description: string;
  };
}

export interface ProbeResponse {
  status: 'SUCCESS' | 'FAILED';
  mcp_url: string;
  latency_ms: number;
  tools: Array<{
    name: string;
    description?: string;
    inputSchema?: Record<string, any>;
  }>;
  error_message?: string | null;
}
