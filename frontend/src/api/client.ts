import {
  HealthResponse,
  Application,
  ApplicationCreatePayload,
  ApplicationLatestStatus,
  PublicationStatus,
  CertificationRun,
  ChecksListResponse,
  FindingsListResponse,
  EvidenceListResponse,
  RemediationReport,
  RemediationStatus,
  PublicationResponse,
  PublicationFailureDetails,
} from '../types/api';

const API_BASE = '/api/v1';

export class ApiError extends Error {
  code: string;
  status: number;
  details?: Record<string, any>;

  constructor(message: string, code = 'API_ERROR', status = 500, details?: Record<string, any>) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorData: any = {};
      try {
        errorData = await response.json();
      } catch {
        // Response was not JSON
      }

      const message =
        errorData?.error?.message ||
        errorData?.detail ||
        `HTTP request failed with status ${response.status}`;
      const code = errorData?.error?.code || `HTTP_${response.status}`;
      const details = errorData?.error?.details || errorData?.details;

      throw new ApiError(message, code, response.status, details);
    }

    // Handle 204 or empty response
    if (response.status === 204) {
      return {} as T;
    }

    return (await response.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) {
      throw err;
    }
    throw new ApiError(
      (err as Error).message || 'Unable to connect to ACE backend service',
      'SERVICE_UNAVAILABLE',
      0
    );
  }
}

export const api = {
  // Health
  checkHealth: () => request<HealthResponse>('/health'),

  // Applications
  listApplications: (skip = 0, limit = 50) =>
    request<Application[]>(`/applications?skip=${skip}&limit=${limit}`),

  getApplication: (applicationId: string) =>
    request<Application>(`/applications/${encodeURIComponent(applicationId)}`),

  createApplication: (payload: ApplicationCreatePayload) =>
    request<Application>('/applications', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getApplicationStatus: (applicationId: string) =>
    request<ApplicationLatestStatus>(
      `/applications/${encodeURIComponent(applicationId)}/status`
    ),

  getApplicationPublicationStatus: (applicationId: string, version?: string) => {
    const query = version ? `?version=${encodeURIComponent(version)}` : '';
    return request<PublicationStatus>(
      `/applications/${encodeURIComponent(applicationId)}/publication-status${query}`
    );
  },

  getApplicationCertificationRuns: (applicationId: string, skip = 0, limit = 50) =>
    request<CertificationRun[]>(
      `/applications/${encodeURIComponent(applicationId)}/certification-runs?skip=${skip}&limit=${limit}`
    ),

  recertifyApplication: (applicationId: string, version?: string) => {
    const query = version ? `?version=${encodeURIComponent(version)}` : '';
    return request<any>(
      `/applications/${encodeURIComponent(applicationId)}/re-certify${query}`,
      { method: 'POST' }
    );
  },

  // Certifications
  listCertifications: (applicationId?: string, status?: string, skip = 0, limit = 50) => {
    const params = new URLSearchParams();
    if (applicationId) params.append('application_id', applicationId);
    if (status) params.append('status', status);
    params.append('skip', String(skip));
    params.append('limit', String(limit));
    return request<CertificationRun[]>(`/certifications?${params.toString()}`);
  },

  getCertification: (certificationId: string) =>
    request<CertificationRun>(`/certifications/${encodeURIComponent(certificationId)}`),

  startCertification: (payload: { application_id: string; version?: string }) =>
    request<any>('/certifications', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getCertificationChecks: (certificationId: string) =>
    request<ChecksListResponse>(
      `/certifications/${encodeURIComponent(certificationId)}/checks`
    ),

  getCertificationFindings: (certificationId: string) =>
    request<FindingsListResponse>(
      `/certifications/${encodeURIComponent(certificationId)}/findings`
    ),

  getCertificationEvidence: (certificationId: string) =>
    request<EvidenceListResponse>(
      `/certifications/${encodeURIComponent(certificationId)}/evidence`
    ),

  getCertificationRemediation: (certificationId: string) =>
    request<RemediationReport>(
      `/certifications/${encodeURIComponent(certificationId)}/remediation`
    ),

  updateRemediationStatus: (
    certificationId: string,
    findingId: string,
    status: RemediationStatus,
    notes?: string
  ) =>
    request<any>(
      `/certifications/${encodeURIComponent(certificationId)}/remediation`,
      {
        method: 'PATCH',
        body: JSON.stringify({
          finding_id: findingId,
          status,
          notes,
        }),
      }
    ),

  recertifyRun: (certificationId: string) =>
    request<any>(
      `/certifications/${encodeURIComponent(certificationId)}/re-certify`,
      { method: 'POST' }
    ),

  // Publication
  requestPublication: (applicationId: string, version?: string, notes?: string) =>
    request<PublicationResponse>(
      `/applications/${encodeURIComponent(applicationId)}/publish`,
      {
        method: 'POST',
        body: JSON.stringify({ version, notes }),
      }
    ),

  getPublicationFailures: (applicationId: string, version?: string) => {
    const query = version ? `?version=${encodeURIComponent(version)}` : '';
    return request<PublicationFailureDetails>(
      `/applications/${encodeURIComponent(applicationId)}/publication-failures${query}`
    );
  },

  verifyPublication: (applicationId: string, version?: string) => {
    const query = version ? `?version=${encodeURIComponent(version)}` : '';
    return request<PublicationResponse>(
      `/applications/${encodeURIComponent(applicationId)}/verify-publication${query}`,
      { method: 'POST' }
    );
  },

  // Integrations & MCP Configuration
  getIntegrations: () =>
    request<import('../types/api').IntegrationsResponse>('/integrations'),

  updateIntegration: (
    integrationId: string,
    data: {
      mcp_url?: string;
      mcp_auth_token?: string;
      base_url?: string;
      api_key?: string;
    }
  ) =>
    request<{ status: string; message: string }>(
      `/integrations/${encodeURIComponent(integrationId)}`,
      {
        method: 'PUT',
        body: JSON.stringify(data),
      }
    ),

  probeMcpEndpoint: (mcpUrl: string, authToken?: string) =>
    request<import('../types/api').ProbeResponse>('/integrations/probe', {
      method: 'POST',
      body: JSON.stringify({ mcp_url: mcpUrl, auth_token: authToken }),
    }),
};

