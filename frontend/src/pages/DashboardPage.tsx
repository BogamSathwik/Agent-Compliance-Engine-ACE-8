import React, { useEffect, useState } from 'react';
import { RefreshCw, ArrowRight, AlertCircle } from 'lucide-react';
import { api } from '../api/client';
import { Application, CertificationRun, ApplicationLatestStatus } from '../types/api';
import { StatCard } from '../components/StatCard';
import { Badge } from '../components/Badge';

interface DashboardPageProps {
  onSelectCertification: (certId: string) => void;
  onSelectApplication: (appId: string) => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  onSelectCertification,
  onSelectApplication,
}) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [applications, setApplications] = useState<Application[]>([]);
  const [certifications, setCertifications] = useState<CertificationRun[]>([]);
  const [appStatuses, setAppStatuses] = useState<Record<string, ApplicationLatestStatus>>({});

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [apps, certs] = await Promise.all([
        api.listApplications(0, 100),
        api.listCertifications(undefined, undefined, 0, 50),
      ]);

      setApplications(apps);
      setCertifications(certs);

      // Fetch statuses for top applications
      const statusMap: Record<string, ApplicationLatestStatus> = {};
      await Promise.all(
        apps.slice(0, 15).map(async (app) => {
          try {
            const stat = await api.getApplicationStatus(app.application_id);
            statusMap[app.application_id] = stat;
          } catch {
            // Non-blocking status fetch
          }
        })
      );
      setAppStatuses(statusMap);
    } catch (err: any) {
      setError(err?.message || 'Failed to load dashboard metrics from ACE backend');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Compute metrics from actual authoritative data
  const totalApps = applications.length;

  let readyToPublishCount = 0;
  let notReadyCount = 0;
  Object.values(appStatuses).forEach((stat) => {
    if (stat.latest_certification?.status === 'READY_TO_PUBLISH') {
      readyToPublishCount++;
    } else if (stat.latest_certification?.status === 'NOT_READY' || stat.latest_certification?.status === 'ERROR') {
      notReadyCount++;
    }
  });

  const inProgressRuns = certifications.filter(
    (c) => c.status === 'RUNNING' || c.status === 'QUEUED'
  ).length;

  const recentCompletedRuns = certifications
    .filter((c) => c.status !== 'RUNNING' && c.status !== 'QUEUED')
    .slice(0, 8);

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-charcoal-900">
            Compliance Dashboard
          </h1>
          <p className="text-sm text-charcoal-500 mt-0.5">
            Overview of application certifications and publication readiness.
          </p>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="inline-flex items-center justify-center px-3.5 py-1.5 border border-borderMuted rounded-md text-sm font-medium text-charcoal-700 bg-white hover:bg-cream-100 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="p-4 rounded-md bg-red-50 border border-red-200 text-red-800 flex items-start space-x-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <span className="font-semibold">Backend Error:</span> {error}
          </div>
        </div>
      )}

      {/* Primary Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Applications"
          value={totalApps}
          subtext="Registered in ACE registry"
        />
        <StatCard
          label="Ready to Publish"
          value={readyToPublishCount}
          variant="success"
          subtext="17 docs, 9 rules, QA passed"
        />
        <StatCard
          label="Not Ready"
          value={notReadyCount}
          variant={notReadyCount > 0 ? 'warning' : 'default'}
          subtext="Pending remediation or verification"
        />
        <StatCard
          label="Runs In Progress"
          value={inProgressRuns}
          variant={inProgressRuns > 0 ? 'warning' : 'default'}
          subtext="Autonomous pipeline active"
        />
      </div>

      {/* Recently Completed Certifications */}
      <div className="bg-white rounded-lg border border-borderMuted shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-borderMuted flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-charcoal-900 uppercase tracking-wider">
              Recently Completed Certifications
            </h2>
            <p className="text-xs text-charcoal-500 mt-0.5">
              Authoritative results evaluated by PolicyEngine.
            </p>
          </div>
        </div>

        {loading && recentCompletedRuns.length === 0 ? (
          <div className="p-8 text-center text-sm text-charcoal-500">
            Loading certification runs from backend...
          </div>
        ) : recentCompletedRuns.length === 0 ? (
          <div className="p-8 text-center text-sm text-charcoal-500">
            No completed certification runs found.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-charcoal-700">
              <thead className="bg-cream-100 text-charcoal-600 text-xs uppercase font-medium border-b border-borderMuted">
                <tr>
                  <th className="px-5 py-3">Certification ID</th>
                  <th className="px-5 py-3">Application</th>
                  <th className="px-5 py-3">Version</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Checks / Findings</th>
                  <th className="px-5 py-3">Completed At</th>
                  <th className="px-5 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-borderMuted">
                {recentCompletedRuns.map((run) => (
                  <tr key={run.certification_id} className="hover:bg-cream-50/70 transition-colors">
                    <td className="px-5 py-3.5 font-mono text-xs font-medium text-charcoal-900">
                      {run.certification_id}
                    </td>
                    <td className="px-5 py-3.5">
                      <button
                        onClick={() => onSelectApplication(run.application_id)}
                        className="font-medium text-charcoal-900 hover:text-sage-700 hover:underline"
                      >
                        {run.application_id}
                      </button>
                    </td>
                    <td className="px-5 py-3.5 text-xs text-charcoal-600 font-mono">
                      v{run.application_version}
                    </td>
                    <td className="px-5 py-3.5">
                      <Badge status={run.status} size="sm" />
                    </td>
                    <td className="px-5 py-3.5 text-xs">
                      {run.findings_summary ? (
                        <div className="flex items-center space-x-2">
                          <span className="text-sage-800 font-medium">
                            {run.findings_summary.passed} Pass
                          </span>
                          <span className="text-charcoal-300">/</span>
                          <span className={run.findings_summary.failed > 0 ? 'text-red-700 font-medium' : 'text-charcoal-500'}>
                            {run.findings_summary.failed} Fail
                          </span>
                          <span className="text-charcoal-300">/</span>
                          <span className="text-charcoal-500">
                            {run.findings_summary.not_verified} Unverified
                          </span>
                        </div>
                      ) : (
                        <span className="text-charcoal-400">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-xs text-charcoal-500 whitespace-nowrap">
                      {run.completed_at
                        ? new Date(run.completed_at).toLocaleString()
                        : new Date(run.created_at).toLocaleString()}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <button
                        onClick={() => onSelectCertification(run.certification_id)}
                        className="inline-flex items-center text-xs font-medium text-sage-700 hover:text-sage-900"
                      >
                        Details <ArrowRight className="w-3.5 h-3.5 ml-1" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
