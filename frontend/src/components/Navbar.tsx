import React from 'react';
import { ShieldCheck, Activity } from 'lucide-react';
import { HealthResponse } from '../types/api';

export type NavigationTab =
  | 'dashboard'
  | 'applications'
  | 'certification'
  | 'remediation'
  | 'publication'
  | 'integrations';

interface NavbarProps {
  currentTab: NavigationTab;
  onSelectTab: (tab: NavigationTab) => void;
  health: HealthResponse | null;
  isHealthLoading: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentTab,
  onSelectTab,
  health,
  isHealthLoading,
}) => {
  const navItems: { id: NavigationTab; label: string }[] = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'applications', label: 'Applications' },
    { id: 'certification', label: 'Certification Details' },
    { id: 'remediation', label: 'Remediation' },
    { id: 'publication', label: 'Publication' },
    { id: 'integrations', label: 'MCP Integrations' },
  ];

  return (
    <header className="border-b border-borderMuted bg-cream-50 sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          {/* Logo & Brand */}
          <div className="flex items-center space-x-3 cursor-pointer" onClick={() => onSelectTab('dashboard')}>
            <div className="w-8 h-8 rounded-md bg-sage-500 text-white flex items-center justify-center">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight text-charcoal-900">
                ACE
              </div>
              <div className="text-[11px] text-charcoal-500 font-medium">
                Agent Compliance Engine
              </div>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="hidden md:flex space-x-1">
            {navItems.map((item) => {
              const active = currentTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onSelectTab(item.id)}
                  className={`px-3.5 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    active
                      ? 'bg-sage-100 text-sage-900 border border-sage-200 shadow-sm'
                      : 'text-charcoal-600 hover:text-charcoal-900 hover:bg-cream-100'
                  }`}
                >
                  {item.label}
                </button>
              );
            })}
          </nav>

          {/* Backend Status indicator */}
          <div className="flex items-center space-x-2 text-xs">
            {isHealthLoading ? (
              <span className="flex items-center text-charcoal-400">
                <Activity className="w-3.5 h-3.5 animate-spin mr-1.5" />
                Connecting...
              </span>
            ) : health?.status === 'ok' ? (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-sage-50 text-sage-800 border border-sage-200">
                <span className="w-1.5 h-1.5 rounded-full bg-sage-500 mr-1.5"></span>
                Backend v{health.version}
              </span>
            ) : (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-200">
                <span className="w-1.5 h-1.5 rounded-full bg-red-500 mr-1.5"></span>
                Backend Offline
              </span>
            )}
          </div>
        </div>

        {/* Mobile Navigation bar */}
        <div className="md:hidden flex overflow-x-auto space-x-1 pb-2 pt-1 border-t border-borderMuted">
          {navItems.map((item) => {
            const active = currentTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                className={`px-2.5 py-1 whitespace-nowrap rounded text-xs font-medium ${
                  active
                    ? 'bg-sage-100 text-sage-900 border border-sage-200'
                    : 'text-charcoal-600 hover:bg-cream-100'
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      </div>
    </header>
  );
};
