export interface User {
  id: string;
  email: string;
  name: string | null;
  avatar: string | null;
  provider: string;
  connections: Connection[];
  _count: { rules: number };
}

export interface Connection {
  id: string;
  provider: 'onedrive' | 'dropbox' | 'googledrive';
  displayName: string | null;
  scope: string | null;
  expiresAt: string | null;
  updatedAt: string;
}

export interface Rule {
  id: string;
  name: string;
  sourceProvider: 'onedrive' | 'dropbox' | 'googledrive';
  sourceConnectionId: string | null;
  sourcePath: string;
  fileTypes: string[];
  filePattern: string | null;
  targetProvider: 'onedrive' | 'dropbox' | 'googledrive';
  targetConnectionId: string | null;
  targetPath: string;
  schedule: string;
  enabled: boolean;
  deleteSource: boolean;
  recursive: boolean;
  lastRunAt: string | null;
  createdAt: string;
  _count?: { jobs: number };
  jobs?: { status: string; startedAt: string; filesProcessed: number }[];
}

export interface Job {
  id: string;
  ruleId: string;
  userId: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  filesProcessed: number;
  filesSkipped: number;
  filesErrored: number;
  startedAt: string;
  completedAt: string | null;
  errorMessage: string | null;
  rule?: { name: string; sourceProvider: string; targetProvider: string };
  logs?: ProcessingLog[];
}

export interface ProcessingLog {
  id: string;
  originalName: string;
  newName: string | null;
  sourcePath: string | null;
  targetPath: string | null;
  sourceConnection: string | null;
  targetConnection: string | null;
  status: 'success' | 'skipped' | 'error';
  message: string | null;
  processedAt: string;
}

export interface JobsResponse {
  jobs: Job[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

export type StorageProvider = 'onedrive' | 'dropbox';
export type FileType = 'photos' | 'videos' | 'both';

export const SCHEDULE_OPTIONS = [
  { label: 'Every hour',     value: '0 * * * *' },
  { label: 'Every 6 hours',  value: '0 */6 * * *' },
  { label: 'Every 12 hours', value: '0 */12 * * *' },
  { label: 'Daily (midnight)',value: '0 0 * * *' },
  { label: 'Weekly (Monday)',value: '0 0 * * 1' },
];
