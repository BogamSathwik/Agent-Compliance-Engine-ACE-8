import React, { useEffect, useState } from 'react';
import {
  Send,
  RefreshCw,
  CheckCircle,
  XCircle,
  AlertCircle,
} from 'lucide-react';
import { api } from '../api/client';
import {
  Application,
  PublicationStatus,
  PublicationResponse,
  PublicationFailureDetails,
} from '../types/api';
import { Badge } from '../components/Badge';

interface PublicationPageProps {
  initialAppId?: string | null;
  initialVersion?: string | null;
  onNavigateToCertification: (certId: string) => void;
}

export const PublicationPage: React.FC<PublicationPageProps> = ({
  initialAppId,
  initialVersion,
  onNavigateToCertification,
}) => {
  const [applications, setApplications] = useState<Application[]>([]);
  const [selectedAppId, setSelectedAppId] = useState(initialAppId || '');
  const [selectedVersion, setSelectedVersion] = useState(initialVersion || '');

  const [loading, setLoading] = useState(false);
  const [actionInProgress, setActionInProgress] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const [pubStatus, setPubStatus] = useState<PublicationStatus | null>(null);
  const [lastPublication, setLastPublication] = useState<PublicationResponse | null>(null);
  const [failureDetails, setFailureDetails] = useState<PublicationFailureDetails | null>(null);

  // Confirmation dialog
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [publishNotes, setPublishNotes] = useState('');

  // Load application list
  useEffect(() => {
    api
      .listApplications(0, 100)
      .then((apps) => {
        setApplications(apps);
        if (!selectedAppId && apps.length > 0) {
          const first = apps[0];
          setSelectedAppId(first.application_id);
          setSelectedVersion(first.current_version);
        }
      })
      .catch(() => {});
  }, []);

  const loadStatus = async (appId: string, version?: string) => {
    if (!appId.trim()) return;
    setLoading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const statusData = await api.getApplicationPublicationStatus(
        appId.trim(),
        version?.trim() || undefined
      );
      setPubStatus(statusData);

      // If status is PUBLICATION_FAILED or there was an error, attempt to load failure details
      if (statusData.publication_record_status === 'PUBLICATION_FAILED') {
        try {
          const fails = await api.getPublicationFailures(appId.trim(), version?.trim() || undefined);
          setFailureDetails(fails);
        } catch {
          setFailureDetails(null);
        }
      } else {
        setFailureDetails(null);
      }
    } catch (err: any) {
      setError(err?.message || `Failed to fetch publication status for ${appId}`);
      setPubStatus(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedAppId) {
      loadStatus(selectedAppId, selectedVersion);
    }
  }, [selectedAppId, selectedVersion]);

  const handleAppSelectChange = (appId: string) => {
    setSelectedAppId(appId);
    const app = applications.find((a) => a.application_id === appId);
    if (app) {
      setSelectedVersion(app.current_version);
    }
  };

  const handleRequestPublication = async () => {
    if (!pubStatus?.is_ready_to_publish || actionInProgress) return;

    setActionInProgress(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const pubRes = await api.requestPublication(
        selectedAppId,
        selectedVersion || undefined,
        publishNotes.trim() || undefined
      );

      setLastPublication(pubRes);
      setShowConfirmModal(false);
      setPublishNotes('');

      if (pubRes.status === 'PUBLISHED') {
        setSuccessMsg(
          `Publication succeeded! External Publication ID: ${pubRes.external_publication_id || pubRes.publication_id}`
        );
      } else if (pubRes.status === 'PUBLICATION_REQUESTED') {
        setSuccessMsg(
          `Publication requested to AgentGen Pro. Current Status: PUBLICATION_REQUESTED (ID: ${pubRes.publication_id})`
        );
      } else if (pubRes.status === 'PUBLICATION_FAILED') {
        setError(`Publication failed: ${pubRes.error_message || pubRes.error_code}`);
      }

      await loadStatus(selectedAppId, selectedVersion);
    } catch (err: any) {
      setError(err?.message || 'Publication request was rejected by backend PolicyEngine');
    } finally {
      setActionInProgress(false);
    }
  };

  const handleVerifyStatus = async () => {
    if (!selectedAppId || actionInProgress) return;

    setActionInProgress(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const pubRes = await api.verifyPublication(selectedAppId, selectedVersion || undefined);
      setLastPublication(pubRes);
      setSuccessMsg(`Status reconciled with AgentGen Pro: ${pubRes.status}`);
      await loadStatus(selectedAppId, selectedVersion);
    } catch (err: any) {
      setError(err?.message || 'Failed to verify external publication status');
    } finally {
      setActionInProgress(false);
    }
  };

  const isEligible = pubStatus?.is_ready_to_publish && pubStatus?.is_eligible_for_publication;
  const currentRecordStatus = pubStatus?.publication_record_status;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-charcoal-900">
            AgentGen Pro Publication
          </h1>
          <p className="text-sm text-charcoal-500 mt-0.5">
            Deterministic gateway to release compliant agents to AgentGen Pro production.
          </p>
        </div>

        {/* Target App & Version selector */}
        <div className="flex items-center space-x-2">
          <select
            value={selectedAppId}
            onChange={(e) => handleAppSelectChange(e.target.value)}
            className="px-3 py-1.5 border border-borderMuted rounded text-xs text-charcoal-800 bg-white font-medium focus:outline-none focus:ring-1 focus:ring-sage-500"
          >
            {applications.map((app) => (
              <option key={app.application_id} value={app.application_id}>
                {app.name} ({app.application_id})
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Version"
            value={selectedVersion}
            onChange={(e) => setSelectedVersion(e.target.value)}
            className="w-20 px-2 py-1.5 border border-borderMuted rounded text-xs font-mono text-charcoal-800 bg-white"
          />
          <button
            onClick={() => loadStatus(selectedAppId, selectedVersion)}
            disabled={loading}
            className="p-1.5 border border-borderMuted rounded bg-white hover:bg-cream-100 text-charcoal-600 disabled:opacity-50"
            title="Refresh status"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Messages */}
      {error && (
        <div className="p-4 rounded-md bg-red-50 border border-red-200 text-red-800 flex items-start space-x-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <span className="font-semibold">Publication Error:</span> {error}
          </div>
        </div>
      )}

      {successMsg && (
        <div className="p-4 rounded-md bg-sage-50 border border-sage-200 text-sage-900 flex items-start space-x-3">
          <CheckCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div className="text-sm font-medium">{successMsg}</div>
        </div>
      )}

      {/* Status Details */}
      {pubStatus && (
        <div className="space-y-6">
          {/* Readiness Banner */}
          <div className="bg-white rounded-lg border border-borderMuted p-6 shadow-sm space-y-5">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-borderMuted pb-4">
              <div>
                <div className="flex items-center space-x-3">
                  <h2 className="text-base font-bold text-charcoal-900">
                    {pubStatus.application_name}
                  </h2>
                  <span className="text-xs font-mono text-charcoal-500">
                    v{pubStatus.version}
                  </span>
                  <Badge status={pubStatus.publication_status} />
                  {currentRecordStatus && (
                    <Badge status={currentRecordStatus} />
                  )}
                </div>
                <div className="text-xs text-charcoal-500 mt-1">
                  Target Application ID: <strong className="text-charcoal-700 font-mono">{pubStatus.application_id}</strong>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center space-x-2">
                <button
                  onClick={handleVerifyStatus}
                  disabled={actionInProgress}
                  className="px-3 py-1.5 border border-borderMuted bg-white hover:bg-cream-100 text-charcoal-700 rounded text-xs font-medium inline-flex items-center disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${actionInProgress ? 'animate-spin' : ''}`} />
                  Reconcile Status
                </button>

                <button
                  onClick={() => setShowConfirmModal(true)}
                  disabled={!isEligible || actionInProgress}
                  className={`px-4 py-1.5 rounded text-xs font-medium inline-flex items-center transition-colors ${
                    isEligible
                      ? 'bg-sage-500 hover:bg-sage-600 text-white shadow-sm'
                      : 'bg-charcoal-100 text-charcoal-400 cursor-not-allowed border border-charcoal-200'
                  }`}
                >
                  <Send className="w-3.5 h-3.5 mr-1.5" />
                  Request Publication
                </button>
              </div>
            </div>

            {/* Publication Gate Conditions Breakdown */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div className="p-4 rounded-md border border-borderMuted bg-cream-50/50 space-y-2">
                <div className="font-semibold text-charcoal-800 uppercase tracking-wider text-[11px]">
                  ACE PolicyEngine Gate
                </div>
                <div className="flex items-center space-x-2">
                  {pubStatus.is_ready_to_publish ? (
                    <CheckCircle className="w-4 h-4 text-sage-600" />
                  ) : (
                    <XCircle className="w-4 h-4 text-red-600" />
                  )}
                  <span className="font-medium text-charcoal-900">
                    Certification Status: {pubStatus.publication_status}
                  </span>
                </div>
                <p className="text-charcoal-500 text-[11px]">
                  {pubStatus.is_ready_to_publish
                    ? 'All 17 documents verified, 9 agent rules passed, and QA verified.'
                    : 'Application has not achieved READY_TO_PUBLISH status. Publication blocked.'}
                </p>
                {pubStatus.latest_certification_id && (
                  <button
                    onClick={() => onNavigateToCertification(pubStatus.latest_certification_id!)}
                    className="text-sage-700 hover:text-sage-900 font-medium inline-flex items-center text-[11px] pt-1"
                  >
                    View Certification Run ({pubStatus.latest_certification_id}) &rarr;
                  </button>
                )}
              </div>

              <div className="p-4 rounded-md border border-borderMuted bg-cream-50/50 space-y-2">
                <div className="font-semibold text-charcoal-800 uppercase tracking-wider text-[11px]">
                  AgentGen Pro Record State
                </div>
                <div className="flex items-center space-x-2">
                  <span className="font-medium text-charcoal-900">
                    Publication State: {currentRecordStatus || 'CERTIFIED (Not Submitted)'}
                  </span>
                </div>
                <div className="text-charcoal-500 text-[11px] space-y-1">
                  {pubStatus.latest_publication_id && (
                    <div>
                      ACE Publication ID: <span className="font-mono text-charcoal-800">{pubStatus.latest_publication_id}</span>
                    </div>
                  )}
                  {pubStatus.external_publication_id && (
                    <div>
                      AgentGen External ID: <span className="font-mono text-sage-800 font-semibold">{pubStatus.external_publication_id}</span>
                    </div>
                  )}
                  {pubStatus.evaluated_at && (
                    <div>
                      Evaluated: {new Date(pubStatus.evaluated_at).toLocaleString()}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Actionable Failure Details if publication failed */}
          {failureDetails && (
            <div className="bg-white rounded-lg border border-red-200 shadow-sm p-5 space-y-3">
              <div className="flex items-center space-x-2 text-red-800 font-semibold text-sm">
                <XCircle className="w-5 h-5 text-red-600" />
                <span>Publication Failure Details</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs bg-red-50/40 p-3.5 rounded border border-red-100">
                <div>
                  <span className="text-charcoal-500">Error Code:</span>
                  <div className="font-mono font-semibold text-red-900">
                    {failureDetails.error_code || 'PUBLICATION_ERROR'}
                  </div>
                </div>
                <div>
                  <span className="text-charcoal-500">Retry Count:</span>
                  <div className="font-semibold text-charcoal-800">
                    {failureDetails.retry_count} attempts
                  </div>
                </div>
                <div className="sm:col-span-2">
                  <span className="text-charcoal-500">Actionable Reason:</span>
                  <div className="text-red-800 mt-0.5">
                    {failureDetails.error_message || 'AgentGen Pro publication gateway rejected submission.'}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Active Publication Response Confirmation */}
          {lastPublication && (
            <div className="bg-white rounded-lg border border-borderMuted shadow-sm p-5 space-y-3">
              <div className="flex items-center justify-between border-b border-borderMuted pb-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-charcoal-800">
                  Last AgentGen Pro Response
                </h3>
                <Badge status={lastPublication.status} size="sm" />
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
                <div>
                  <span className="text-charcoal-400">Publication ID:</span>
                  <div className="font-mono text-charcoal-900 font-medium">
                    {lastPublication.publication_id}
                  </div>
                </div>
                <div>
                  <span className="text-charcoal-400">External ID:</span>
                  <div className="font-mono text-charcoal-900 font-medium">
                    {lastPublication.external_publication_id || 'Pending'}
                  </div>
                </div>
                <div>
                  <span className="text-charcoal-400">Confirmed At:</span>
                  <div className="text-charcoal-700">
                    {lastPublication.confirmed_at
                      ? new Date(lastPublication.confirmed_at).toLocaleString()
                      : 'Pending Confirmation'}
                  </div>
                </div>
                <div>
                  <span className="text-charcoal-400">Requested By:</span>
                  <div className="text-charcoal-700">
                    {lastPublication.requested_by}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Confirmation Modal */}
      {showConfirmModal && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-lg border border-borderMuted shadow-lg max-w-md w-full p-6 space-y-4">
            <div className="flex items-center space-x-2 text-charcoal-900 font-semibold text-base">
              <Send className="w-5 h-5 text-sage-600" />
              <span>Confirm AgentGen Pro Publication</span>
            </div>

            <p className="text-xs text-charcoal-600">
              You are requesting publication for <strong className="text-charcoal-900">{pubStatus?.application_name}</strong> (Version <span className="font-mono font-medium">{pubStatus?.version}</span>).
              The backend <span className="font-mono">PolicyEngine</span> will revalidate all 17 document requirements, 9 agent rules, and QA results before submitting to AgentGen Pro.
            </p>

            <div>
              <label className="block text-xs font-medium text-charcoal-700 mb-1">
                Release / Audit Notes (Optional)
              </label>
              <textarea
                rows={2}
                placeholder="e.g. Approved for production release by compliance auditor..."
                value={publishNotes}
                onChange={(e) => setPublishNotes(e.target.value)}
                className="w-full px-3 py-1.5 border border-borderMuted rounded text-sm text-charcoal-900 focus:outline-none focus:ring-1 focus:ring-sage-500"
              />
            </div>

            <div className="flex justify-end space-x-2 pt-2 border-t border-borderMuted">
              <button
                type="button"
                onClick={() => setShowConfirmModal(false)}
                className="px-3.5 py-1.5 border border-borderMuted text-charcoal-600 rounded text-sm hover:bg-cream-100"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleRequestPublication}
                disabled={actionInProgress}
                className="px-4 py-1.5 bg-sage-500 hover:bg-sage-600 text-white rounded text-sm font-medium disabled:opacity-50"
              >
                {actionInProgress ? 'Publishing...' : 'Confirm & Publish'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
