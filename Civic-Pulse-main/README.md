<div align="center">

# 🏛️ Civic Pulse
### Digital Governance, Autonomous Public Service & Multimodal Fact-Verification Platform

[![React 18](https://img.shields.io/badge/Frontend-React_18_%2B_Vite_5-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI_%2B_Python_3.11-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL_16_(pgvector_%2B_PostGIS)-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Playwright](https://img.shields.io/badge/Automation-Playwright_%2B_WebSockets-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)](https://playwright.dev/)

**Civic Pulse** is a unified civic-tech platform designed to democratize public information, modernize municipal service delivery, automate legacy e-governance workflows, and combat synthetic misinformation.

[Quick Start](#-quick-start-docker--local-setup) • [Core Pillars](#-the-4-core-pillars) • [How to Use](#-how-to-use-civic-pulse-step-by-step-walkthrough) • [API Reference](#-api--websocket-quick-reference) • [Team Workflow](#-3-person-parallel-development-workflow)

</div>

---

## 🌟 The 4 Core Pillars

| Pillar | Problem Solved | Key Capabilities |
| :--- | :--- | :--- |
| **1. Multilingual Policy & Voice Explainer** | Government gazettes and welfare schemes are published as dense, unreadable legal PDFs. | • OCR + native PDF parsing (`PyMuPDF` + `pytesseract`)<br>• `pgvector` RAG clause matching against citizen profiles<br>• Regional language voice synthesis (`.mp3` in `hi-IN`, `ta-IN`, `mr-IN`, `te-IN`, `en-IN`) with clause citations |
| **2. Civic Grievance & SLA Triage System** | Infrastructure complaints suffer from manual routing bottlenecks, duplicate filings, and opaque resolution tracking. | • Multimodal intake (Photo + Browser Voice Note + GPS)<br>• Whisper ASR transcription + VLM structural severity scoring<br>• **50m radius PostGIS (`ST_DWithin`) spatial deduplication**<br>• Unauthenticated Public SLA & Leaflet Geospatial Heatmap Dashboard |
| **3. Autonomous Bureaucracy Execution Agent** | Legacy government portals lack APIs and force citizens through brittle multi-step HTML forms. | • **AES-256-GCM encrypted** Citizen Profile Vault<br>• Headless **Playwright** worker navigating multi-step legacy forms<br>• Live WebSocket screenshot streaming + **Human-in-the-Loop (HITL)** OTP/CAPTCHA relay<br>• Verifiable downloadable PDF tracking receipts |
| **4. Real-Time Fact-Check & Deepfake Audit Engine** | Viral synthetic media and false policy rumors distort public trust. | • **C2PA Content Credentials** cryptographic manifest verification<br>• **Error Level Analysis (ELA)** heatmaps + ViT deepfake detection on images & `ffmpeg` video keyframes<br>• Cross-verification against `pgvector` trusted government registries |

---

## 🏗️ System Architecture

```mermaid
graph TB
    subgraph Client_SPA ["Client SPA (React 18 + Vite + TypeScript)"]
        Router["React Router DOM v6 (/policies, /grievances, /accountability, /agent, /fact-check)"]
        Hooks["Custom Server Hooks (useAsyncData / useAsyncAction)"]
        Stores["Zustand Client Stores (useAuthStore, usePreferencesStore, useLiveTaskStore)"]
        ApiLayer["Axios Service Modules + WebSocket Manager"]
        Router --> Hooks
        Router --> Stores
        Hooks --> ApiLayer
    end

    subgraph Server_Core ["Backend Core & Civic Domains (FastAPI)"]
        AppEntry["FastAPI Gateway + CORS + RBAC Middleware"]
        IdentityDom["Identity Domain (Argon2id, JWT, AES-256-GCM Profile Vault)"]
        PolicyDom["Policy Explainer Domain (PDF OCR, pgvector RAG, Regional TTS)"]
        GrievanceDom["Grievance Triage Domain (PostGIS 50m Dedup, VLM Severity, Public SLA)"]
        WSHub["Redis-Backed WebSocket Broadcast Hub"]
    end

    subgraph Server_Advanced ["Advanced AI & Automation Domains"]
        AgentDom["Bureaucracy Agent Domain (Playwright Worker, HITL OTP Relay, PDF Receipt)"]
        MockPortal["Self-Hosted Mock Legacy Gov Portal (/mock-gov-portal)"]
        FactDom["Fact-Verification Domain (C2PA, ELA + ViT Deepfake, Registry RAG)"]
    end

    subgraph Data_Infra ["Shared Persistence & Infrastructure"]
        PG[("PostgreSQL 16\n(pgvector + PostGIS)")]
        Redis[("Redis 7\n(Celery Broker + WS PubSub)")]
        MinIO[("MinIO S3 Storage\n(PDFs, Audio, Media, Receipts)")]
    end

    ApiLayer <-->|"REST /api/v1/* + WSS /ws/*"| AppEntry
    AppEntry --> IdentityDom & PolicyDom & GrievanceDom & AgentDom & FactDom & WSHub
    PolicyDom & GrievanceDom & AgentDom & FactDom <--> PG
    PolicyDom & GrievanceDom & AgentDom & FactDom <--> MinIO
    AgentDom <--> Redis
    AgentDom <-->|"Headless Chromium"| MockPortal
    Redis --> WSHub
```

---

## 🚀 Quick Start (Docker + Local Setup)

### Prerequisites
* **Docker & Docker Compose** (v2.20+)
* **Python 3.11+** (for local backend development/migrations)
* **Node.js 20+** & **npm** (for local React + Vite SPA development)

### 1. Clone & Configure Environment
```bash
git clone [https://github.com/your-org/civic-pulse-workspace.git](https://github.com/your-org/civic-pulse-workspace.git)
cd civic-pulse-workspace
cp .env.example .env
```

<details>
<summary><b>📄 Click to view required <code>.env</code> variables</b></summary>

```ini
# Database & Infrastructure
DATABASE_URL=postgresql+asyncpg://civicpulse:civicpulse_secret@localhost:5432/civicpulse_db
REDIS_URL=redis://localhost:6379/0
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET=civicpulse-media

# Security (Generate a 32-byte hex key for AES-256-GCM Vault Encryption)
JWT_SECRET_KEY=super_secret_jwt_signing_key_change_in_prod
VAULT_AES256_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef

# AI & External Providers (Optional: Offline deterministic fallbacks are built-in)
GEMINI_API_KEY=your_gemini_api_key
OPENAI_API_KEY=your_openai_api_key
GOOGLE_FACTCHECK_API_KEY=your_factcheck_key

# Frontend Vite Config
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_WS_BASE_URL=ws://localhost:8000
VITE_USE_API_MOCKS=false
```
</details>

### 2. Launch Infrastructure & Backend Services
Start PostgreSQL 16 (`pgvector` + `PostGIS`), Redis 7, and MinIO S3 storage:
```bash
docker compose up -d postgres redis minio
```

Install backend dependencies, run Alembic migrations, and seed sample data:
```bash
cd server
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
playwright install --with-deps chromium

# Run database migrations (001 Core + 002 Agent/Forensics)
alembic upgrade head

# Seed municipal departments, sample users, policies, and verified fact registry
python ../infra/seeds/seed_core_data.py
python ../infra/seeds/seed_verification_registry.py

# Start FastAPI Server & Celery Worker (in separate terminals)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
celery -A app.worker.celery_app worker --loglevel=info
```

### 3. Launch the React + Vite Frontend SPA
```bash
cd client
npm install
npm run dev
```

### 🌐 Active Service URLs
| Service | Local URL | Description |
| :--- | :--- | :--- |
| **Frontend SPA** | `http://localhost:5173` | React 18 + Vite + Tailwind UI |
| **Backend API & Swagger Docs** | `http://localhost:8000/docs` | Interactive OpenAPI 3.1 Documentation |
| **Mock Legacy Gov Portal** | `http://localhost:8000/mock-gov-portal/SCHOLARSHIP_RENEWAL` | Target portal for autonomous Playwright agent testing |
| **MinIO Object Console** | `http://localhost:9001` | S3 bucket browser (`minioadmin` / `minioadmin123`) |

---

## 📖 How to Use Civic Pulse (Step-by-Step Walkthrough)

### 1️⃣ Set Up Your Encrypted Citizen Vault
1. Log in at `http://localhost:5173/login` (or register a new account).
2. Navigate to **Bureaucracy Agent (`/agent`)** → **Citizen Profile Vault**.
3. Enter your demographic metrics (State, Annual Income, Occupation, MSME status) and sensitive PII (National ID, Date of Birth, Bank IBAN).
4. Click **Save to Encrypted Vault**. Sensitive PII is encrypted at rest using **AES-256-GCM** (`BYTEA`) and is only decrypted in-memory when matching policy eligibility or executing an authorized agent run.

### 2️⃣ Translate & Audit Government Policies (`/policies`)
1. Go to **Policy Studio (`/policies`)** and click **Upload Policy PDF** to ingest any government gazette or scheme notification (scanned or digital).
2. Select your preferred regional language from the top bar (`Hindi`, `Tamil`, `Marathi`, `Telugu`, or `English`).
3. Click **Generate Regional Explainer** on any indexed policy.
4. **Output:** View your personalized `ELIGIBLE` / `INELIGIBLE` breakdown, clause-by-clause citations, financial impacts, and listen to the synthesized regional `.mp3` voice explainer in the built-in audio player.

### 3️⃣ Report Civic Grievances & Track Public SLAs (`/grievances` & `/accountability`)
1. Open **Grievance Portal (`/grievances`)**.
2. Upload a photo of an infrastructure hazard (e.g., water pipeline burst, pothole), record a voice note using the browser microphone, and click **Detect GPS**.
3. Submit the report. The backend automatically:
   * Transcribes your voice note via Whisper ASR.
   * Evaluates structural hazard severity (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) via VLM.
   * Checks **PostGIS (`ST_DWithin`)** within a **50-meter radius** to link duplicate reports and increment upvote counts.
   * Assigns an SLA deadline (`CRITICAL` = 4h, `HIGH` = 24h) and routes the ticket to the responsible municipal department.
4. Visit **Public Accountability (`/accountability`)** (no login required) to explore the live **React-Leaflet geospatial heatmap** and department SLA compliance scorecards.

### 4️⃣ Dispatch the Autonomous Bureaucracy Agent (`/agent`)
1. Go to **Bureaucracy Agent (`/agent`)**, select a target service (e.g., `SCHOLARSHIP_RENEWAL` or `MSME_LICENSE`), and click **Launch Autonomous Agent**.
2. Watch the **Live Browser Stream Viewport** as the headless Playwright worker navigates `/mock-gov-portal/SCHOLARSHIP_RENEWAL`, populates multi-page HTML forms from your decrypted Citizen Vault, and uploads supporting certificates.
3. **Human-in-the-Loop (HITL) OTP Relay:** When the legacy portal challenges the agent with an SMS OTP modal, an interactive **HITL Obstacle Modal** automatically pops up in your React UI.
4. Enter the demo OTP **`482910`** and click **Submit to Agent**.
5. The agent resumes execution immediately, submits the final form, and returns a downloadable **Official PDF Tracking Receipt (`GOV-SCH-2026-*`)**.

### 5️⃣ Verify Viral Claims & Audit Deepfakes (`/fact-check`)
1. Navigate to **Fact-Check Studio (`/fact-check`)**.
2. Paste a suspicious viral claim or URL and upload an accompanying image or video clip.
3. Click **Run Forensic & Registry Audit**.
4. **Output:** Inspect the **Credibility Score Dial (0–100)**, **C2PA Content Credentials** signature status, side-by-side **Error Level Analysis (ELA) manipulation heatmap**, **ViT Deepfake probability score**, and direct citations from the `pgvector` verified government registry.

---

## 🔌 API & WebSocket Quick Reference

All REST endpoints are prefixed with `/api/v1` and return a standardized JSON envelope:
```json
{
  "success": true,
  "data": { ... },
  "meta": { "page": 1, "page_size": 20, "total_items": 1, "total_pages": 1 }
}
```

| Domain | Endpoint | Method | Auth | Description |
| :--- | :--- | :---: | :---: | :--- |
| **Identity** | `/api/v1/auth/register` | `POST` | Public | Register user (`CITIZEN`, `OFFICER`, `ADMIN`) |
| **Identity** | `/api/v1/auth/login` | `POST` | Public | Authenticate & receive JWT access token |
| **Identity** | `/api/v1/profile/vault` | `PUT` / `GET` | Bearer | Save or fetch AES-256-GCM encrypted Citizen Vault |
| **Policy** | `/api/v1/policies` | `POST` / `GET` | Bearer / Public | Upload & index policy PDF or search catalog |
| **Policy** | `/api/v1/policies/{id}/explain` | `POST` | Bearer | Generate RAG eligibility matrix + regional `.mp3` TTS |
| **Grievance** | `/api/v1/grievances` | `POST` | Public / Bearer | Submit multimodal complaint (Photo + Audio + GPS) |
| **Grievance** | `/api/v1/grievances/public-dashboard` | `GET` | Public | Fetch geospatial markers, KPIs & SLA scorecards |
| **Grievance** | `/api/v1/grievances/{id}/status` | `PATCH` | `OFFICER`/`ADMIN` | Update ticket status with resolution proof photo |
| **Agent** | `/api/v1/agent/runs` | `POST` | Bearer | Dispatch headless Playwright bureaucracy run |
| **Agent** | `/api/v1/agent/runs/{run_id}/hitl` | `POST` | Bearer | Supply OTP/CAPTCHA to resume paused Playwright worker |
| **Agent** | `/ws/agent/{run_id}` | `WSS` | Public / Token | Live stream of `STEP_UPDATE`, `AGENT_HITL_REQUIRED`, `AGENT_COMPLETED` |
| **Fact-Check** | `/api/v1/fact-checks/audit` | `POST` | Public / Bearer | Run C2PA, ELA/ViT deepfake & registry verification |
| **Fact-Check** | `/api/v1/fact-checks/feed` | `GET` | Public | Paginated feed of verified claims & forensic audits |

---

## 📂 Repository Structure

```text
civic-pulse-workspace/
├── contracts/                  # Locked OpenAPI 3.1 & WebSocket JSON schemas
├── infra/
│   ├── postgres/               # SQL init scripts (vector, postgis, pgcrypto)
│   └── seeds/                  # Core & fact-verification registry seed scripts
├── server/                     # FastAPI + SQLAlchemy 2.0 Async + Celery + Playwright
│   ├── migrations/versions/    # 001 (Core/Policy/Grievance) & 002 (Agent/FactCheck)
│   ├── app/
│   │   ├── core/               # DB, AES-256-GCM Security, MinIO, Redis PubSub, WS Hub
│   │   └── domains/
│   │       ├── identity/           # Auth, RBAC & Encrypted Citizen Vault
│   │       ├── policy_explainer/   # Pillar 1: PDF OCR, pgvector RAG, Regional TTS
│   │       ├── grievance_triage/   # Pillar 2: PostGIS Dedup, VLM Triage, Public SLA
│   │       ├── bureaucracy_agent/  # Pillar 3: Playwright Runner, HITL, Mock Gov Portal
│   │       └── fact_verification/  # Pillar 4: C2PA, ELA/ViT Forensics, Registry RAG
│   └── tests/                  # Async pytest suites across all 4 pillars
└── client/                     # Standalone React 18 + TypeScript + Vite SPA
    └── src/
        ├── api/                # Axios httpClient, wsClient & 5 domain API modules
        ├── hooks/              # Custom server hooks (useAsyncData, useAsyncAction)
        ├── stores/             # Zustand stores (auth, preferences, liveTask)
        ├── components/         # Modular UI components per pillar
        └── pages/              # Route views (/policies, /grievances, /agent, /fact-check)
```

---

## 👥 3-Person Parallel Development Workflow

This repository is engineered using **Vertical Domain Isolation** so three developers can build in parallel with **zero merge conflicts**:

| Developer Role | Dedicated Branch | Owned Paths | Independent Development Mode |
| :--- | :--- | :--- | :--- |
| **Person 1 — Frontend SPA Lead** | `feat/p1-frontend-spa` | `client/**` | Set `VITE_USE_API_MOCKS=true` in `.env` to develop and test all 4 UI pillars using built-in contract fixtures before backend merge. |
| **Person 2 — Backend Core & Pillars 1–2 Lead** | `feat/p2-civic-core` | `server/app/core/**`, `domains/identity/**`, `domains/policy_explainer/**`, `domains/grievance_triage/**`, `001_*.py` | Commits `core/` and `001` migration on Day 1 so Person 3 can branch off cleanly. |
| **Person 3 — Backend Automation & Forensics Lead (Pillars 3–4)** | `feat/p3-agent-and-forensics` | `domains/bureaucracy_agent/**`, `domains/fact_verification/**`, `002_*.py` | Chains migration `002` (`down_revision = '001'`) and tests Playwright against self-hosted `/mock-gov-portal`. |

---

## 🧪 Running Tests & Verification

```bash
# 1. Run Backend Unit, Spatial PostGIS, Playwright HITL & Forensic Tests
cd server
pytest -v

# 2. Run Frontend TypeScript Compiler Check & Production Bundle Build
cd ../client
npx tsc --noEmit
npm run build
```

---
