import React, { useEffect, useState } from 'react';
import {
  FileCheck,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Database,
  ArrowRight,
  Key,
  AlertCircle,
  Hash,
} from 'lucide-react';
import { api } from '../api/client';
import {
  CertificationRun,
  CheckItem,
  FindingItem,
  EvidenceItem,
} from '../types/api';
import { Badge } from '../components/Badge';

interface CertificationDetailsPageProps {
  initialCertificationId?: string | null;
  onNavigateToRemediation: (certId: string) => void;
  onNavigateToPublication: (appId: string, version: string) => void;
}

export const CertificationDetailsPage: React.FC<CertificationDetailsPageProps> = ({
  initialCertificationId,
  onNavigateToRemediation,
  onNavigateToPublication,
}) => {
  const [certIdInput, setCertIdInput] = useState(initialCertificationId || '');
  const [activeCertId, setActiveCertId] = useState<string | null>(initialCertificationId || null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [run, setRun] = useState<CertificationRun | null>(null);
  const [checks, setChecks] = useState<CheckItem[]>([]);
  const [findings, setFindings] = useState<FindingItem[]>([]);
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);

  // Active view tab inside Details: 'all' | 'documents' | 'rules' | 'qa' | 'evidence' | 'findings'
  const [subTab, setSubTab] = useState<'all' | 'documents' | 'rules' | 'qa' | 'evidence' | 'findings'>('all');

  // Search/select from recent certifications list
  const [recentCerts, setRecentCerts] = useState<CertificationRun[]>([]);

  useEffect(() => {
    // Fetch recent runs for quick switching
    api.listCertifications(undefined, undefined, 0, 20).then(setRecentCerts).catch(() => {});
  }, []);

  const loadCertificationDetails = async (idToLoad: string) => {
    if (!idToLoad.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const [runData, checksData, findingsData, evidenceData] = await Promise.all([
        api.getCertification(idToLoad.trim()),
        api.getCertificationChecks(idToLoad.trim()),
        api.getCertificationFindings(idToLoad.trim()),
        api.getCertificationEvidence(idToLoad.trim()),
      ]);

      setRun(runData);
      setChecks(checksData.checks || []);
      setFindings(findingsData.findings || []);
      setEvidenceList(evidenceData.evidence || []);
      setActiveCertId(idToLoad.trim());
      setCertIdInput(idToLoad.trim());
    } catch (err: any) {
      setError(err?.message || `Failed to load certification run ${idToLoad}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (initialCertificationId) {
      loadCertificationDetails(initialCertificationId);
    }
  }, [initialCertificationId]);

  // Group checks
  const documentChecks = checks.filter(
    (c) =>
      c.check_type === 'DOCUMENT_RAG' ||
      c.check_type === 'DOCUMENT_VERIFICATION' ||
      c.check_name.toLowerCase().includes('document') ||
      c.check_id.startsWith('DOC-')
  );

  const ruleChecks = checks.filter(
    (c) =>
      c.check_type === 'AGENT_RULE' ||
      c.check_type === 'RULE_EVALUATION' ||
      c.check_id.startsWith('RULE-') ||
      c.check_name.toLowerCase().includes('rule')
  );

  const qaChecks = checks.filter(
    (c) =>
      c.check_type === 'MYBLOCKS_QA' ||
      c.check_type === 'QA_TEST_SUITE' ||
      c.check_id.startsWith('QA-') ||
      c.check_name.toLowerCase().includes('qa')
  );

  // Status breakdown
  const passedChecksCount = checks.filter((c) => c.status === 'PASSED').length;
  const failedChecksCount = checks.filter((c) => c.status === 'FAILED').length;
  const unverifiedChecksCount = checks.filter(
    (c) => c.status === 'UNVERIFIED' || c.status === 'PENDING'
  ).length;

  return (
    <div className="space-y-6">
      {/* Header and Run Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-charcoal-900">
            Certification Details
          </h1>
          <p className="text-sm text-charcoal-500 mt-0.5">
            Granular breakdown of 17 document requirements, 9 agent rules, QA results, and verifiable evidence.
          </p>
        </div>

        {/* Input & selector for run ID */}
        <div className="flex items-center space-x-2">
          <div className="relative">
            <input
              type="text"
              placeholder="Enter Certification ID..."
              value={certIdInput}
              onChange={(e) => setCertIdInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && loadCertificationDetails(certIdInput)}
              className="w-56 px-3 py-1.5 border border-borderMuted rounded text-xs font-mono text-charcoal-900 focus:outline-none focus:ring-1 focus:ring-sage-500 bg-white"
            />
          </div>
          <button
            onClick={() => loadCertificationDetails(certIdInput)}
            disabled={loading || !certIdInput.trim()}
            className="px-3 py-1.5 bg-sage-500 hover:bg-sage-600 text-white rounded text-xs font-medium disabled:opacity-50"
          >
            Load
          </button>
          {recentCerts.length > 0 && (
            <select
              value={activeCertId || ''}
              onChange={(e) => loadCertificationDetails(e.target.value)}
              className="px-2 py-1.5 border border-borderMuted rounded text-xs text-charcoal-700 bg-white focus:outline-none"
            >
              <option value="">Recent Runs...</option>
              {recentCerts.map((r) => (
                <option key={r.certification_id} value={r.certification_id}>
                  {r.certification_id} ({r.application_id} - {r.status})
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="p-4 rounded-md bg-red-50 border border-red-200 text-red-800 flex items-start space-x-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <span className="font-semibold">Backend Error:</span> {error}
          </div>
        </div>
      )}

      {/* If No Certification Loaded */}
      {!run && !loading && (
        <div className="bg-white rounded-lg border border-borderMuted p-12 text-center space-y-3">
          <div className="w-12 h-12 rounded-full bg-cream-100 text-charcoal-500 flex items-center justify-center mx-auto">
            <FileCheck className="w-6 h-6" />
          </div>
          <h3 className="text-base font-semibold text-charcoal-800">
            No Certification Run Loaded
          </h3>
          <p className="text-sm text-charcoal-500 max-w-md mx-auto">
            Please enter a Certification ID above or choose from recent runs to inspect document checks, agent rules, and evidence.
          </p>
        </div>
      )}

      {/* Loaded Certification Run Content */}
      {run && (
        <div className="space-y-6">
          {/* Top Status Banner */}
          <div className="bg-white rounded-lg border border-borderMuted p-5 shadow-sm space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-borderMuted pb-4">
              <div>
                <div className="flex items-center space-x-3">
                  <h2 className="text-lg font-mono font-bold text-charcoal-900">
                    {run.certification_id}
                  </h2>
                  <Badge status={run.status} />
                </div>
                <div className="text-xs text-charcoal-500 mt-1 flex flex-wrap gap-x-4 gap-y-1">
                  <span>
                    Application: <strong className="text-charcoal-800 font-medium">{run.application_id}</strong>
                  </span>
                  <span>
                    Version: <strong className="text-charcoal-800 font-mono">v{run.application_version}</strong>
                  </span>
                  {run.commit_hash && (
                    <span>
                      Commit: <strong className="font-mono text-charcoal-700">{run.commit_hash.substring(0, 8)}</strong>
                    </span>
                  )}
                  <span>
                    Policy: <strong className="text-charcoal-700">{run.policy_version || 'v1.0'}</strong>
                  </span>
                </div>
              </div>

              {/* Quick Action Buttons */}
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => onNavigateToRemediation(run.certification_id)}
                  className="px-3 py-1.5 border border-borderMuted bg-white hover:bg-cream-100 text-charcoal-700 rounded text-xs font-medium"
                >
                  View Remediation ({findings.length})
                </button>
                {run.status === 'READY_TO_PUBLISH' && (
                  <button
                    onClick={() => onNavigateToPublication(run.application_id, run.application_version)}
                    className="px-3 py-1.5 bg-sage-500 hover:bg-sage-600 text-white rounded text-xs font-medium inline-flex items-center"
                  >
                    Proceed to Publication <ArrowRight className="w-3.5 h-3.5 ml-1" />
                  </button>
                )}
              </div>
            </div>

            {/* Run Timestamps & Summary Counters */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
              <div>
                <span className="text-charcoal-400 block mb-0.5">Execution Timestamps</span>
                <div className="text-charcoal-700">
                  Started: {run.started_at ? new Date(run.started_at).toLocaleTimeString() : 'Queued'}
                </div>
                <div className="text-charcoal-700">
                  Completed: {run.completed_at ? new Date(run.completed_at).toLocaleTimeString() : 'In Progress'}
                </div>
              </div>

              <div>
                <span className="text-charcoal-400 block mb-0.5">Verification Checks</span>
                <div className="font-semibold text-charcoal-800">
                  {passedChecksCount} Passed / {failedChecksCount} Failed / {unverifiedChecksCount} Pending
                </div>
                <div className="text-charcoal-400">Total: {checks.length} checks</div>
              </div>

              <div>
                <span className="text-charcoal-400 block mb-0.5">Outstanding Findings</span>
                <div className={`font-semibold ${findings.length > 0 ? 'text-red-700' : 'text-sage-800'}`}>
                  {findings.length} findings recorded
                </div>
                <div className="text-charcoal-400">
                  {findings.filter((f) => f.remediation_status === 'RESOLVED').length} marked resolved
                </div>
              </div>

              <div>
                <span className="text-charcoal-400 block mb-0.5">Evidence Collected</span>
                <div className="font-semibold text-charcoal-800">
                  {evidenceList.length} cryptographic hashes
                </div>
                <div className="text-charcoal-400">SHA-256 provenance</div>
              </div>
            </div>
          </div>

          {/* Sub Navigation Tabs */}
          <div className="border-b border-borderMuted flex space-x-4 text-xs font-medium">
            {[
              { id: 'all', label: `All Checks (${checks.length})` },
              { id: 'documents', label: `17 Documents (${documentChecks.length})` },
              { id: 'rules', label: `9 Agent Rules (${ruleChecks.length})` },
              { id: 'qa', label: `QA Suite (${qaChecks.length})` },
              { id: 'evidence', label: `Evidence (${evidenceList.length})` },
              { id: 'findings', label: `Findings (${findings.length})` },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setSubTab(tab.id as any)}
                className={`pb-2.5 transition-colors border-b-2 -mb-px ${
                  subTab === tab.id
                    ? 'border-sage-600 text-sage-900 font-semibold'
                    : 'border-transparent text-charcoal-500 hover:text-charcoal-800'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Section: 17 Document Requirements */}
          {(subTab === 'all' || subTab === 'documents') && (
            <div className="bg-white rounded-lg border border-borderMuted shadow-sm overflow-hidden">
              <div className="px-5 py-3.5 bg-cream-100 border-b border-borderMuted flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-charcoal-800 flex items-center">
                    <FileCheck className="w-4 h-4 mr-1.5 text-sage-600" />
                    17 Authoritative Document Requirements (MyBlocks RAG)
                  </h3>
                  <p className="text-[11px] text-charcoal-500 mt-0.5">
                    Deterministic verification of all 17 mandatory architectural and compliance document categories.
                  </p>
                </div>
              </div>

              {documentChecks.length === 0 ? (
                <div className="p-6 text-center text-xs text-charcoal-500">
                  No individual document checks executed or logged yet.
                </div>
              ) : (
                <div className="divide-y divide-borderMuted">
                  {documentChecks.map((chk) => (
                    <div key={chk.id} className="p-4 hover:bg-cream-50/60 transition-colors">
                      <div className="flex items-start justify-between">
                        <div className="space-y-1">
                          <div className="flex items-center space-x-2">
                            {chk.status === 'PASSED' ? (
                              <CheckCircle2 className="w-4 h-4 text-sage-600" />
                            ) : chk.status === 'FAILED' ? (
                              <XCircle className="w-4 h-4 text-red-600" />
                            ) : (
                              <HelpCircle className="w-4 h-4 text-charcoal-400" />
                            )}
                            <span className="font-semibold text-xs text-charcoal-900">
                              {chk.check_name}
                            </span>
                            <span className="font-mono text-[10px] text-charcoal-400">
                              [{chk.check_id}]
                            </span>
                          </div>

                          {chk.error_message && (
                            <p className="text-xs text-red-700 pl-6">
                              <strong className="font-medium">Failure Reason:</strong> {chk.error_message}
                            </p>
                          )}
                        </div>

                        <div className="text-right flex items-center space-x-3">
                          <Badge status={chk.status} size="sm" />
                          <span className="text-[11px] text-charcoal-400">
                            {chk.completed_at ? new Date(chk.completed_at).toLocaleTimeString() : '—'}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Section: 9 Agent Rules */}
          {(subTab === 'all' || subTab === 'rules') && (
            <div className="bg-white rounded-lg border border-borderMuted shadow-sm overflow-hidden">
              <div className="px-5 py-3.5 bg-cream-100 border-b border-borderMuted">
                <h3 className="text-xs font-bold uppercase tracking-wider text-charcoal-800 flex items-center">
                  <ShieldCheck className="w-4 h-4 mr-1.5 text-sage-600" />
                  9 Mandatory Agent Governance Rules
                </h3>
                <p className="text-[11px] text-charcoal-500 mt-0.5">
                  Autonomous policy checks including prompt-injection defense, tool boundary controls, and safety guardrails.
                </p>
              </div>

              {ruleChecks.length === 0 ? (
                <div className="p-6 text-center text-xs text-charcoal-500">
                  No rule checks logged for this run.
                </div>
              ) : (
                <div className="divide-y divide-borderMuted">
                  {ruleChecks.map((chk) => (
                    <div key={chk.id} className="p-4 hover:bg-cream-50/60 transition-colors">
                      <div className="flex items-start justify-between">
                        <div className="space-y-1">
                          <div className="flex items-center space-x-2">
                            {chk.status === 'PASSED' ? (
                              <CheckCircle2 className="w-4 h-4 text-sage-600" />
                            ) : chk.status === 'FAILED' ? (
                              <XCircle className="w-4 h-4 text-red-600" />
                            ) : (
                              <HelpCircle className="w-4 h-4 text-charcoal-400" />
                            )}
                            <span className="font-semibold text-xs text-charcoal-900">
                              {chk.check_name}
                            </span>
                            <span className="font-mono text-[10px] text-charcoal-400">
                              [{chk.check_id}]
                            </span>
                          </div>

                          {chk.error_message && (
                            <p className="text-xs text-red-700 pl-6">
                              <strong className="font-medium">Failure Reason:</strong> {chk.error_message}
                            </p>
                          )}
                        </div>

                        <div className="text-right flex items-center space-x-3">
                          <Badge status={chk.status} size="sm" />
                          <span className="text-[11px] text-charcoal-400">
                            {chk.completed_at ? new Date(chk.completed_at).toLocaleTimeString() : '—'}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Section: QA Test Suite */}
          {(subTab === 'all' || subTab === 'qa') && (
            <div className="bg-white rounded-lg border border-borderMuted shadow-sm overflow-hidden">
              <div className="px-5 py-3.5 bg-cream-100 border-b border-borderMuted">
                <h3 className="text-xs font-bold uppercase tracking-wider text-charcoal-800 flex items-center">
                  <Database className="w-4 h-4 mr-1.5 text-sage-600" />
                  MyBlocks Authoritative QA Test Suite
                </h3>
                <p className="text-[11px] text-charcoal-500 mt-0.5">
                  End-to-end integration and functionality test suite verification.
                </p>
              </div>

              {qaChecks.length === 0 ? (
                <div className="p-6 text-center text-xs text-charcoal-500">
                  No QA checks recorded.
                </div>
              ) : (
                <div className="divide-y divide-borderMuted">
                  {qaChecks.map((chk) => (
                    <div key={chk.id} className="p-4 hover:bg-cream-50/60 transition-colors">
                      <div className="flex items-start justify-between">
                        <div className="space-y-1">
                          <div className="flex items-center space-x-2">
                            {chk.status === 'PASSED' ? (
                              <CheckCircle2 className="w-4 h-4 text-sage-600" />
                            ) : chk.status === 'FAILED' ? (
                              <XCircle className="w-4 h-4 text-red-600" />
                            ) : (
                              <HelpCircle className="w-4 h-4 text-charcoal-400" />
                            )}
                            <span className="font-semibold text-xs text-charcoal-900">
                              {chk.check_name}
                            </span>
                            <span className="font-mono text-[10px] text-charcoal-400">
                              [{chk.check_id}]
                            </span>
                          </div>
                          {chk.error_message && (
                            <p className="text-xs text-red-700 pl-6">
                              {chk.error_message}
                            </p>
                          )}
                        </div>
                        <div className="text-right flex items-center space-x-3">
                          <Badge status={chk.status} size="sm" />
                          <span className="text-[11px] text-charcoal-400">
                            {chk.completed_at ? new Date(chk.completed_at).toLocaleTimeString() : '—'}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Section: Evidence Provenance */}
          {(subTab === 'all' || subTab === 'evidence') && (
            <div className="bg-white rounded-lg border border-borderMuted shadow-sm overflow-hidden">
              <div className="px-5 py-3.5 bg-cream-100 border-b border-borderMuted flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-charcoal-800 flex items-center">
                    <Key className="w-4 h-4 mr-1.5 text-sage-600" />
                    Cryptographic Evidence Provenance
                  </h3>
                  <p className="text-[11px] text-charcoal-500 mt-0.5">
                    Immutable SHA-256 hashes verifying input documents, QA runs, and rule evaluations.
                  </p>
                </div>
                <span className="text-xs text-charcoal-500">
                  {evidenceList.length} evidence records
                </span>
              </div>

              {evidenceList.length === 0 ? (
                <div className="p-6 text-center text-xs text-charcoal-500">
                  No evidence records collected for this run.
                </div>
              ) : (
                <div className="divide-y divide-borderMuted max-h-96 overflow-y-auto">
                  {evidenceList.map((ev) => (
                    <div key={ev.id} className="p-4 hover:bg-cream-50/60 transition-colors">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                        <div>
                          <div className="flex items-center space-x-2 text-xs">
                            <span className="font-semibold text-charcoal-900">
                              {ev.source_system}
                            </span>
                            <span className="text-charcoal-400">•</span>
                            <span className="text-charcoal-600">{ev.evidence_type}</span>
                          </div>
                          <div className="flex items-center space-x-1.5 font-mono text-[11px] text-charcoal-500 mt-1">
                            <Hash className="w-3.5 h-3.5 text-charcoal-400" />
                            <span className="break-all">{ev.evidence_hash}</span>
                          </div>
                        </div>
                        <div className="text-right sm:text-right whitespace-nowrap">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 text-[11px] rounded font-medium ${
                              ev.verified
                                ? 'bg-sage-50 text-sage-800 border border-sage-200'
                                : 'bg-red-50 text-red-700 border border-red-200'
                            }`}
                          >
                            {ev.verified ? 'Verified Hash' : 'Unverified'}
                          </span>
                          <div className="text-[10px] text-charcoal-400 mt-0.5">
                            {new Date(ev.collected_at).toLocaleTimeString()}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Section: Findings */}
          {(subTab === 'all' || subTab === 'findings') && (
            <div className="bg-white rounded-lg border border-borderMuted shadow-sm overflow-hidden">
              <div className="px-5 py-3.5 bg-cream-100 border-b border-borderMuted flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-charcoal-800 flex items-center">
                    <AlertCircle className="w-4 h-4 mr-1.5 text-red-600" />
                    Certification Findings ({findings.length})
                  </h3>
                  <p className="text-[11px] text-charcoal-500 mt-0.5">
                    Issues requiring correction before PolicyEngine permits publication.
                  </p>
                </div>
                <button
                  onClick={() => onNavigateToRemediation(run.certification_id)}
                  className="text-xs font-medium text-sage-700 hover:text-sage-900 inline-flex items-center"
                >
                  Manage in Remediation <ArrowRight className="w-3 h-3 ml-1" />
                </button>
              </div>

              {findings.length === 0 ? (
                <div className="p-8 text-center text-xs text-sage-800 bg-sage-50/20">
                  <CheckCircle2 className="w-6 h-6 text-sage-600 mx-auto mb-1.5" />
                  No compliance findings or defects identified for this certification run.
                </div>
              ) : (
                <div className="divide-y divide-borderMuted">
                  {findings.map((f) => (
                    <div key={f.id} className="p-4 hover:bg-cream-50/60 transition-colors">
                      <div className="flex items-start justify-between">
                        <div className="space-y-1">
                          <div className="flex items-center space-x-2">
                            <span className="font-semibold text-xs text-charcoal-900">
                              {f.title}
                            </span>
                            <Badge status={f.severity} size="sm" />
                            <Badge status={f.remediation_status} size="sm" />
                          </div>
                          <p className="text-xs text-charcoal-600">{f.description}</p>
                          {f.failure_reason && (
                            <p className="text-xs text-red-700">
                              <span className="font-medium">Reason:</span> {f.failure_reason}
                            </p>
                          )}
                          {f.remediation_guidance && (
                            <p className="text-xs text-sage-800">
                              <span className="font-medium">Action:</span> {f.remediation_guidance}
                            </p>
                          )}
                        </div>
                        <div className="text-right text-[11px] font-mono text-charcoal-400">
                          {f.finding_id}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
