import React, { useState, useEffect } from 'react';
import {
  Network,
  CheckCircle,
  XCircle,
  RefreshCw,
  Send,
  Save,
  Key,
  Globe,
  Shield,
  Layers,
  Copy,
  Check,
  AlertTriangle,
} from 'lucide-react';
import { api } from '../api/client';
import { IntegrationsResponse, ProbeResponse } from '../types/api';

export const IntegrationsPage: React.FC = () => {
  const [data, setData] = useState<IntegrationsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit form states for each integration: { [id]: { mcp_url, mcp_auth_token, base_url, api_key } }
  const [formData, setFormData] = useState<
    Record<string, { mcp_url: string; mcp_auth_token: string; base_url: string; api_key: string }>
  >({});
  const [saveStatus, setSaveStatus] = useState<Record<string, 'idle' | 'saving' | 'saved' | 'error'>>({});

  // Probe testing state: { [id]: { isProbing, result } }
  const [probeResults, setProbeResults] = useState<Record<string, ProbeResponse | null>>({});
  const [probingState, setProbingState] = useState<Record<string, boolean>>({});

  // Custom Probe URL Sandbox
  const [customProbeUrl, setCustomProbeUrl] = useState('');
  const [customProbeToken, setCustomProbeToken] = useState('');
  const [customProbeResult, setCustomProbeResult] = useState<ProbeResponse | null>(null);
  const [isCustomProbing, setIsCustomProbing] = useState(false);

  // Clipboard copy state
  const [copiedEndpoint, setCopiedEndpoint] = useState(false);

  const fetchIntegrations = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.getIntegrations();
      setData(res);

      // Pre-fill form fields
      const forms: Record<string, { mcp_url: string; mcp_auth_token: string; base_url: string; api_key: string }> = {};
      res.integrations.forEach((item) => {
        forms[item.id] = {
          mcp_url: item.mcp_url || '',
          mcp_auth_token: '', // Leave blank unless user re-enters
          base_url: item.base_url || '',
          api_key: '',
        };
      });
      setFormData(forms);
    } catch (err: any) {
      setError(err?.message || 'Failed to load integrations');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchIntegrations();
  }, []);

  const handleFieldChange = (id: string, field: 'mcp_url' | 'mcp_auth_token' | 'base_url' | 'api_key', val: string) => {
    setFormData((prev) => ({
      ...prev,
      [id]: {
        ...(prev[id] || { mcp_url: '', mcp_auth_token: '', base_url: '', api_key: '' }),
        [field]: val,
      },
    }));
  };

  const handleSave = async (id: string) => {
    const item = formData[id];
    if (!item) return;

    setSaveStatus((prev) => ({ ...prev, [id]: 'saving' }));
    try {
      const payload: any = {
        mcp_url: item.mcp_url,
        base_url: item.base_url,
      };
      if (item.mcp_auth_token.trim()) {
        payload.mcp_auth_token = item.mcp_auth_token.trim();
      }
      if (item.api_key.trim()) {
        payload.api_key = item.api_key.trim();
      }

      await api.updateIntegration(id, payload);
      setSaveStatus((prev) => ({ ...prev, [id]: 'saved' }));
      setTimeout(() => {
        setSaveStatus((prev) => ({ ...prev, [id]: 'idle' }));
      }, 3000);
      // Refresh to update masked values
      fetchIntegrations();
    } catch (err: any) {
      alert(`Save failed: ${err?.message || err}`);
      setSaveStatus((prev) => ({ ...prev, [id]: 'error' }));
    }
  };

  const handleProbe = async (id: string) => {
    const item = formData[id];
    const url = item?.mcp_url;
    if (!url) {
      alert('Please enter an MCP Endpoint URL first before probing.');
      return;
    }

    setProbingState((prev) => ({ ...prev, [id]: true }));
    try {
      const token = item.mcp_auth_token.trim() || undefined;
      const res = await api.probeMcpEndpoint(url, token);
      setProbeResults((prev) => ({ ...prev, [id]: res }));
    } catch (err: any) {
      setProbeResults((prev) => ({
        ...prev,
        [id]: {
          status: 'FAILED',
          mcp_url: url,
          latency_ms: 0,
          tools: [],
          error_message: err?.message || 'Probe request failed',
        },
      }));
    } finally {
      setProbingState((prev) => ({ ...prev, [id]: false }));
    }
  };

  const handleCustomProbe = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customProbeUrl.trim()) return;

    setIsCustomProbing(true);
    setCustomProbeResult(null);
    try {
      const res = await api.probeMcpEndpoint(customProbeUrl.trim(), customProbeToken.trim() || undefined);
      setCustomProbeResult(res);
    } catch (err: any) {
      setCustomProbeResult({
        status: 'FAILED',
        mcp_url: customProbeUrl,
        latency_ms: 0,
        tools: [],
        error_message: err?.message || 'Probe request failed',
      });
    } finally {
      setIsCustomProbing(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedEndpoint(true);
    setTimeout(() => setCopiedEndpoint(false), 2000);
  };

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-borderMuted pb-5">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-charcoal-900 flex items-center gap-2">
            <Network className="w-6 h-6 text-sage-600" />
            MCP Integrations & Endpoints
          </h1>
          <p className="text-sm text-charcoal-600 mt-1">
            Configure, manage, and probe external Model Context Protocol (MCP) servers and endpoints used by ACE.
          </p>
        </div>
        <button
          onClick={fetchIntegrations}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-charcoal-700 bg-white border border-borderMuted rounded-md hover:bg-cream-100 shadow-sm transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 flex-shrink-0 text-red-500" />
          <span>{error}</span>
        </div>
      )}

      {/* Inbound MCP Server Card (ACE as Provider) */}
      {data?.ace_mcp_server && (
        <div className="bg-sage-50/70 border border-sage-200 rounded-xl p-5 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-lg bg-sage-500 text-white flex items-center justify-center flex-shrink-0 mt-0.5">
                <Shield className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-charcoal-900 flex items-center gap-2">
                  ACE Inbound MCP Server (Provider)
                  <span className="px-2 py-0.5 text-[11px] font-mono bg-sage-200 text-sage-800 rounded">
                    Protocol {data.ace_mcp_server.protocol_version}
                  </span>
                </h3>
                <p className="text-xs text-charcoal-600 mt-0.5">
                  External applications (such as AgentGen Pro or Agent WatchTower) can connect to this endpoint to
                  discover tools, trigger compliance certifications, and query policy statuses.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-1 text-xs font-medium rounded-full bg-sage-100 text-sage-800 border border-sage-300">
                {data.ace_mcp_server.exposed_tools_count} Tools Exposed
              </span>
            </div>
          </div>

          <div className="mt-4 flex items-center gap-2 bg-white/90 border border-sage-200 rounded-lg px-3 py-2 font-mono text-xs text-charcoal-800 overflow-x-auto">
            <Globe className="w-4 h-4 text-sage-600 flex-shrink-0" />
            <span className="flex-1 font-semibold">{data.ace_mcp_server.full_url}</span>
            <button
              onClick={() => copyToClipboard(data.ace_mcp_server.full_url)}
              className="inline-flex items-center gap-1 text-[11px] font-sans font-medium text-sage-700 hover:text-sage-900 px-2 py-1 rounded hover:bg-sage-100 transition-colors"
            >
              {copiedEndpoint ? <Check className="w-3.5 h-3.5 text-sage-600" /> : <Copy className="w-3.5 h-3.5" />}
              {copiedEndpoint ? 'Copied' : 'Copy URL'}
            </button>
          </div>
        </div>
      )}

      {/* External Subsystem Integration Cards */}
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-charcoal-900 flex items-center gap-2">
            <Layers className="w-5 h-5 text-sage-600" />
            External MCP Target Services
          </h2>
          <span className="text-xs text-charcoal-500">
            Configure external endpoints consumed during certification & publication
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {data?.integrations.map((item) => {
            const form = formData[item.id] || { mcp_url: '', mcp_auth_token: '', base_url: '', api_key: '' };
            const probe = probeResults[item.id];
            const isProbing = probingState[item.id] || false;
            const saveState = saveStatus[item.id] || 'idle';

            return (
              <div
                key={item.id}
                className="bg-white border border-borderMuted rounded-xl p-5 shadow-sm flex flex-col justify-between hover:border-sage-300 transition-all"
              >
                <div>
                  {/* Card Title & Status Badge */}
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div>
                      <h3 className="text-base font-semibold text-charcoal-900 flex items-center gap-2">
                        {item.name}
                      </h3>
                      <p className="text-xs text-charcoal-600 mt-0.5">{item.description}</p>
                    </div>
                    {item.is_configured ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 flex-shrink-0">
                        <CheckCircle className="w-3 h-3 text-emerald-500" />
                        Configured
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200 flex-shrink-0">
                        <AlertTriangle className="w-3 h-3 text-amber-500" />
                        Unconfigured
                      </span>
                    )}
                  </div>

                  {/* Expected tools */}
                  {item.expected_tools.length > 0 && (
                    <div className="flex items-center gap-1.5 flex-wrap my-3">
                      <span className="text-[11px] text-charcoal-500 font-medium">Expected Tool:</span>
                      {item.expected_tools.map((t) => (
                        <code key={t} className="px-1.5 py-0.5 text-[11px] font-mono bg-cream-100 text-charcoal-700 rounded border border-borderMuted">
                          {t}
                        </code>
                      ))}
                    </div>
                  )}

                  {/* Inputs Form */}
                  <div className="space-y-3.5 mt-4">
                    <div>
                      <label className="block text-xs font-medium text-charcoal-700 mb-1 flex items-center justify-between">
                        <span className="flex items-center gap-1.5">
                          <Globe className="w-3.5 h-3.5 text-sage-600" />
                          MCP Endpoint URL
                        </span>
                        <span className="text-[11px] text-charcoal-400 font-normal">JSON-RPC 2.0</span>
                      </label>
                      <input
                        type="url"
                        placeholder="e.g. http://localhost:3000/mcp or https://myblocks.in/.../mcp"
                        value={form.mcp_url}
                        onChange={(e) => handleFieldChange(item.id, 'mcp_url', e.target.value)}
                        className="w-full text-xs px-3 py-2 border border-borderMuted rounded-md bg-cream-50/50 font-mono focus:outline-none focus:ring-1 focus:ring-sage-500 focus:bg-white transition-colors"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-charcoal-700 mb-1 flex items-center justify-between">
                        <span className="flex items-center gap-1.5">
                          <Key className="w-3.5 h-3.5 text-sage-600" />
                          MCP Auth Token / Bearer Key
                        </span>
                        {item.mcp_auth_token && (
                          <span className="text-[11px] text-emerald-600 font-mono">Current: {item.mcp_auth_token}</span>
                        )}
                      </label>
                      <input
                        type="password"
                        placeholder={item.mcp_auth_token ? 'Enter new token to overwrite...' : 'Bearer token (optional)'}
                        value={form.mcp_auth_token}
                        onChange={(e) => handleFieldChange(item.id, 'mcp_auth_token', e.target.value)}
                        className="w-full text-xs px-3 py-2 border border-borderMuted rounded-md bg-cream-50/50 font-mono focus:outline-none focus:ring-1 focus:ring-sage-500 focus:bg-white transition-colors"
                      />
                    </div>
                  </div>

                  {/* Probe Result Box if available */}
                  {probe && (
                    <div
                      className={`mt-4 p-3 rounded-lg border text-xs ${
                        probe.status === 'SUCCESS'
                          ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900'
                          : 'bg-red-50/70 border-red-200 text-red-900'
                      }`}
                    >
                      <div className="flex items-center justify-between font-semibold">
                        <span className="flex items-center gap-1.5">
                          {probe.status === 'SUCCESS' ? (
                            <CheckCircle className="w-4 h-4 text-emerald-600" />
                          ) : (
                            <XCircle className="w-4 h-4 text-red-600" />
                          )}
                          Probe Status: {probe.status}
                        </span>
                        <span className="font-mono text-[11px] opacity-80">{probe.latency_ms} ms</span>
                      </div>
                      {probe.error_message && (
                        <p className="mt-1 text-red-700 text-[11px]">{probe.error_message}</p>
                      )}
                      {probe.tools && probe.tools.length > 0 && (
                        <div className="mt-2">
                          <span className="text-[11px] font-medium text-emerald-800">
                            Discovered Tools ({probe.tools.length}):
                          </span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {probe.tools.map((t, idx) => (
                              <span
                                key={idx}
                                className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-mono text-[10px]"
                              >
                                {t.name}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Card Action Buttons */}
                <div className="flex items-center justify-between gap-3 mt-5 pt-3 border-t border-borderMuted">
                  <button
                    onClick={() => handleProbe(item.id)}
                    disabled={isProbing || !form.mcp_url}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-charcoal-700 bg-cream-100 border border-borderMuted rounded-md hover:bg-cream-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <Send className={`w-3.5 h-3.5 ${isProbing ? 'animate-pulse' : ''}`} />
                    {isProbing ? 'Probing...' : 'Test Connection'}
                  </button>

                  <button
                    onClick={() => handleSave(item.id)}
                    disabled={saveState === 'saving'}
                    className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium text-white rounded-md shadow-sm transition-colors ${
                      saveState === 'saved'
                        ? 'bg-emerald-600 hover:bg-emerald-700'
                        : 'bg-sage-600 hover:bg-sage-700'
                    }`}
                  >
                    <Save className="w-3.5 h-3.5" />
                    {saveState === 'saving'
                      ? 'Saving...'
                      : saveState === 'saved'
                      ? 'Saved!'
                      : 'Save Endpoint'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Custom Endpoint Probe Sandbox */}
      <div className="bg-white border border-borderMuted rounded-xl p-6 shadow-sm">
        <h3 className="text-base font-semibold text-charcoal-900 flex items-center gap-2 mb-1">
          <Send className="w-5 h-5 text-sage-600" />
          Test Any Custom MCP Endpoint
        </h3>
        <p className="text-xs text-charcoal-600 mb-4">
          Test any external application's MCP server before saving it. This executes an MCP JSON-RPC 2.0{' '}
          <code className="text-charcoal-800 font-mono">tools/list</code> request and reports response time and capabilities.
        </p>

        <form onSubmit={handleCustomProbe} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="md:col-span-2">
              <label className="block text-xs font-medium text-charcoal-700 mb-1">MCP URL</label>
              <input
                type="url"
                required
                placeholder="http://localhost:3000/mcp or https://your-server.com/mcp"
                value={customProbeUrl}
                onChange={(e) => setCustomProbeUrl(e.target.value)}
                className="w-full text-xs px-3 py-2 border border-borderMuted rounded-md bg-cream-50/50 font-mono focus:outline-none focus:ring-1 focus:ring-sage-500 focus:bg-white transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-charcoal-700 mb-1">Bearer Token (optional)</label>
              <input
                type="password"
                placeholder="Bearer token"
                value={customProbeToken}
                onChange={(e) => setCustomProbeToken(e.target.value)}
                className="w-full text-xs px-3 py-2 border border-borderMuted rounded-md bg-cream-50/50 font-mono focus:outline-none focus:ring-1 focus:ring-sage-500 focus:bg-white transition-colors"
              />
            </div>
          </div>

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isCustomProbing || !customProbeUrl}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-sage-600 hover:bg-sage-700 rounded-md shadow-sm disabled:opacity-50 transition-colors"
            >
              <Send className={`w-3.5 h-3.5 ${isCustomProbing ? 'animate-pulse' : ''}`} />
              {isCustomProbing ? 'Probing MCP Endpoint...' : 'Send MCP Probe'}
            </button>
          </div>
        </form>

        {customProbeResult && (
          <div
            className={`mt-4 p-4 rounded-lg border text-xs ${
              customProbeResult.status === 'SUCCESS'
                ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900'
                : 'bg-red-50/70 border-red-200 text-red-900'
            }`}
          >
            <div className="flex items-center justify-between font-semibold text-sm">
              <span className="flex items-center gap-2">
                {customProbeResult.status === 'SUCCESS' ? (
                  <CheckCircle className="w-5 h-5 text-emerald-600" />
                ) : (
                  <XCircle className="w-5 h-5 text-red-600" />
                )}
                Probe Result: {customProbeResult.status}
              </span>
              <span className="font-mono text-xs opacity-80">{customProbeResult.latency_ms} ms</span>
            </div>

            {customProbeResult.error_message && (
              <p className="mt-2 text-red-700 font-mono">{customProbeResult.error_message}</p>
            )}

            {customProbeResult.tools && customProbeResult.tools.length > 0 ? (
              <div className="mt-3">
                <span className="text-xs font-semibold text-emerald-900">
                  Discovered MCP Tools ({customProbeResult.tools.length}):
                </span>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
                  {customProbeResult.tools.map((tool, idx) => (
                    <div key={idx} className="p-2.5 bg-white border border-emerald-200 rounded-md shadow-2xs">
                      <div className="font-mono font-bold text-emerald-800">{tool.name}</div>
                      {tool.description && (
                        <p className="text-[11px] text-charcoal-600 mt-0.5">{tool.description}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : customProbeResult.status === 'SUCCESS' ? (
              <p className="mt-2 text-emerald-800 text-[11px]">
                Server responded with 200 OK, but exposed 0 tools in tools/list.
              </p>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
};
