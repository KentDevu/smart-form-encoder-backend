# Catalyx SmartForm Encoder — AI Agent Instructions

> **Source of truth:** `docs/project-plan.md`
> If the project plan changes, update this file accordingly.

---

## Project Context

You are working on **Catalyx SmartForm Encoder**, an AI-assisted system that digitizes
handwritten paper forms used in Philippine City Hall operations. The system scans forms,
extracts field values via OCR/AI, presents data side-by-side with the form image for human
verification, saves to a database, and generates reports.

**Core Principle:** Automation suggests. Humans confirm.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (Pages Router), TypeScript, Tailwind CSS + shadcn/ui, Redux Toolkit |
| Backend | Python 3.12, FastAPI, Celery + Redis, SQLAlchemy 2.0 + Alembic, Pydantic v2 |
| Database | PostgreSQL (hosted on Supabase free tier) |
| OCR | PaddleOCR (primary), EasyOCR (fallback), GPT-4o Vision (low-confidence enhancement) |
| ML Training | Google Colab, LayoutLMv3, YOLOv8, PaddleOCR fine-tuning, T5 |
| Storage | Cloudflare R2 (S3-compatible, free tier) |
| Auth | Custom JWT (backend-managed), bcrypt, access + refresh tokens |
| Communication | REST API + WebSocket (real-time OCR progress) |
| Infrastructure | Docker + Docker Compose, Nginx |
| Package Managers | npm (frontend), pip (backend) |

---

## Architecture

### Microservices

The backend uses a **microservices** architecture with 3 services:

1. **API Service** (`smart-form-encoder-api`) — Auth, CRUD, form management, WebSocket (port 8000)
2. **OCR Worker** (`smart-form-encoder-ocr`) — Celery worker for image preprocessing + OCR extraction (no port)
3. **Report Service** (`smart-form-encoder-reports`) — Report generation, CSV/PDF export (port 8001)

### Frontend 4-Layer Architecture

```
src/
├── presentation/      ← Layer 1: UI Components, Layouts, Pages, Views
├── application/       ← Layer 2: Hooks, Redux State, Form Logic
├── domain/            ← Layer 3: Types, Models, Validation (Zod), Constants
└── infrastructure/    ← Layer 4: API Clients, WebSocket, Storage, Config
```

**Layer rules:**
- **Presentation:** Receives data via props only. No API calls. No business logic.
- **Application:** Orchestrates Domain + Infrastructure. Manages side effects. No UI rendering.
- **Domain:** Zero external dependencies. Pure TypeScript. No React, no API calls.
- **Infrastructure:** All external communication. Returns domain types. Encapsulates third-party libs.
- No layer may skip levels (Presentation cannot call Infrastructure directly).

### Repository Structure (Separate Repos)

| Repository | Description |
|---|---|
| `smart-form-encoder-web` | Next.js frontend |
| `smart-form-encoder-api` | FastAPI API service |
| `smart-form-encoder-ocr` | OCR worker (Celery) |
| `smart-form-encoder-reports` | Report service |
| `smart-form-encoder-infra` | Docker Compose, Nginx, deployment scripts |

---

## Code Rules

### General

- All frontend code in **TypeScript** with `strict: true`
- All backend code in **Python 3.12** with full type hints
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- No `any` types in TypeScript (use `unknown` if necessary)
- No `# type: ignore` in Python unless justified with a comment
- All sensitive config via environment variables — never hardcoded

### Frontend Rules

- Follow the 4-layer architecture strictly
- **Functional components** only (no class components)
- **Named exports** only (no default exports except Next.js pages)
- One component per file
- shadcn/ui components in `presentation/components/ui/`
- Custom hooks must start with `use` prefix
- All API calls go through `infrastructure/api/` only
- Forms use **Zod** for validation schemas
- Use **Redux Toolkit** for global state — no prop drilling beyond 2 levels
- Styling: **Tailwind CSS** utility classes + shadcn/ui `cn()` helper

### Backend Rules

- Every endpoint must have **Pydantic schemas** for request and response
- Use **dependency injection** (`Depends()`) for DB sessions and auth
- Business logic in `services/` — route handlers only handle HTTP concerns
- All database operations through **SQLAlchemy models**
- Use **Alembic** for all schema changes — never modify DB manually
- Celery tasks must be **idempotent** (safe to retry)
- Structured logging with proper log levels

### API Rules

- RESTful conventions with proper HTTP methods and status codes
- Consistent response shape:
  ```json
  {
    "success": true,
    "data": { },
    "message": "Optional message",
    "errors": []
  }
  ```
- Pagination: `?page=1&per_page=20`
- Filtering via query params: `?status=verified&date_from=2026-01-01`
- API versioning: `/api/v1/`
- WebSocket for OCR progress: `ws://host/ws/ocr/{form_entry_id}`

---

## Database Schema

### Key Tables

- **users** — id, email, password, full_name, role (`admin` | `encoder`), is_active
- **form_templates** — id, name, description, field_schema (JSON), sample_image_url
- **form_entries** — id, template_id (FK), uploaded_by (FK), verified_by (FK), image_url, status, raw_ocr_data, verified_data, confidence_score, processing_time
- **form_fields** — id, entry_id (FK), field_name, ocr_value, verified_value, confidence (float 0.0–1.0), was_corrected
- **audit_logs** — id, user_id (FK), action, entity_type, entity_id, changes (JSON), ip_address

### Status Flow

`uploaded` → `processing` → `extracted` → `verified` → `archived`

### Confidence Thresholds

