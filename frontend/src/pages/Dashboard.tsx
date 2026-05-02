import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { Rule, Job, Connection } from '../types';
import {
  Activity, CheckCircle, Clock, Plus, TrendingUp, Zap, ArrowRight, AlertCircle, Link2,
} from 'lucide-react';

interface Stats {
  totalRules: number;
  activeRules: number;
  totalJobs: number;
  successRate: number;
  connections: number;
}

function StatCard({
  label, value, icon: Icon, color,
}: { label: string; value: string | number; icon: React.ElementType; color: string }) {
  return (
    <div className="card p-5 flex items-center gap-4">
      <div className={`flex items-center justify-center w-12 h-12 rounded-xl ${color}`}>
        <Icon className="w-6 h-6 text-white" />
      </div>
      <div>
        <p className="text-2xl font-bold text-slate-900">{value}</p>
        <p className="text-sm text-slate-500">{label}</p>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const [rules, setRules] = useState<Rule[]>([]);
  const [recentJobs, setRecentJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<Stats>({ totalRules: 0, activeRules: 0, totalJobs: 0, successRate: 0, connections: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get<Rule[]>('/rules/'),
      api.get<{ jobs: Job[]; total: number }>('/jobs/?limit=5'),
      api.get<Connection[]>('/connections/'),
    ])
      .then(([rulesRes, jobsRes, connRes]) => {
        const r = rulesRes.data;
        const j = jobsRes.data.jobs;
        setRules(r);
        setRecentJobs(j);
        const completed = j.filter((x) => x.status === 'completed').length;
        setStats({
          totalRules: r.length,
          activeRules: r.filter((x) => x.enabled).length,
          totalJobs: jobsRes.data.total,
          successRate: j.length ? Math.round((completed / j.length) * 100) : 0,
          connections: connRes.data.length,
        });
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const firstName = user?.name?.split(' ')[0] ?? 'there';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Good morning, {firstName} 👋</h1>
          <p className="text-slate-500 text-sm mt-0.5">Here's what's happening with your files today.</p>
        </div>
        <Link to="/rules/new" className="btn-primary">
          <Plus className="w-4 h-4" />
          New Rule
        </Link>
      </div>

      {/* Stats */}
      {loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="card p-5 h-24 animate-pulse bg-slate-100" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Connections"   value={stats.connections} icon={Link2}       color="bg-sky-500" />
          <StatCard label="Total Rules"   value={stats.totalRules}  icon={Zap}         color="bg-primary-500" />
          <StatCard label="Active Rules"  value={stats.activeRules} icon={CheckCircle} color="bg-emerald-500" />
          <StatCard label="Success Rate"  value={`${stats.successRate}%`} icon={TrendingUp} color="bg-violet-500" />
        </div>
      )}

      {/* Recent Activity + Quick actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Jobs */}
        <div className="lg:col-span-2 card">
          <div className="flex items-center justify-between p-5 border-b border-slate-100">
            <h2 className="font-semibold text-slate-800">Recent Activity</h2>
            <Link to="/history" className="text-primary-600 text-sm hover:underline flex items-center gap-1">
              View all <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          <div className="divide-y divide-slate-50">
            {recentJobs.length === 0 && (
              <div className="p-8 text-center text-slate-400 text-sm">
                No jobs yet. Create a rule to get started.
              </div>
            )}
            {recentJobs.map((job) => (
              <div key={job.id} className="flex items-center gap-3 px-5 py-3.5">
                <JobStatusIcon status={job.status} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800 truncate">
                    {job.rule?.name ?? 'Unknown Rule'}
                  </p>
                  <p className="text-xs text-slate-400">
                    {job.filesProcessed} file{job.filesProcessed !== 1 ? 's' : ''} processed
                    {' · '}
                    {new Date(job.startedAt).toLocaleString()}
                  </p>
                </div>
                <JobStatusBadge status={job.status} />
              </div>
            ))}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="card p-5">
          <h2 className="font-semibold text-slate-800 mb-4">Quick Actions</h2>
          <div className="space-y-2">
            <Link to="/rules/new"
              className="flex items-center gap-3 p-3 rounded-lg hover:bg-primary-50 text-slate-700 hover:text-primary-700 transition-colors group">
              <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary-100 group-hover:bg-primary-200 transition-colors">
                <Plus className="w-4 h-4 text-primary-600" />
              </span>
              <span className="text-sm font-medium">Create Rule</span>
            </Link>
            <Link to="/connections"
              className="flex items-center gap-3 p-3 rounded-lg hover:bg-sky-50 text-slate-700 hover:text-sky-700 transition-colors group">
              <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-sky-100 group-hover:bg-sky-200 transition-colors">
                <Activity className="w-4 h-4 text-sky-600" />
              </span>
              <span className="text-sm font-medium">Manage Connections</span>
            </Link>
            <Link to="/history"
              className="flex items-center gap-3 p-3 rounded-lg hover:bg-violet-50 text-slate-700 hover:text-violet-700 transition-colors group">
              <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-violet-100 group-hover:bg-violet-200 transition-colors">
                <Clock className="w-4 h-4 text-violet-600" />
              </span>
              <span className="text-sm font-medium">View History</span>
            </Link>
          </div>

          {/* Active rules list */}
          {rules.length > 0 && (
            <>
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mt-6 mb-2">Active Rules</h3>
              <div className="space-y-1">
                {rules.filter((r) => r.enabled).slice(0, 5).map((rule) => (
                  <Link key={rule.id} to="/rules"
                    className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-slate-50 text-slate-600 hover:text-slate-900 text-sm">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0" />
                    <span className="truncate">{rule.name}</span>
                  </Link>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function JobStatusIcon({ status }: { status: string }) {
  if (status === 'completed') return <CheckCircle className="w-5 h-5 text-emerald-500 flex-shrink-0" />;
  if (status === 'failed')    return <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />;
  if (status === 'running')   return <div className="w-5 h-5 border-2 border-sky-500 border-t-transparent rounded-full animate-spin flex-shrink-0" />;
  return <Clock className="w-5 h-5 text-slate-400 flex-shrink-0" />;
}

function JobStatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: 'badge bg-emerald-100 text-emerald-700',
    failed:    'badge bg-red-100 text-red-700',
    running:   'badge bg-sky-100 text-sky-700',
    pending:   'badge bg-slate-100 text-slate-600',
  };
  return <span className={map[status] ?? 'badge bg-slate-100 text-slate-600'}>{status}</span>;
}
