import { useEffect, useState } from 'react';
import api from '../services/api';
import { Job, JobsResponse, ProcessingLog } from '../types';
import {
  CheckCircle, AlertCircle, Clock, Loader, ChevronDown, ChevronUp, Filter, RefreshCw,
} from 'lucide-react';

const STATUS_STYLES: Record<string, string> = {
  completed: 'bg-emerald-100 text-emerald-700',
  failed:    'bg-red-100 text-red-700',
  running:   'bg-sky-100 text-sky-700',
  pending:   'bg-slate-100 text-slate-600',
};

function duration(job: Job): string {
  if (!job.completedAt) return '—';
  const ms = new Date(job.completedAt).getTime() - new Date(job.startedAt).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
}

export default function History() {
  const [data, setData] = useState<JobsResponse | null>(null);
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [expandedLogs, setExpandedLogs] = useState<ProcessingLog[]>([]);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [filter, setFilter] = useState('all');
  const [refreshing, setRefreshing] = useState(false);

  const fetchJobs = (p: number) => {
    setRefreshing(true);
    api.get<JobsResponse>(`/jobs/?page=${p}&limit=15`)
      .then((r) => setData(r.data))
      .catch(console.error)
      .finally(() => setRefreshing(false));
  };

  useEffect(() => {
    fetchJobs(page);
  }, [page]);

  const toggleExpand = async (jobId: string) => {
    if (expanded === jobId) {
      setExpanded(null);
      return;
    }
    setExpanded(jobId);
    setLoadingLogs(true);
    try {
      const res = await api.get<Job>(`/jobs/${jobId}`);
      setExpandedLogs(res.data.logs ?? []);
    } catch {
      setExpandedLogs([]);
    } finally {
      setLoadingLogs(false);
    }
  };

  const filtered = data?.jobs.filter((j) => filter === 'all' || j.status === filter) ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Processing History</h1>
          <p className="text-slate-500 text-sm mt-0.5">Review past runs and their results.</p>
        </div>

        <div className="flex items-center gap-2">
          <button
            className="btn-secondary py-1.5 px-3 flex items-center gap-1.5"
            onClick={() => fetchJobs(page)}
            disabled={refreshing}
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <Filter className="w-4 h-4 text-slate-400" />
          <select
            className="input py-1.5 w-36"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">All statuses</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="running">Running</option>
            <option value="pending">Pending</option>
          </select>
        </div>
      </div>

      {!data && (
        <div className="flex items-center justify-center h-40 text-slate-400">
          <Loader className="w-6 h-6 animate-spin" />
        </div>
      )}

      {data && filtered.length === 0 && (
        <div className="card p-10 text-center text-slate-400 text-sm">
          No jobs found.
        </div>
      )}

      {data && filtered.length > 0 && (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Rule</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Status</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Files</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide hidden md:table-cell">Started</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide hidden md:table-cell">Duration</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((job) => (
                <>
                  <tr
                    key={job.id}
                    className="hover:bg-slate-50 cursor-pointer transition-colors"
                    onClick={() => toggleExpand(job.id)}
                  >
                    <td className="px-4 py-3 font-medium text-slate-800">
                      {job.rule?.name ?? 'Deleted Rule'}
                      {job.errorMessage && (
                        <p className="text-xs text-red-500 font-normal mt-0.5 truncate max-w-xs">{job.errorMessage}</p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`badge ${STATUS_STYLES[job.status] ?? ''}`}>
                        <StatusIcon status={job.status} />
                        {job.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-slate-600">
                      <span className="text-emerald-600">{job.filesProcessed}</span>
                      {job.filesErrored > 0 && <span className="text-red-500"> / {job.filesErrored} err</span>}
                    </td>
                    <td className="px-4 py-3 text-slate-500 hidden md:table-cell">
                      {new Date(job.startedAt).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right text-slate-500 hidden md:table-cell tabular-nums">
                      {duration(job)}
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {expanded === job.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </td>
                  </tr>

                  {/* Expanded log rows */}
                  {expanded === job.id && (
                    <tr key={`${job.id}-detail`} className="bg-slate-50">
                      <td colSpan={6} className="px-4 py-4">
                        {loadingLogs ? (
                          <div className="flex justify-center py-4 text-slate-400">
                            <Loader className="w-5 h-5 animate-spin" />
                          </div>
                        ) : expandedLogs.length === 0 ? (
                          <p className="text-slate-400 text-sm text-center py-2">No file logs available.</p>
                        ) : (
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-slate-500">
                                <th className="text-left pb-1 font-medium">Source file</th>
                                <th className="text-left pb-1 font-medium">Destination</th>
                                <th className="text-left pb-1 font-medium">Connections</th>
                                <th className="text-left pb-1 font-medium">Status</th>
                                <th className="text-left pb-1 font-medium hidden sm:table-cell">Message</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200">
                              {expandedLogs.map((log) => (
                                <tr key={log.id} className="align-top">
                                  <td className="py-1.5 pr-4 max-w-[160px]">
                                    <p className="font-mono text-slate-700 truncate" title={log.sourcePath ?? log.originalName}>{log.originalName}</p>
                                    {log.sourcePath && (
                                      <p className="text-slate-400 truncate text-[10px]" title={log.sourcePath}>{log.sourcePath}</p>
                                    )}
                                  </td>
                                  <td className="py-1.5 pr-4 max-w-[160px]">
                                    {log.targetPath ? (
                                      <>
                                        <p className="font-mono text-slate-600 truncate" title={log.targetPath}>{log.newName ?? '—'}</p>
                                        <p className="text-slate-400 truncate text-[10px]" title={log.targetPath}>{log.targetPath}</p>
                                      </>
                                    ) : (
                                      <span className="text-slate-400">—</span>
                                    )}
                                  </td>
                                  <td className="py-1.5 pr-4 text-slate-500 text-[10px] max-w-[140px]">
                                    {log.sourceConnection && <p className="truncate" title={log.sourceConnection}>↑ {log.sourceConnection}</p>}
                                    {log.targetConnection && <p className="truncate" title={log.targetConnection}>↓ {log.targetConnection}</p>}
                                  </td>
                                  <td className="py-1.5 pr-4">
                                    <span className={`badge text-[10px] ${STATUS_STYLES[log.status] ?? ''}`}>{log.status}</span>
                                  </td>
                                  <td className="py-1.5 text-slate-400 hidden sm:table-cell">{log.message ?? ''}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button className="btn-secondary py-1.5 px-3" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
            Previous
          </button>
          <span className="text-sm text-slate-500">{page} / {data.pages}</span>
          <button className="btn-secondary py-1.5 px-3" onClick={() => setPage((p) => Math.min(data.pages, p + 1))} disabled={page === data.pages}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'completed') return <CheckCircle className="w-3 h-3 mr-1" />;
  if (status === 'failed')    return <AlertCircle className="w-3 h-3 mr-1" />;
  if (status === 'running')   return <Loader className="w-3 h-3 mr-1 animate-spin" />;
  return <Clock className="w-3 h-3 mr-1" />;
}
