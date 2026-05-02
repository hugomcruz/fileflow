import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import api from '../services/api';
import { SCHEDULE_OPTIONS } from '../types';
import type { Rule, Connection } from '../types';
import { ChevronLeft, ChevronRight, Check, Cloud, Image, Video, Calendar, Layers, Filter, Trash2, ChevronDown } from 'lucide-react';

function TemplateVarsHint() {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button type="button" onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-xs text-primary-600 hover:underline">
        <ChevronDown className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`} />
        Available template variables
      </button>
      {open && (
        <div className="mt-2 p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-600 space-y-3">
          <div>
            <p className="font-semibold text-slate-700 mb-1">📅 EXIF capture date (falls back to file date)</p>
            <div className="flex flex-wrap gap-1">
              {['{year}','{month}','{day}','{hour}','{minute}','{seconds}','{date}','{time}'].map(v => (
                <code key={v} className="bg-white border border-slate-200 px-1.5 py-0.5 rounded">{v}</code>
              ))}
            </div>
          </div>
          <div>
            <p className="font-semibold text-slate-700 mb-1">🗂 File creation date</p>
            <div className="flex flex-wrap gap-1">
              {['{fileyear}','{filemonth}','{fileday}','{filehour}','{fileminute}','{fileseconds}','{filedate}','{filetime}'].map(v => (
                <code key={v} className="bg-white border border-slate-200 px-1.5 py-0.5 rounded">{v}</code>
              ))}
            </div>
          </div>
          <div>
            <p className="font-semibold text-slate-700 mb-1">🏷 Media type &amp; filename</p>
            <div className="flex flex-wrap gap-1">
              {['{type}','{name}','{originalname}','{originalstem}','{ext}'].map(v => (
                <code key={v} className="bg-white border border-slate-200 px-1.5 py-0.5 rounded">{v}</code>
              ))}
            </div>
            <p className="mt-1.5 text-slate-400">
              <code>{'{type}'}</code>: <em>photo</em>, <em>screenshot</em>, or <em>video</em>. &nbsp;
              <code>{'{name}'}</code>: auto-generated canonical name.
              Include a filename variable to set a custom filename; otherwise the folder path is used and the name is appended automatically.
            </p>
          </div>
          <p className="text-slate-400 italic">Example: <code>/Photos/{'{year}'}/{'{month}'}/{'{day}'}/</code> &nbsp;or&nbsp; <code>/Media/{'{type}'}/{'{year}'}/{'{originalname}'}</code></p>
        </div>
      )}
    </div>
  );
}

interface FormData {
  name: string;
  sourceConnectionId: string;
  sourceProvider: string;
  sourcePath: string;
  fileTypes: string[];
  filePattern: string;
  targetConnectionId: string;
  targetProvider: string;
  targetPath: string;
  schedule: string;
  deleteSource: boolean;
  recursive: boolean;
}

const STEPS = ['Basics', 'Source', 'Files', 'Pattern', 'Target', 'Schedule'];

export default function EditRule() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [connections, setConnections] = useState<Connection[]>([]);

  const [form, setForm] = useState<FormData>({
    name: '',
    sourceConnectionId: '',
    sourceProvider: '',
    sourcePath: '',
    fileTypes: ['photos'],
    filePattern: '',
    targetConnectionId: '',
    targetProvider: '',
    targetPath: '',
    schedule: '0 * * * *',
    deleteSource: false,
    recursive: false,
  });

  useEffect(() => {
    api.get<Connection[]>('/connections/').then((r) => setConnections(r.data)).catch(console.error);
  }, []);

  useEffect(() => {
    api.get<Rule>(`/rules/${id}`).then((res) => {
      const r = res.data;
      setForm({
        name: r.name,
        sourceConnectionId: r.sourceConnectionId ?? '',
        sourceProvider: r.sourceProvider,
        sourcePath: r.sourcePath,
        fileTypes: r.fileTypes,
        filePattern: r.filePattern ?? '',
        targetConnectionId: r.targetConnectionId ?? '',
        targetProvider: r.targetProvider,
        targetPath: r.targetPath,
        schedule: r.schedule,
        deleteSource: r.deleteSource,
        recursive: r.recursive ?? false,
      });
      setLoading(false);
    }).catch(() => {
      setError('Failed to load rule.');
      setLoading(false);
    });
  }, [id]);

  const set = <K extends keyof FormData>(key: K, val: FormData[K]) =>
    setForm((f) => ({ ...f, [key]: val }));

  const pickConnection = (side: 'source' | 'target', conn: Connection) => {
    if (side === 'source') {
      setForm((f) => ({ ...f, sourceConnectionId: conn.id, sourceProvider: conn.provider }));
    } else {
      setForm((f) => ({ ...f, targetConnectionId: conn.id, targetProvider: conn.provider }));
    }
  };

  const toggleFileType = (type: string) => {
    setForm((f) => ({
      ...f,
      fileTypes: f.fileTypes.includes(type)
        ? f.fileTypes.filter((t) => t !== type)
        : [...f.fileTypes, type],
    }));
  };

  const canNext = (): boolean => {
    if (step === 0) return form.name.trim().length > 0;
    if (step === 1) return form.sourceConnectionId.length > 0 && form.sourcePath.trim().length > 0;
    if (step === 2) return form.fileTypes.length > 0;
    if (step === 3) return true;
    if (step === 4) return form.targetConnectionId.length > 0 && form.targetPath.trim().length > 0;
    return true;
  };

  const handleSubmit = async () => {
    setSaving(true);
    setError('');
    try {
      await api.put(`/rules/${id}`, {
        name: form.name,
        source_provider: form.sourceProvider,
        source_connection_id: form.sourceConnectionId,
        source_path: form.sourcePath,
        file_types: form.fileTypes,
        file_pattern: form.filePattern || null,
        target_provider: form.targetProvider,
        target_connection_id: form.targetConnectionId,
        target_path: form.targetPath,
        schedule: form.schedule,
        delete_source: form.deleteSource,
        recursive: form.recursive,
      });
      navigate('/rules');
    } catch {
      setError('Failed to save rule. Please try again.');
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-slate-400">
        Loading…
      </div>
    );
  }

  return (
    <div className="max-w-xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Edit Processing Rule</h1>
        <p className="text-slate-500 text-sm mt-0.5">Update source, processing type, and destination.</p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-0">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold border-2 transition-colors ${
                i < step ? 'bg-primary-600 border-primary-600 text-white'
                  : i === step ? 'border-primary-600 text-primary-600'
                  : 'border-slate-300 text-slate-400'
              }`}>
                {i < step ? <Check className="w-4 h-4" /> : i + 1}
              </div>
              <span className={`text-xs mt-1 font-medium ${i === step ? 'text-primary-600' : 'text-slate-400'}`}>
                {label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`flex-1 h-0.5 mx-1 mt-[-14px] ${i < step ? 'bg-primary-600' : 'bg-slate-200'}`} />
            )}
          </div>
        ))}
      </div>

      {/* Step content */}
      <div className="card p-6 min-h-[240px] flex flex-col gap-5">
        {step === 0 && (
          <div>
            <label className="label">Rule Name</label>
            <input
              className="input"
              placeholder="e.g. Organise iPhone photos to Dropbox"
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              autoFocus
            />
            <p className="text-xs text-slate-400 mt-1.5">A friendly name to identify this rule.</p>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <div>
              <label className="label">Source Connection</label>
              <ConnectionPicker
                connections={connections}
                selectedId={form.sourceConnectionId}
                onChange={(conn) => pickConnection('source', conn)}
              />
            </div>
            <div>
              <label className="label">Source Folder Path</label>
              <input
                className="input"
                placeholder="/Camera Uploads"
                value={form.sourcePath}
                onChange={(e) => set('sourcePath', e.target.value)}
              />
            </div>
            <label
              className={`flex items-center gap-3 p-3 rounded-xl border-2 cursor-pointer transition-colors select-none ${
                form.recursive ? 'border-primary-400 bg-primary-50' : 'border-slate-200 hover:border-slate-300'
              }`}
              onClick={() => set('recursive', !form.recursive)}
            >
              <div className={`w-5 h-5 rounded flex items-center justify-center border-2 flex-shrink-0 transition-colors ${
                form.recursive ? 'bg-primary-600 border-primary-600' : 'border-slate-300'
              }`}>
                {form.recursive && <Check className="w-3 h-3 text-white" />}
              </div>
              <div>
                <p className={`text-sm font-medium ${form.recursive ? 'text-primary-700' : 'text-slate-700'}`}>Process subfolders recursively</p>
                <p className="text-xs text-slate-400">Include files in all subdirectories of the source path.</p>
              </div>
            </label>
          </div>
        )}

        {step === 2 && (
          <div>
            <label className="label">File Types to Process</label>
            <div className="flex gap-3 mt-2">
              <TypeToggle
                label="Photos"
                icon={<Image className="w-5 h-5" />}
                active={form.fileTypes.includes('photos')}
                onClick={() => toggleFileType('photos')}
                desc="jpg, jpeg, png, heic, heif…"
              />
              <TypeToggle
                label="Videos"
                icon={<Video className="w-5 h-5" />}
                active={form.fileTypes.includes('videos')}
                onClick={() => toggleFileType('videos')}
                desc="mp4, mov, avi, mkv…"
              />
            </div>
            <p className="text-xs text-slate-500 mt-4">
              Files will be renamed using the embedded timestamp.
            </p>
          </div>
        )}

        {step === 3 && (
          <div>
            <label className="label">
              <Filter className="inline w-4 h-4 mr-1 -mt-0.5" />
              File Pattern <span className="text-slate-400 font-normal">(optional)</span>
            </label>
            <input
              className="input mt-1"
              placeholder="e.g. *.jpg, IMG_*.heic, *.mp4"
              value={form.filePattern}
              onChange={(e) => set('filePattern', e.target.value)}
            />
            <p className="text-xs text-slate-500 mt-2">
              Comma-separated glob patterns. Leave empty to process all matching file types.<br />
              Examples: <code className="bg-slate-100 px-1 rounded">*.jpg</code> &nbsp;
              <code className="bg-slate-100 px-1 rounded">IMG_*.heic, *.mp4</code>
            </p>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-4">
            <div>
              <label className="label">Target Connection</label>
              <ConnectionPicker
                connections={connections}
                selectedId={form.targetConnectionId}
                onChange={(conn) => pickConnection('target', conn)}
              />
            </div>
            <div>
              <label className="label">Target Folder Path</label>
              <input
                className="input"
                placeholder="/Organised  or  /Photos/{year}/{month}/{day}/"
                value={form.targetPath}
                onChange={(e) => set('targetPath', e.target.value)}
              />
              <TemplateVarsHint />
            </div>
          </div>
        )}

        {step === 5 && (
          <div className="space-y-5">
            <div>
              <label className="label">
                <Calendar className="inline w-4 h-4 mr-1 -mt-0.5" />
                Run Schedule
              </label>
              <div className="space-y-2 mt-1">
                {SCHEDULE_OPTIONS.map((opt) => (
                  <label key={opt.value} className="flex items-center gap-3 p-3 rounded-lg border border-slate-200 cursor-pointer hover:bg-slate-50 has-[:checked]:border-primary-400 has-[:checked]:bg-primary-50">
                    <input
                      type="radio"
                      name="schedule"
                      value={opt.value}
                      checked={form.schedule === opt.value}
                      onChange={() => set('schedule', opt.value)}
                      className="text-primary-600"
                    />
                    <span className="text-sm font-medium text-slate-700">{opt.label}</span>
                    <code className="ml-auto text-xs text-slate-400">{opt.value}</code>
                  </label>
                ))}
              </div>
            </div>

            <div
              onClick={() => set('deleteSource', !form.deleteSource)}
              className={`flex items-start gap-3 p-4 rounded-xl border-2 cursor-pointer transition-colors ${
                form.deleteSource ? 'border-red-400 bg-red-50' : 'border-slate-200 hover:border-slate-300'
              }`}
            >
              <Trash2 className={`w-5 h-5 mt-0.5 shrink-0 ${form.deleteSource ? 'text-red-500' : 'text-slate-400'}`} />
              <div className="flex-1">
                <p className={`text-sm font-medium ${form.deleteSource ? 'text-red-700' : 'text-slate-700'}`}>
                  Delete source files after transfer
                </p>
                <p className="text-xs text-slate-400 mt-0.5">
                  Files are only deleted once successfully written to the destination.
                  If a file already exists there with identical content, the source is deleted without re-uploading.
                </p>
              </div>
              <input type="checkbox" checked={form.deleteSource} readOnly className="mt-1 accent-red-500" />
            </div>
          </div>
        )}

        {error && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
            {error}
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <button
          className="btn-secondary"
          onClick={() => (step === 0 ? navigate('/rules') : setStep((s) => s - 1))}
        >
          <ChevronLeft className="w-4 h-4" />
          {step === 0 ? 'Cancel' : 'Back'}
        </button>

        {step < STEPS.length - 1 ? (
          <button
            className="btn-primary"
            onClick={() => setStep((s) => s + 1)}
            disabled={!canNext()}
          >
            Next
            <ChevronRight className="w-4 h-4" />
          </button>
        ) : (
          <button
            className="btn-primary"
            onClick={handleSubmit}
            disabled={saving || !canNext()}
          >
            {saving ? (
              <><span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />Saving…</>
            ) : (
              <><Layers className="w-4 h-4" />Save Rule</>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

function providerLabel(provider: string): string {
  if (provider === 'onedrive') return 'OneDrive';
  if (provider === 'dropbox') return 'Dropbox';
  if (provider === 'googledrive') return 'Google Drive';
  return provider;
}

function ConnectionPicker({
  connections,
  selectedId,
  onChange,
}: {
  connections: Connection[];
  selectedId: string;
  onChange: (conn: Connection) => void;
}) {
  if (connections.length === 0) {
    return (
      <p className="text-sm text-slate-400 mt-1">
        No connections found. <a href="/connections" className="text-primary-600 underline">Add one first.</a>
      </p>
    );
  }

  return (
    <div className="space-y-2 mt-1">
      {connections.map((conn) => (
        <button
          key={conn.id}
          type="button"
          onClick={() => onChange(conn)}
          className={`w-full flex items-center gap-3 p-3 rounded-xl border-2 text-sm font-medium transition-colors text-left ${
            selectedId === conn.id
              ? 'border-primary-500 bg-primary-50 text-primary-700'
              : 'border-slate-200 text-slate-600 hover:border-slate-300'
          }`}
        >
          <Cloud className="w-5 h-5 shrink-0" />
          <span className="flex-1">
            {conn.displayName
              ? <><span className="font-semibold">{conn.displayName}</span><span className="text-slate-400 font-normal ml-1">({providerLabel(conn.provider)})</span></>
              : providerLabel(conn.provider)
            }
          </span>
          {selectedId === conn.id && <Check className="w-4 h-4 shrink-0" />}
        </button>
      ))}
    </div>
  );
}

function TypeToggle({
  label, icon, active, onClick, desc,
}: { label: string; icon: React.ReactNode; active: boolean; onClick: () => void; desc: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 flex flex-col items-center gap-2 p-4 rounded-xl border-2 text-sm font-medium transition-colors ${
        active
          ? 'border-primary-500 bg-primary-50 text-primary-700'
          : 'border-slate-200 text-slate-500 hover:border-slate-300'
      }`}
    >
      {icon}
      {label}
      <span className="text-[10px] font-normal opacity-70">{desc}</span>
    </button>
  );
}