- **High (0.9–1.0):** Normal display
- **Medium (0.7–0.89):** Subtle highlight
- **Low (< 0.7):** Red highlight, routed to GPT-4o Vision first

---

## OCR Pipeline

1. **Preprocess** — Crop, deskew, denoise, contrast enhance
2. **Template Detection** — Identify form type (MVP: manual selection by user)
3. **Region Extraction** — Bounding boxes from template field definitions
4. **PaddleOCR** — Primary extraction (free, runs offline)
5. **Confidence Scoring** — Score each field 0.0–1.0
6. **GPT-4o Vision** — Only for fields with confidence < 0.7 (pay-per-use)
7. **Field Mapping** — Map OCR text → structured form fields
8. **Store + Notify** — Save to DB, send WebSocket progress update

---

## ML Training Pipeline (OCR Accuracy Improvement)

A Google Colab-based continuous learning pipeline that improves OCR accuracy using human-verified data.

### Feedback Loop

```
Upload → OCR Extract → Human Verify → Corrections = Training Data → Fine-tune Models → Better OCR
```

### Training Data Source

The `form_fields` table provides labeled data:
- `ocr_value` — model input (what OCR extracted)
- `verified_value` — ground truth (what humans confirmed)
- `was_corrected` — error analysis flag
- `confidence` — model certainty score

### Colab Notebooks (in `notebooks/` directory)

| Notebook | Purpose |
|---|---|
| `01_data_export` | Download verified entries from DB/API as training dataset |
| `02_preprocessing_experiments` | Test deskew, denoise, binarization, contrast |
| `03_layout_detection` | Train YOLOv8 for field region detection |
| `04_ocr_finetuning` | Fine-tune PaddleOCR on PH handwriting |
| `05_field_mapping_model` | Train LayoutLMv3 for field classification (replaces LLM) |
| `06_post_correction` | Text correction for Filipino/English names, addresses |
| `07_evaluation` | Benchmark: field accuracy, CER, WER per template |

### Integration Points

- `ocr_service.py` → `_get_paddle_ocr()` — loads fine-tuned model
- `ocr_service.py` → `_map_fields_with_ai()` — replaced by local LayoutLMv3
- `ocr_service.py` → new `_post_correct()` — post-OCR text correction
- `api/v1/ml.py` — training data export endpoint

### ML Models

| Model | Purpose | Replaces |
|---|---|---|
| Fine-tuned PaddleOCR | PH handwriting recognition | Generic PaddleOCR |
| YOLOv8 | Field region detection | Manual template regions |
| LayoutLMv3 | Field classification (text + layout → field) | Groq/LLM API |
| T5 / Rule-based | Post-OCR text correction | New capability |

---

## User Roles

| Role | Permissions |
|---|---|
| **Admin** | Full access: manage users, templates, view all data, reports, exports, audit logs |
| **Encoder** | Upload forms, view/verify own OCR results, view own submissions |

---

## Authentication Flow

1. `POST /api/v1/auth/login` with email + password
2. Backend returns `{ access_token }` + sets `refresh_token` in httpOnly cookie
3. Access token: 30 min expiry, stored in Redux state (NOT localStorage)
4. Refresh token: 7 day expiry, httpOnly cookie
5. All requests use `Authorization: Bearer <access_token>` via Axios interceptor
6. On 401 → auto-refresh → retry; on refresh failure → redirect to login

---

## File Storage (Cloudflare R2)

- Bucket: `smartform-uploads`
- Path: `forms/{year}/{month}/{form_entry_id}/{filename}`
- Upload: Pre-signed URLs (frontend uploads directly to R2)
- SDK: `boto3` (S3-compatible)

---

## Form Templates (MVP)

Common Philippine City Hall forms:
1. Business Permit Application
2. Community Tax Certificate (Cedula)
3. Birth/Marriage/Death Certificate Applications
4. Barangay Clearance
5. Building Permit Application
6. Real Property Tax Declaration

> MVP starts with 2–3 most common forms.

---

## Constraints

- **Budget:** Free to low-cost. Use free tiers (Supabase, Cloudflare R2, open-source OCR).
- **Deployment:** Must work on AWS, VPS, or on-premise via Docker.
- **Compliance:** Philippine Data Privacy Act (RA 10173).
- **Users:** Non-technical City Hall staff — UI must be simple and intuitive.
- **Languages:** Forms in Filipino and English.

---

## Performance Targets

| Metric | Target |
|---|---|
| OCR extraction | < 5 seconds |
| Image upload | < 3 seconds |
| Page load | < 2 seconds |
| Verification save | < 1 second |
| Report generation | < 5 seconds |
| Concurrent users | 20+ |

---

## Git Workflow

- `main` — production-ready
- `develop` — integration branch
- `feature/description` — feature branches (from `develop`)
- `fix/description` — bugfix branches (from `develop`)
- Pull requests required for merges to `develop` and `main`

---

> **Reminder:** This file must stay in sync with `docs/project-plan.md`.
> When the project plan is updated, reflect changes here.

---

## Progress Tracking (MANDATORY)

**After every implementation session, you MUST:**

1. **Update `docs/project-plan.md`:**
   - Mark completed items with `[x]` in Section 16 (Implementation Plan).
   - Add a dated entry to the **Progress Log** appendix.
2. **Update this file (`.github/copilot-instructions.md`):**
   - Reflect any architecture, rules, or tech stack changes.
3. **Never leave the plan stale** — it is the single source of truth for project status.

This ensures continuity across sessions and agents.
