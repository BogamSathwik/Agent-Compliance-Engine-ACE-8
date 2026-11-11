import React, { useEffect, useState } from 'react';
import {
  RefreshCw,
  CheckCircle,
  ShieldAlert,
  AlertCircle,
  Info,
} from 'lucide-react';
import { api } from '../api/client';
import {
  CertificationRun,
  RemediationReport,
  RemediationStatus,
  FindingItem,
} from '../types/api';
import { Badge } from '../components/Badge';

interface RemediationPageProps {
  initialCertificationId?: string | null;
  onSelectCertification: (certId: string) => void;
}

export const RemediationPage: React.FC<RemediationPageProps> = ({
  initialCertificationId,
  onSelectCertification,
}) => {
  const [certIdInput, setCertIdInput] = useState(initialCertificationId || '');
  const [activeCertId, setActiveCertId] = useState<string | null>(initialCertificationId || null);

  const [loading, setLoading] = useState(false);
  const [actionInProgress, setActionInProgress] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const [report, setReport] = useState<RemediationReport | null>(null);
  const [rawFindings, setRawFindings] = useState<FindingItem[]>([]);
  const [recentCerts, setRecentCerts] = useState<CertificationRun[]>([]);

  // Update modal / inline edit state
  const [editingFinding, setEditingFinding] = useState<FindingItem | null>(null);
  const [newStatus, setNewStatus] = useState<RemediationStatus>('IN_PROGRESS');
  const [notes, setNotes] = useState('');

  useEffect(() => {
    // Load recent runs for switcher
    api.listCertifications(undefined, undefined, 0, 20).then(setRecentCerts).catch(() => {});
  }, []);

  const loadRemediation = async (certId: string) => {
    if (!certId.trim()) return;
    setLoading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const [remReport, findingsRes] = await Promise.all([
        api.getCertificationRemediation(certId.trim()),
        api.getCertificationFindings(certId.trim()),
      ]);

      setReport(remReport);
      setRawFindings(findingsRes.findings || []);
      setActiveCertId(certId.trim());
      setCertIdInput(certId.trim());
    } catch (err: any) {
      setError(err?.message || `Failed to load remediation for ${certId}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (initialCertificationId) {
      loadRemediation(initialCertificationId);
    }
  }, [initialCertificationId]);

  const handleUpdateStatus = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingFinding || !activeCertId || actionInProgress) return;

    setActionInProgress(true);
    setError(null);
    setSuccessMsg(null);
    try {
      await api.updateRemediationStatus(
        activeCertId,
        editingFinding.finding_id,
        newStatus,
        notes.trim() || undefined
      );

      setSuccessMsg(
        `Remediation status for "${editingFinding.title}" updated to ${newStatus}.`
      );
      setEditingFinding(null);
      setNotes('');
      // Reload report
      await loadRemediation(activeCertId);
    } catch (err: any) {
      setError(err?.message || 'Failed to update remediation status');
    } finally {
      setActionInProgress(false);
    }
  };

  const handleTriggerRecertification = async () => {
    if (!activeCertId || actionInProgress) return;

    setActionInProgress(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await api.recertifyRun(activeCertId);
      setSuccessMsg(
        `Re-certification run ${res.certification_id} initiated. It will re-verify all 17 documents, 9 rules, and QA.`
      );
      // Wait briefly then select new run
      setTimeout(() => {
        onSelectCertification(res.certification_id);
      }, 1200);
    } catch (err: any) {
      setError(err?.message || 'Failed to trigger re-certification run');
    } finally {
      setActionInProgress(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header and Run Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-charcoal-900">
            Compliance Remediation
          </h1>
          <p className="text-sm text-charcoal-500 mt-0.5">
            Resolve failed compliance requirements and trigger re-certification.
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <input
            type="text"
            placeholder="Certification ID..."
            value={certIdInput}
            onChange={(e) => setCertIdInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && loadRemediation(certIdInput)}
            className="w-56 px-3 py-1.5 border border-borderMuted rounded text-xs font-mono text-charcoal-900 bg-white focus:outline-none focus:ring-1 focus:ring-sage-500"
          />
          <button
            onClick={() => loadRemediation(certIdInput)}
            disabled={loading || !certIdInput.trim()}
            className="px-3 py-1.5 bg-sage-500 hover:bg-sage-600 text-white rounded text-xs font-medium disabled:opacity-50"
          >
            Load
          </button>
          {recentCerts.length > 0 && (
            <select
              value={activeCertId || ''}
              onChange={(e) => loadRemediation(e.target.value)}
              className="px-2 py-1.5 border border-borderMuted rounded text-xs text-charcoal-700 bg-white"
            >
              <option value="">Recent Runs...</option>
              {recentCerts.map((r) => (
                <option key={r.certification_id} value={r.certification_id}>
                  {r.certification_id} ({r.application_id})
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Critical Legal/Compliance Notice */}
      <div className="p-4 rounded-lg bg-cream-100 border border-borderMuted flex items-start space-x-3 text-xs text-charcoal-700">
        <Info className="w-4 h-4 text-sage-600 flex-shrink-0 mt-0.5" />
        <div className="space-y-1">
          <div className="font-semibold text-charcoal-900">
            Important Compliance Notice
          </div>
          <div>
            Marking a remediation item as <span className="font-semibold">RESOLVED</span> records an operator note in the audit trail, but <span className="font-semibold text-charcoal-900">does not establish compliance</span>.
            The backend <span className="font-mono text-charcoal-800">PolicyEngine</span> remains the sole authority for publication eligibility. An explicit <span className="font-semibold text-sage-800">Re-certification Run</span> must execute and authoritatively verify all requirements before publication is permitted.
          </div>
        </div>
      </div>

      {/* Messages */}
      {error && (
        <div className="p-4 rounded-md bg-red-50 border border-red-200 text-red-800 flex items-start space-x-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <span className="font-semibold">Error:</span> {error}
          </div>
        </div>
      )}

      {successMsg && (
        <div className="p-4 rounded-md bg-sage-50 border border-sage-200 text-sage-900 flex items-start space-x-3">
          <CheckCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div className="text-sm font-medium">{successMsg}</div>
        </div>
      )}

      {/* Empty State */}
      {!report && !loading && (
        <div className="bg-white rounded-lg border border-borderMuted p-12 text-center space-y-3">
          <div className="w-12 h-12 rounded-full bg-cream-100 text-charcoal-500 flex items-center justify-center mx-auto">
            <ShieldAlert className="w-6 h-6" />
          </div>
          <h3 className="text-base font-semibold text-charcoal-800">
            No Remediation Plan Loaded
          </h3>
          <p className="text-sm text-charcoal-500 max-w-md mx-auto">
            Enter a Certification ID or choose from recent runs above to view outstanding findings and record remediation actions.
          </p>
        </div>
      )}

      {/* Report Loaded */}
      {report && (
        <div className="space-y-6">
          {/* Remediation Summary Card */}
          <div className="bg-white rounded-lg border border-borderMuted p-5 shadow-sm space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-borderMuted pb-4">
              <div>
                <div className="flex items-center space-x-3">
                  <h2 className="text-lg font-mono font-bold text-charcoal-900">
                    {report.certification_id}
                  </h2>
                  <Badge status={report.overall_status} />
                </div>
                <div className="text-xs text-charcoal-500 mt-1 flex space-x-4">
                  <span>
                    Application: <strong className="text-charcoal-800">{report.application_id}</strong>
                  </span>
                  <span>
                    Version: <strong className="font-mono text-charcoal-800">v{report.application_version}</strong>
                  </span>
                </div>
              </div>

              {/* Re-certify Action Button */}
              <button
                onClick={handleTriggerRecertification}
                disabled={actionInProgress}
                className="inline-flex items-center px-4 py-2 bg-sage-500 hover:bg-sage-600 text-white rounded text-sm font-medium shadow-sm transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 mr-2 ${actionInProgress ? 'animate-spin' : ''}`} />
                Trigger Re-certification
              </button>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-xs">
              <div>
                <span className="text-charcoal-400 block mb-0.5">Total Findings</span>
                <div className="text-2xl font-semibold text-charcoal-900">
                  {report.total_remediation_items}
                </div>
              </div>
              <div>
                <span className="text-charcoal-400 block mb-0.5">Unresolved Items</span>
                <div className={`text-2xl font-semibold ${report.unresolved_items > 0 ? 'text-red-700' : 'text-sage-800'}`}>
                  {report.unresolved_items}
                </div>
              </div>
              <div>
                <span className="text-charcoal-400 block mb-0.5">Resolved Notes</span>
                <div className="text-2xl font-semibold text-sage-800">
                  {report.total_remediation_items - report.unresolved_items}
                </div>
              </div>
            </div>
          </div>

          {/* Remediation Action Items List */}
          <div className="bg-white rounded-lg border border-borderMuted shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-borderMuted flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-charcoal-800">
                  Corrective Action Items ({rawFindings.length})
                </h3>
                <p className="text-[11px] text-charcoal-500 mt-0.5">
                  Specific remediation steps required to fulfill policy checks.
                </p>
              </div>
            </div>

            {rawFindings.length === 0 ? (
              <div className="p-8 text-center text-xs text-sage-800 bg-sage-50/20">
                <CheckCircle className="w-6 h-6 text-sage-600 mx-auto mb-1.5" />
                All requirements verified compliant. No remediation actions required.
              </div>
            ) : (
              <div className="divide-y divide-borderMuted">
                {rawFindings.map((finding) => {
                  return (
                    <div key={finding.id} className="p-5 hover:bg-cream-50/50 transition-colors">
                      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                        <div className="space-y-2 max-w-3xl">
                          <div className="flex items-center space-x-2">
                            <span className="font-semibold text-sm text-charcoal-900">
                              {finding.title}
                            </span>
                            <Badge status={finding.severity} size="sm" />
                            <Badge status={finding.remediation_status} size="sm" />
                          </div>

                          <div className="text-xs text-charcoal-500 font-mono">
                            Check: {finding.check_type} | Category: {finding.finding_category} | ID: {finding.finding_id}
                          </div>

                          {finding.failure_reason && (
                            <div className="text-xs text-red-800 bg-red-50/60 p-2.5 rounded border border-red-200">
                              <span className="font-semibold block mb-0.5">Failure Reason:</span>
                              {finding.failure_reason}
                            </div>
                          )}

                          {finding.remediation_guidance && (
                            <div className="text-xs text-sage-900 bg-sage-50/50 p-2.5 rounded border border-sage-200">
                              <span className="font-semibold block mb-0.5">Corrective Action:</span>
                              {finding.remediation_guidance}
                            </div>
                          )}

                          {finding.remediation_notes && (
                            <div className="text-xs text-charcoal-600 bg-cream-100 p-2 rounded">
                              <span className="font-medium text-charcoal-800">Operator Note:</span> {finding.remediation_notes}
                            </div>
                          )}
                        </div>

                        {/* Action buttons */}
                        <div className="flex-shrink-0">
                          <button
                            onClick={() => {
                              setEditingFinding(finding);
                              setNewStatus(finding.remediation_status);
                              setNotes(finding.remediation_notes || '');
                            }}
                            className="px-3 py-1.5 border border-borderMuted bg-white hover:bg-cream-100 text-charcoal-700 rounded text-xs font-medium"
                          >
                            Update Status
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Update Remediation Status Modal */}
      {editingFinding && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-lg border border-borderMuted shadow-lg max-w-md w-full p-6 space-y-4">
            <h3 className="text-base font-semibold text-charcoal-900">
              Update Remediation Status
            </h3>
            <p className="text-xs text-charcoal-500">
              Update operator lifecycle status for: <strong className="text-charcoal-800">{editingFinding.title}</strong>
            </p>

            <form onSubmit={handleUpdateStatus} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-charcoal-700 mb-1">
                  Lifecycle Status
                </label>
                <select
                  value={newStatus}
                  onChange={(e) => setNewStatus(e.target.value as RemediationStatus)}
                  className="w-full px-3 py-1.5 border border-borderMuted rounded text-sm text-charcoal-900 bg-white focus:outline-none focus:ring-1 focus:ring-sage-500"
                >
                  <option value="OPEN">OPEN (Pending investigation)</option>
                  <option value="IN_PROGRESS">IN_PROGRESS (Fix underway)</option>
                  <option value="RESOLVED">RESOLVED (Corrective action completed)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-charcoal-700 mb-1">
                  Remediation / Audit Notes
                </label>
                <textarea
                  rows={3}
                  placeholder="Document the corrective actions taken, commit hash, or uploaded document reference..."
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="w-full px-3 py-1.5 border border-borderMuted rounded text-sm text-charcoal-900 focus:outline-none focus:ring-1 focus:ring-sage-500"
                />
              </div>

              <div className="text-[11px] text-charcoal-500 bg-cream-100 p-2.5 rounded">
                Note: Setting to RESOLVED records operator intent in the database. Only an authoritative re-certification run can verify compliance.
              </div>

              <div className="flex justify-end space-x-2 pt-2 border-t border-borderMuted">
                <button
                  type="button"
                  onClick={() => setEditingFinding(null)}
                  className="px-3.5 py-1.5 border border-borderMuted text-charcoal-600 rounded text-sm hover:bg-cream-100"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionInProgress}
                  className="px-4 py-1.5 bg-sage-500 hover:bg-sage-600 text-white rounded text-sm font-medium disabled:opacity-50"
                >
                  {actionInProgress ? 'Saving...' : 'Save Update'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
