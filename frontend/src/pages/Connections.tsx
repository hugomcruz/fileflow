import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import api from '../services/api';
import { Connection } from '../types';
import { Cloud, CheckCircle, RefreshCw, Trash2, ExternalLink, Info, Plus, X, Pencil, Check } from 'lucide-react';

const BACKEND = '';

interface ProviderInfo {
  key: 'onedrive' | 'dropbox' | 'googledrive';
  label: string;
  description: string;
  color: string;
  connectPath: string;
}

const PROVIDERS: ProviderInfo[] = [
  {
    key: 'onedrive',
    label: 'Microsoft OneDrive',
    description: 'Personal or work OneDrive storage.',
    color: 'from-sky-500 to-blue-600',
    connectPath: '/api/auth/onedrive/connect',
  },
  {
    key: 'dropbox',
    label: 'Dropbox',
    description: 'Dropbox personal or team account.',
    color: 'from-indigo-500 to-violet-600',
    connectPath: '/api/auth/dropbox/connect',
  },
  {
    key: 'googledrive',
    label: 'Google Drive',
    description: 'Google Drive personal or Workspace account.',
    color: 'from-red-500 to-orange-500',
    connectPath: '/api/auth/googledrive/connect',
  },
];

function AddConnectionModal({
  onClose,
  onConfirm,
}: {
  onClose: () => void;
  onConfirm: (provider: ProviderInfo, displayName: string) => void;
}) {
  const [name, setName] = useState('');
  const [selectedKey, setSelectedKey] = useState<ProviderInfo['key'] | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  const selectedProvider = PROVIDERS.find((p) => p.key === selectedKey) ?? null;

  const handleConfirm = () => {
    if (!selectedProvider) return;
    onConfirm(selectedProvider, name.trim());
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="card w-full max-w-md p-6 space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-slate-900">Add Storage Account</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Name */}
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-slate-700">Account name</label>
          <input
            ref={nameRef}
            type="text"
            className="input w-full"
            placeholder='e.g. "Personal" or "Work"'
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleConfirm()}
          />
          <p className="text-xs text-slate-400">Give this connection a label so you can tell it apart from others.</p>
        </div>

        {/* Provider choice */}
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-slate-700">Connection type</label>
          <div className="space-y-2">
            {PROVIDERS.map((p) => (
              <button
                key={p.key}
                type="button"
                onClick={() => setSelectedKey(p.key)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl border-2 text-left transition-colors ${
                  selectedKey === p.key
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-slate-200 hover:border-slate-300 bg-white'
                }`}
              >
                <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${p.color} flex items-center justify-center flex-shrink-0`}>
                  <Cloud className="w-4 h-4 text-white" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium ${selectedKey === p.key ? 'text-primary-700' : 'text-slate-800'}`}>
                    {p.label}
                  </p>
                  <p className="text-xs text-slate-400">{p.description}</p>
                </div>
                <div className={`w-4 h-4 rounded-full border-2 flex-shrink-0 ${
                  selectedKey === p.key ? 'border-primary-500 bg-primary-500' : 'border-slate-300'
                }`} />
              </button>
            ))}
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2 justify-end pt-1">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            disabled={!selectedProvider}
            onClick={handleConfirm}
          >
            Authorise
            <ExternalLink className="w-3 h-3 opacity-70" />
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Connections() {
  const [params] = useSearchParams();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [reauthenticating, setReauthenticating] = useState<string | null>(null);
  const [toast, setToast] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');

  const load = () => {
    api.get<Connection[]>('/connections/')
      .then((r) => setConnections(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    const success = params.get('success');
    const error = params.get('error');
    if (success) {
      const label = PROVIDERS.find((p) => p.key === success)?.label ?? success;
      setToast(`✅ ${label} connected successfully!`);
    }
    if (error) setToast('❌ Failed to connect. Please try again.');
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(''), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const handleConnect = (provider: ProviderInfo, displayName: string) => {
    const token = localStorage.getItem('ff_token');
    const nameParam = displayName ? `&display_name=${encodeURIComponent(displayName)}` : '';
    window.location.href = `${BACKEND}${provider.connectPath}?_auth=${token}${nameParam}`;
  };

  const handleReauthenticate = (conn: Connection) => {
    const provider = PROVIDERS.find((p) => p.key === conn.provider);
    if (!provider) return;
    setReauthenticating(conn.id);
    const token = localStorage.getItem('ff_token');
    const nameParam = conn.displayName ? `&display_name=${encodeURIComponent(conn.displayName)}` : '';
    const idParam = `&connection_id=${encodeURIComponent(conn.id)}`;
    window.location.href = `${BACKEND}${provider.connectPath}?_auth=${token}${nameParam}${idParam}`;
  };

  const handleDelete = async (conn: Connection) => {
    const label = conn.displayName ?? PROVIDERS.find((p) => p.key === conn.provider)?.label ?? conn.provider;
    if (!confirm(`Delete "${label}"? This cannot be undone.`)) return;
    setDeleting(conn.id);
    try {
      await api.delete(`/connections/${conn.id}`);
      load();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setToast(`❌ ${detail ?? 'Failed to delete connection. Please try again.'}`);
    } finally {
      setDeleting(null);
    }
  };

  const startEdit = (conn: Connection) => {
    setEditingId(conn.id);
    setEditingName(conn.displayName ?? '');
  };

  const saveEdit = async (conn: Connection) => {
    if (editingName.trim() === (conn.displayName ?? '')) {
      setEditingId(null);
      return;
    }
    try {
      await api.patch(`/connections/${conn.id}`, { display_name: editingName.trim() });
      load();
    } catch {
      setToast('❌ Failed to rename connection.');
    } finally {
      setEditingId(null);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Page header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Storage Connections</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Connect your cloud storage accounts to use as sources or targets in your rules.
          </p>
        </div>
        <button className="btn-primary whitespace-nowrap" onClick={() => setShowModal(true)}>
          <Plus className="w-4 h-4" />
          Add Account
        </button>
      </div>

      {/* Toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 card px-5 py-3 shadow-lg text-sm font-medium text-slate-800 border-l-4 border-primary-500">
          {toast}
        </div>
      )}

      {/* Info banner */}
      <div className="flex gap-3 px-4 py-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-sm">
        <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
        <p>
          Connecting requires authorising FileFlow to access your files.
          Only folders specified in your rules will be accessed.
        </p>
      </div>

      {/* Connections list */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => <div key={i} className="h-16 bg-slate-100 animate-pulse rounded-xl" />)}
        </div>
      ) : connections.length === 0 ? (
        <div className="card p-10 text-center text-slate-400 space-y-2">
          <Cloud className="w-10 h-10 mx-auto opacity-30" />
          <p className="text-sm">No accounts connected yet. Click <strong>Add Account</strong> to get started.</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {connections.map((conn) => {
            const provider = PROVIDERS.find((p) => p.key === conn.provider);
            return (
              <li key={conn.id} className="card flex items-center gap-4 px-5 py-4">
                <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${provider?.color ?? 'from-slate-400 to-slate-500'} flex items-center justify-center flex-shrink-0`}>
                  <Cloud className="w-5 h-5 text-white" />
                </div>
                <div className="flex-1 min-w-0">
                  {editingId === conn.id ? (
                    <div className="flex items-center gap-2">
                      <input
                        autoFocus
                        className="input py-1 text-sm font-semibold w-48"
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveEdit(conn);
                          if (e.key === 'Escape') setEditingId(null);
                        }}
                      />
                      <button onClick={() => saveEdit(conn)} className="text-emerald-600 hover:text-emerald-700">
                        <Check className="w-4 h-4" />
                      </button>
                      <button onClick={() => setEditingId(null)} className="text-slate-400 hover:text-slate-600">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-slate-900 truncate">
                        {conn.displayName ?? provider?.label ?? conn.provider}
                      </p>
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
                      <button onClick={() => startEdit(conn)} className="text-slate-300 hover:text-slate-500 ml-0.5">
                        <Pencil className="w-3 h-3" />
                      </button>
                    </div>
                  )}
                  <p className="text-xs text-slate-400">
                    {provider?.label}
                    {' · '}Updated {new Date(conn.updatedAt).toLocaleString()}
                    {conn.expiresAt && ` · expires ${new Date(conn.expiresAt).toLocaleDateString()}`}
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    className="btn-secondary text-xs whitespace-nowrap"
                    onClick={() => handleReauthenticate(conn)}
                    disabled={reauthenticating === conn.id}
                    title="Re-authorise this connection"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${reauthenticating === conn.id ? 'animate-spin' : ''}`} />
                    Reauthenticate
                  </button>
                  <button
                    className="btn-secondary text-red-600 hover:bg-red-50 hover:border-red-200 text-xs whitespace-nowrap"
                    onClick={() => handleDelete(conn)}
                    disabled={deleting === conn.id}
                    title="Delete this connection"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    {deleting === conn.id ? 'Deleting…' : 'Delete'}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {showModal && (
        <AddConnectionModal
          onClose={() => setShowModal(false)}
          onConfirm={(provider, displayName) => {
            setShowModal(false);
            handleConnect(provider, displayName);
          }}
        />
      )}
    </div>
  );
}
