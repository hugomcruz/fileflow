import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../services/api';
import { Rule } from '../types';
import {
  Plus, Play, Trash2, ToggleLeft, ToggleRight, Cloud, Clock, ArrowRight,
  Image, Video, Layers, Pencil,
} from 'lucide-react';

const PROVIDER_LABELS: Record<string, string> = {
  onedrive: 'OneDrive',
  dropbox:  'Dropbox',
};

const PROVIDER_COLORS: Record<string, string> = {
  onedrive: 'bg-sky-100 text-sky-700',
  dropbox:  'bg-indigo-100 text-indigo-700',
};

export default function Rules() {
  const navigate = useNavigate();
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set());

  const load = () => {
    api.get<Rule[]>('/rules/')
      .then((r) => setRules(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleToggle = async (rule: Rule) => {
    await api.post(`/rules/${rule.id}/toggle`);
    load();
  };

  const handleDelete = async (rule: Rule) => {
    if (!confirm(`Delete rule "${rule.name}"?`)) return;
    await api.delete(`/rules/${rule.id}`);
    load();
  };

  const handleRun = async (rule: Rule) => {
    setRunningIds((s) => new Set(s).add(rule.id));
    try {
      await api.post(`/rules/${rule.id}/run`);
    } finally {
      setRunningIds((s) => { const n = new Set(s); n.delete(rule.id); return n; });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Processing Rules</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Define how your files are renamed and organised.
          </p>
        </div>
        <Link to="/rules/new" className="btn-primary">
          <Plus className="w-4 h-4" />
          New Rule
        </Link>
      </div>

      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="card p-5 h-40 animate-pulse bg-slate-100" />
          ))}
        </div>
      )}

      {!loading && rules.length === 0 && (
        <div className="card p-12 flex flex-col items-center text-center">
          <div className="w-16 h-16 rounded-2xl bg-primary-50 flex items-center justify-center mb-4">
            <Layers className="w-8 h-8 text-primary-400" />
          </div>
          <h3 className="text-lg font-semibold text-slate-800">No rules yet</h3>
          <p className="text-slate-500 text-sm mt-1 max-w-xs">
            Create your first rule to start automatically organising your photos and videos.
          </p>
          <Link to="/rules/new" className="btn-primary mt-6">
            <Plus className="w-4 h-4" />
            Create First Rule
          </Link>
        </div>
      )}

      {!loading && rules.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {rules.map((rule) => (
            <RuleCard
              key={rule.id}
              rule={rule}
              isRunning={runningIds.has(rule.id)}
              onToggle={() => handleToggle(rule)}
              onDelete={() => handleDelete(rule)}
              onRun={() => handleRun(rule)}
              onEdit={() => navigate(`/rules/${rule.id}/edit`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function RuleCard({
  rule, isRunning, onToggle, onDelete, onRun, onEdit,
}: {
  rule: Rule;
  isRunning: boolean;
  onToggle: () => void;
  onDelete: () => void;
  onRun: () => void;
  onEdit: () => void;
}) {
  return (
    <div className={`card p-5 flex flex-col gap-4 transition-opacity ${!rule.enabled ? 'opacity-60' : ''}`}>
      {/* Title row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-slate-900 truncate">{rule.name}</h3>
          <div className="flex items-center gap-1 mt-1 text-xs text-slate-500">
            <Clock className="w-3 h-3" />
            {rule.lastRunAt
              ? `Last run ${new Date(rule.lastRunAt).toLocaleString()}`
              : 'Never run'}
          </div>
        </div>
        <button
          onClick={onToggle}
          className="flex-shrink-0 text-slate-400 hover:text-primary-600 transition-colors"
          title={rule.enabled ? 'Disable' : 'Enable'}
        >
          {rule.enabled
            ? <ToggleRight className="w-7 h-7 text-primary-600" />
            : <ToggleLeft className="w-7 h-7" />}
        </button>
      </div>

      {/* Source → Target */}
      <div className="flex items-center gap-2">
        <span className={`badge ${PROVIDER_COLORS[rule.sourceProvider]}`}>
          <Cloud className="w-3 h-3 mr-1" />
          {PROVIDER_LABELS[rule.sourceProvider]}
        </span>
        <ArrowRight className="w-4 h-4 text-slate-400 flex-shrink-0" />
        <span className={`badge ${PROVIDER_COLORS[rule.targetProvider]}`}>
          <Cloud className="w-3 h-3 mr-1" />
          {PROVIDER_LABELS[rule.targetProvider]}
        </span>
        <span className="ml-auto flex gap-1">
          {rule.fileTypes.includes('photos') && (
            <span className="badge bg-amber-100 text-amber-700">
              <Image className="w-3 h-3 mr-1" />Photos
            </span>
          )}
          {rule.fileTypes.includes('videos') && (
            <span className="badge bg-rose-100 text-rose-700">
              <Video className="w-3 h-3 mr-1" />Videos
            </span>
          )}
        </span>
      </div>

      {/* Paths */}
      <div className="text-xs text-slate-500 space-y-0.5">
        <div><span className="font-medium">Source:</span> {rule.sourcePath}</div>
        <div><span className="font-medium">Target:</span> {rule.targetPath}</div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-1 border-t border-slate-100">
        <button
          onClick={onRun}
          disabled={isRunning}
          className="btn-secondary text-xs px-3 py-1.5 flex-1 justify-center"
        >
          {isRunning
            ? <><span className="w-3 h-3 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />Running…</>
            : <><Play className="w-3 h-3" />Run Now</>}
        </button>
        <button
          onClick={onEdit}
          className="p-2 rounded-lg text-slate-400 hover:text-primary-600 hover:bg-primary-50 transition-colors"
          title="Edit rule"
        >
          <Pencil className="w-4 h-4" />
        </button>
        <button
          onClick={onDelete}
          className="p-2 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors"
          title="Delete rule"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
