# FileFlow ⚡

Automatically detect timestamps from photos & videos and rename/move them across **OneDrive** and **Dropbox** — on a schedule, for every user.

---

## Architecture

```
fileflow/
├── backend/          Node.js + Express + TypeScript + Prisma
└── frontend/         React + TypeScript + Vite + Tailwind CSS
```

### Key Features
- **Multi-tenant** – every user has isolated rules, connections, and job history
- **OAuth login** – Google and Microsoft accounts
- **Cloud storage** – OneDrive (Microsoft Graph) and Dropbox as both source and target
- **Processing** – EXIF timestamp for photos, `ffprobe` for videos → rename to `YYYY-MM-DD_HH-mm-ss_original.ext`
- **Scheduler** – per-rule `cron` expressions run in-process (`node-cron`)
- **History** – every job and every processed file is logged

---

## Quick Start

### Prerequisites

| Tool | Version |
|------|---------|
| Node.js | ≥ 20 |
| Docker + Compose | any recent |
| ffmpeg | system-installed (for video metadata) |

### 1. Start the database

```bash
docker compose up postgres -d
```

### 2. Backend setup

```bash
cd backend
cp .env.example .env          # fill in your OAuth credentials
npm install
npm run db:migrate            # apply Prisma migrations
npm run dev                   # starts on http://localhost:3001
```

### 3. Frontend setup

```bash
cd frontend
npm install
npm run dev                   # starts on http://localhost:5173
```

---

## OAuth Credential Setup

### Google (login)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services → Credentials**
2. Create an OAuth 2.0 Client ID (Web application)
3. Add `http://localhost:3001/api/auth/google/callback` as an authorised redirect URI
4. Copy **Client ID** and **Secret** into `backend/.env`

### Microsoft (login + OneDrive)

1. Go to [Azure Portal](https://portal.azure.com/) → **App registrations → New registration**
2. Add these redirect URIs:
   - `http://localhost:3001/api/auth/microsoft/callback`
   - `http://localhost:3001/api/auth/onedrive/callback`
3. Under **API permissions** add: `User.Read`, `Files.ReadWrite.All`, `offline_access`
4. Create a client secret and copy credentials into `backend/.env`

> **Tip:** You can use the same Azure app for both Microsoft login and OneDrive, or separate apps.

### Dropbox

1. Go to [Dropbox Developer Console](https://www.dropbox.com/developers/apps) → **Create app**
2. Choose **Scoped access → Full Dropbox**
3. Add `http://localhost:3001/api/auth/dropbox/callback` as a redirect URI
4. Enable permissions: `files.metadata.read`, `files.content.read`, `files.content.write`
5. Copy **App key** and **App secret** into `backend/.env`

---

## Processing Logic

```
Rule triggers (cron)
  → list files at source path (filter by extension)
  → for each file:
      download
      photos → exifr → DateTimeOriginal
      videos → ffprobe → creation_time
      fallback → file modification date
      rename → YYYY-MM-DD_HH-mm-ss_originalname.ext
      upload to target path
      log result
  → update rule.lastRunAt
```

---

## Production Checklist

- [ ] Replace in-memory OAuth state store with Redis
- [ ] Encrypt `accessToken` / `refreshToken` at rest
- [ ] Use `secure` + `httpOnly` cookies instead of `localStorage` for JWT
- [ ] Add token refresh logic before each API call
- [ ] Move scheduler to a dedicated worker process or BullMQ
- [ ] Add rate limiting / request validation middleware
- [ ] Configure proper CORS origin for production domain
- [ ] Use an upload session for OneDrive files > 4 MB
