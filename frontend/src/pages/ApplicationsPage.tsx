import React, { useEffect, useState } from 'react';
import {
  Plus,
  RefreshCw,
  Search,
  ExternalLink,
  ArrowRight,
  AlertCircle,
  CheckCircle,
  PlayCircle,
  History,
} from 'lucide-react';
import { api } from '../api/client';
import {
  Application,
  ApplicationLatestStatus,
  PublicationStatus,
  CertificationRun,
} from '../types/api';
import { Badge } from '../components/Badge';

interface ApplicationsPageProps {
  selectedAppId?: string | null;
  onSelectCertification: (certId: string) => void;
  onNavigateToPublication: (appId: string, version: string) => void;
}

export const ApplicationsPage: React.FC<ApplicationsPageProps> = ({
  selectedAppId,
  onSelectCertification,
  onNavigateToPublication,
}) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [applications, setApplications] = useState<Application[]>([]);
  const [statuses, setStatuses] = useState<Record<string, ApplicationLatestStatus>>({});
  const [pubStatuses, setPubStatuses] = useState<Record<string, PublicationStatus>>({});
  const [searchTerm, setSearchTerm] = useState('');

  // Selected App detail view & certification history
  const [activeApp, setActiveApp] = useState<Application | null>(null);
  const [historyRuns, setHistoryRuns] = useState<CertificationRun[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Register Modal state
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [newAppId, setNewAppId] = useState('');
  const [newAppName, setNewAppName] = useState('');
  const [newAppDesc, setNewAppDesc] = useState('');
  const [newAppType, setNewAppType] = useState('AI_AGENT');
  const [newAppVersion, setNewAppVersion] = useState('1.0.0');
  const [submitting, setSubmitting] = useState(false);

  // Action states
  const [actionInProgress, setActionInProgress] = useState(false);

  const loadApplications = async () => {
    setLoading(true);
    setError(null);
    try {
      const apps = await api.listApplications(0, 100);
      setApplications(apps);

      // Load status and publication readiness
      const statusMap: Record<string, ApplicationLatestStatus> = {};
      const pubMap: Record<string, PublicationStatus> = {};

      await Promise.all(
        apps.map(async (app) => {
          try {
            const [stat, pub] = await Promise.all([
              api.getApplicationStatus(app.application_id),
              api.getApplicationPublicationStatus(app.application_id, app.current_version),
            ]);
            statusMap[app.application_id] = stat;
            pubMap[app.application_id] = pub;
          } catch {
            // Ignore individual status fetch errors
          }
        })
      );

      setStatuses(statusMap);
      setPubStatuses(pubMap);

      // If selectedAppId is provided, select it
      if (selectedAppId) {
        const found = apps.find((a) => a.application_id === selectedAppId);
        if (found) {
          selectAppDetails(found);
        }
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load applications from ACE backend');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadApplications();
  }, [selectedAppId]);

  const selectAppDetails = async (app: Application) => {
    setActiveApp(app);
    setLoadingHistory(true);
    try {
      const runs = await api.getApplicationCertificationRuns(app.application_id, 0, 50);
      setHistoryRuns(runs);
    } catch (err: any) {
      setError(err?.message || `Failed to fetch certification history for ${app.application_id}`);
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleRegisterApp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAppId.trim() || !newAppName.trim()) return;

    setSubmitting(true);
    setError(null);
    try {
      const created = await api.createApplication({
        application_id: newAppId.trim(),
        name: newAppName.trim(),
        description: newAppDesc.trim() || undefined,
        application_type: newAppType,
        version: newAppVersion.trim() || '1.0.0',
      });

      setShowRegisterModal(false);
      setNewAppId('');
      setNewAppName('');
      setNewAppDesc('');
      setSuccessMsg(`Application "${created.name}" registered successfully.`);
      await loadApplications();
      selectAppDetails(created);
    } catch (err: any) {
      setError(err?.message || 'Failed to register application');
    } finally {
      setSubmitting(false);
    }
  };

  const handleTriggerCertification = async (appId: string, version: string) => {
    if (actionInProgress) return;
    setActionInProgress(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const run = await api.startCertification({
        application_id: appId,
        version,
      });
      setSuccessMsg(`Certification run ${run.certification_id} queued for ${appId} v${version}.`);
      if (activeApp?.application_id === appId) {
        await selectAppDetails(activeApp);
      }
      await loadApplications();
    } catch (err: any) {
      setError(err?.message || 'Failed to start certification run');
    } finally {
      setActionInProgress(false);
    }
  };

  const handleTriggerRecertify = async (appId: string, version: string) => {
    if (actionInProgress) return;
    setActionInProgress(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await api.recertifyApplication(appId, version);
      setSuccessMsg(`Re-certification queued: ${res.certification_id || 'Job accepted'}`);
      if (activeApp?.application_id === appId) {
        await selectAppDetails(activeApp);
      }
      await loadApplications();
    } catch (err: any) {
      setError(err?.message || 'Failed to request re-certification');
    } finally {
      setActionInProgress(false);
    }
  };

  const filteredApps = applications.filter((app) => {
    const q = searchTerm.toLowerCase();
    return (
      app.application_id.toLowerCase().includes(q) ||
      app.name.toLowerCase().includes(q) ||
      app.application_type.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-charcoal-900">
            Registered Applications
          </h1>
          <p className="text-sm text-charcoal-500 mt-0.5">
            Manage agents, inspect compliance status, and view historical certification runs.
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={loadApplications}
            disabled={loading}
            className="inline-flex items-center px-3 py-1.5 border border-borderMuted rounded-md text-sm font-medium text-charcoal-700 bg-white hover:bg-cream-100 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={() => setShowRegisterModal(true)}
            className="inline-flex items-center px-3.5 py-1.5 bg-sage-500 hover:bg-sage-600 text-white rounded-md text-sm font-medium transition-colors"
          >
            <Plus className="w-4 h-4 mr-1.5" />
            Register Application
          </button>
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

      {/* Main Grid: Application List + Detail Pane */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Application Table */}
        <div className={`${activeApp ? 'lg:col-span-7' : 'lg:col-span-12'} space-y-4`}>
          {/* Search bar */}
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-3 text-charcoal-400" />
            <input
              type="text"
              placeholder="Search applications by name, ID or type..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-4 py-2 border border-borderMuted rounded-md bg-white text-sm text-charcoal-900 focus:outline-none focus:ring-1 focus:ring-sage-500"
            />
          </div>

          <div className="bg-white rounded-lg border border-borderMuted shadow-sm overflow-hidden">
            {loading && applications.length === 0 ? (
              <div className="p-8 text-center text-sm text-charcoal-500">
                Loading applications from backend...
              </div>
            ) : filteredApps.length === 0 ? (
              <div className="p-8 text-center text-sm text-charcoal-500">
                No registered applications found matching "{searchTerm}".
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm text-charcoal-700">
                  <thead className="bg-cream-100 text-charcoal-600 text-xs uppercase font-medium border-b border-borderMuted">
                    <tr>
                      <th className="px-4 py-3">Application</th>
                      <th className="px-4 py-3">Type / Version</th>
                      <th className="px-4 py-3">Latest Status</th>
                      <th className="px-4 py-3">Publication</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-borderMuted">
                    {filteredApps.map((app) => {
                      const stat = statuses[app.application_id];
                      const pub = pubStatuses[app.application_id];
                      const isSelected = activeApp?.application_id === app.application_id;

                      const certStatus = stat?.latest_certification?.status || 'UNVERIFIED';
                      const pubReady = pub?.is_ready_to_publish ?? false;
                      const pubRecordStatus = pub?.publication_record_status;

                      return (
                        <tr
                          key={app.application_id}
                          className={`hover:bg-cream-50/80 cursor-pointer transition-colors ${
                            isSelected ? 'bg-sage-50/50' : ''
                          }`}
                          onClick={() => selectAppDetails(app)}
                        >
                          <td className="px-4 py-3.5">
                            <div className="font-medium text-charcoal-900">{app.name}</div>
                            <div className="font-mono text-xs text-charcoal-500">
                              {app.application_id}
                            </div>
                          </td>
                          <td className="px-4 py-3.5 text-xs">
                            <div className="font-medium text-charcoal-700">
                              {app.application_type}
                            </div>
                            <div className="font-mono text-charcoal-500">
                              v{app.current_version}
                            </div>
                          </td>
                          <td className="px-4 py-3.5">
                            <Badge status={certStatus} size="sm" />
                          </td>
                          <td className="px-4 py-3.5 text-xs">
                            {pubRecordStatus ? (
                              <Badge status={pubRecordStatus} size="sm" />
                            ) : pubReady ? (
                              <span className="inline-flex items-center text-sage-800 font-medium">
                                <span className="w-1.5 h-1.5 rounded-full bg-sage-500 mr-1.5" />
                                Ready
                              </span>
                            ) : (
                              <span className="text-charcoal-400">Not Eligible</span>
                            )}
                          </td>
                          <td className="px-4 py-3.5 text-right whitespace-nowrap">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                selectAppDetails(app);
                              }}
                              className="text-xs text-sage-700 font-medium hover:text-sage-900 mr-2"
                            >
                              History
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleTriggerCertification(app.application_id, app.current_version);
                              }}
                              disabled={actionInProgress}
                              className="text-xs text-charcoal-600 hover:text-charcoal-900 border border-borderMuted px-2 py-0.5 rounded bg-white hover:bg-cream-50 disabled:opacity-50"
                            >
                              Certify
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Right: Application Details & Certification History */}
        {activeApp && (
          <div className="lg:col-span-5 space-y-4">
            <div className="bg-white rounded-lg border border-borderMuted shadow-sm p-5 space-y-4">
              <div className="flex items-start justify-between border-b border-borderMuted pb-3">
                <div>
                  <h3 className="font-semibold text-charcoal-900 text-base">
                    {activeApp.name}
                  </h3>
                  <div className="font-mono text-xs text-charcoal-500">
                    {activeApp.application_id}
                  </div>
                </div>
                <button
                  onClick={() => setActiveApp(null)}
                  className="text-xs text-charcoal-400 hover:text-charcoal-700"
                >
                  Close
                </button>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-charcoal-400">Current Version:</span>
                  <div className="font-mono font-medium text-charcoal-900">
                    v{activeApp.current_version}
                  </div>
                </div>
                <div>
                  <span className="text-charcoal-400">Application Type:</span>
                  <div className="font-medium text-charcoal-900">
                    {activeApp.application_type}
                  </div>
                </div>
                <div className="col-span-2">
                  <span className="text-charcoal-400">Description:</span>
                  <div className="text-charcoal-700 mt-0.5">
                    {activeApp.description || 'No description provided.'}
                  </div>
                </div>
              </div>

              {/* Action buttons */}
              <div className="pt-2 flex flex-wrap gap-2 border-t border-borderMuted">
                <button
                  onClick={() =>
                    handleTriggerCertification(activeApp.application_id, activeApp.current_version)
                  }
                  disabled={actionInProgress}
                  className="inline-flex items-center px-3 py-1.5 bg-sage-500 hover:bg-sage-600 text-white rounded text-xs font-medium disabled:opacity-50"
                >
                  <PlayCircle className="w-3.5 h-3.5 mr-1.5" />
                  Start Certification
                </button>
                <button
                  onClick={() =>
                    handleTriggerRecertify(activeApp.application_id, activeApp.current_version)
                  }
                  disabled={actionInProgress}
                  className="inline-flex items-center px-3 py-1.5 border border-borderMuted bg-white hover:bg-cream-100 text-charcoal-700 rounded text-xs font-medium disabled:opacity-50"
                >
                  <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                  Re-certify
                </button>
                {pubStatuses[activeApp.application_id]?.is_ready_to_publish && (
                  <button
                    onClick={() =>
                      onNavigateToPublication(activeApp.application_id, activeApp.current_version)
                    }
                    className="inline-flex items-center px-3 py-1.5 bg-charcoal-800 hover:bg-charcoal-900 text-white rounded text-xs font-medium"
                  >
                    <ExternalLink className="w-3.5 h-3.5 mr-1.5" />
                    Publish View
                  </button>
                )}
              </div>
            </div>

            {/* Certification History */}
            <div className="bg-white rounded-lg border border-borderMuted shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-borderMuted flex items-center justify-between">
                <div className="flex items-center space-x-1.5">
                  <History className="w-4 h-4 text-charcoal-500" />
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-charcoal-800">
                    Certification History
                  </h4>
                </div>
                <span className="text-xs text-charcoal-400">
                  {historyRuns.length} runs
                </span>
              </div>

              {loadingHistory ? (
                <div className="p-6 text-center text-xs text-charcoal-500">
                  Loading history runs...
                </div>
              ) : historyRuns.length === 0 ? (
                <div className="p-6 text-center text-xs text-charcoal-500">
                  No certification runs recorded for this application.
                </div>
              ) : (
                <div className="divide-y divide-borderMuted max-h-80 overflow-y-auto">
                  {historyRuns.map((run) => (
                    <div
                      key={run.certification_id}
                      className="p-3.5 hover:bg-cream-50/60 flex items-center justify-between text-xs transition-colors"
                    >
                      <div className="space-y-1">
                        <div className="font-mono font-medium text-charcoal-900">
                          {run.certification_id}
                        </div>
                        <div className="flex items-center space-x-2 text-charcoal-500">
                          <span>v{run.application_version}</span>
                          <span>•</span>
                          <span>{new Date(run.created_at).toLocaleDateString()}</span>
                        </div>
                      </div>
                      <div className="flex items-center space-x-2">
                        <Badge status={run.status} size="sm" />
                        <button
                          onClick={() => onSelectCertification(run.certification_id)}
                          className="p-1 text-charcoal-400 hover:text-sage-700"
                          title="Open Details"
                        >
                          <ArrowRight className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Register Application Modal */}
      {showRegisterModal && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-lg border border-borderMuted shadow-lg max-w-md w-full p-6 space-y-4">
            <h3 className="text-base font-semibold text-charcoal-900">
              Register New Application
            </h3>
            <p className="text-xs text-charcoal-500">
              Add a new AI agent or web application to the ACE compliance registry.
            </p>

            <form onSubmit={handleRegisterApp} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-charcoal-700 mb-1">
                  Application ID <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. AGENT-FINANCE-PRO"
                  value={newAppId}
                  onChange={(e) => setNewAppId(e.target.value)}
                  className="w-full px-3 py-1.5 border border-borderMuted rounded text-sm text-charcoal-900 focus:outline-none focus:ring-1 focus:ring-sage-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-charcoal-700 mb-1">
                  Application Display Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Finance Analytics Agent"
                  value={newAppName}
                  onChange={(e) => setNewAppName(e.target.value)}
                  className="w-full px-3 py-1.5 border border-borderMuted rounded text-sm text-charcoal-900 focus:outline-none focus:ring-1 focus:ring-sage-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-charcoal-700 mb-1">
                    Application Type
                  </label>
                  <select
                    value={newAppType}
                    onChange={(e) => setNewAppType(e.target.value)}
                    className="w-full px-3 py-1.5 border border-borderMuted rounded text-sm text-charcoal-900 focus:outline-none focus:ring-1 focus:ring-sage-500"
                  >
                    <option value="AI_AGENT">AI Agent</option>
                    <option value="WEB_APP">Web App</option>
                    <option value="OTHER">Other</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-charcoal-700 mb-1">
                    Initial Version
                  </label>
                  <input
                    type="text"
                    placeholder="1.0.0"
                    value={newAppVersion}
                    onChange={(e) => setNewAppVersion(e.target.value)}
                    className="w-full px-3 py-1.5 border border-borderMuted rounded text-sm text-charcoal-900 focus:outline-none focus:ring-1 focus:ring-sage-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-charcoal-700 mb-1">
                  Description
                </label>
                <textarea
                  rows={2}
                  placeholder="Brief description of application role..."
                  value={newAppDesc}
                  onChange={(e) => setNewAppDesc(e.target.value)}
                  className="w-full px-3 py-1.5 border border-borderMuted rounded text-sm text-charcoal-900 focus:outline-none focus:ring-1 focus:ring-sage-500"
                />
              </div>

              <div className="flex justify-end space-x-2 pt-3 border-t border-borderMuted">
                <button
                  type="button"
                  onClick={() => setShowRegisterModal(false)}
                  className="px-3.5 py-1.5 border border-borderMuted text-charcoal-600 rounded text-sm hover:bg-cream-100"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-1.5 bg-sage-500 hover:bg-sage-600 text-white rounded text-sm font-medium disabled:opacity-50"
                >
                  {submitting ? 'Registering...' : 'Register'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
