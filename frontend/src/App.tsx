import React, { useState, useEffect } from 'react';
import { Navbar, NavigationTab } from './components/Navbar';
import { DashboardPage } from './pages/DashboardPage';
import { ApplicationsPage } from './pages/ApplicationsPage';
import { CertificationDetailsPage } from './pages/CertificationDetailsPage';
import { RemediationPage } from './pages/RemediationPage';
import { PublicationPage } from './pages/PublicationPage';
import { IntegrationsPage } from './pages/IntegrationsPage';
import { api } from './api/client';
import { HealthResponse } from './types/api';

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<NavigationTab>('dashboard');

  // Shared navigation state
  const [activeCertId, setActiveCertId] = useState<string | null>(null);
  const [activeAppId, setActiveAppId] = useState<string | null>(null);
  const [activeVersion, setActiveVersion] = useState<string | null>(null);

  // Health check
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isHealthLoading, setIsHealthLoading] = useState(true);

  useEffect(() => {
    api
      .checkHealth()
      .then((h) => setHealth(h))
      .catch(() => setHealth(null))
      .finally(() => setIsHealthLoading(false));
  }, []);

  const handleSelectCertification = (certId: string) => {
    setActiveCertId(certId);
    setCurrentTab('certification');
  };

  const handleSelectApplication = (appId: string) => {
    setActiveAppId(appId);
    setCurrentTab('applications');
  };

  const handleNavigateToRemediation = (certId: string) => {
    setActiveCertId(certId);
    setCurrentTab('remediation');
  };

  const handleNavigateToPublication = (appId: string, version: string) => {
    setActiveAppId(appId);
    setActiveVersion(version);
    setCurrentTab('publication');
  };

  return (
    <div className="min-h-screen flex flex-col bg-cream-50 text-charcoal-900 font-sans">
      <Navbar
        currentTab={currentTab}
        onSelectTab={setCurrentTab}
        health={health}
        isHealthLoading={isHealthLoading}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {currentTab === 'dashboard' && (
          <DashboardPage
            onSelectCertification={handleSelectCertification}
            onSelectApplication={handleSelectApplication}
          />
        )}

        {currentTab === 'applications' && (
          <ApplicationsPage
            selectedAppId={activeAppId}
            onSelectCertification={handleSelectCertification}
            onNavigateToPublication={handleNavigateToPublication}
          />
        )}

        {currentTab === 'certification' && (
          <CertificationDetailsPage
            initialCertificationId={activeCertId}
            onNavigateToRemediation={handleNavigateToRemediation}
            onNavigateToPublication={handleNavigateToPublication}
          />
        )}

        {currentTab === 'remediation' && (
          <RemediationPage
            initialCertificationId={activeCertId}
            onSelectCertification={handleSelectCertification}
          />
        )}

        {currentTab === 'publication' && (
          <PublicationPage
            initialAppId={activeAppId}
            initialVersion={activeVersion}
            onNavigateToCertification={handleSelectCertification}
          />
        )}

        {currentTab === 'integrations' && <IntegrationsPage />}
      </main>

      <footer className="border-t border-borderMuted bg-cream-50 py-4 text-center text-xs text-charcoal-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row justify-between items-center gap-2">
          <span>
            ACE Agent Compliance Engine • Autonomous Certification Platform
          </span>
          <span className="font-mono text-[11px] text-charcoal-400">
            Policy Engine v1.0 • SHA-256 Provenance
          </span>
        </div>
      </footer>
    </div>
  );
};

export default App;
