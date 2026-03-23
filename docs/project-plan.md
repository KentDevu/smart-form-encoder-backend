# Catalyx SmartForm Encoder — Project Plan

> AI-Assisted Handwritten Form Digitization System for Philippine City Hall Operations

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Goals & Success Criteria](#2-goals--success-criteria)
3. [Constraints](#3-constraints)
4. [Technology Stack](#4-technology-stack)
5. [System Architecture](#5-system-architecture)
6. [Frontend Architecture](#6-frontend-architecture)
7. [Backend Architecture](#7-backend-architecture)
8. [Database Design](#8-database-design)
9. [OCR & AI Pipeline](#9-ocr--ai-pipeline)
10. [API Design](#10-api-design)
11. [Authentication & Authorization](#11-authentication--authorization)
12. [File Storage](#12-file-storage)
13. [Project Structure](#13-project-structure)
14. [Form Templates (MVP)](#14-form-templates-mvp)
15. [User Roles & Permissions](#15-user-roles--permissions)
16. [Implementation Plan](#16-implementation-plan)
17. [Development Workflow & Rules](#17-development-workflow--rules)
18. [Deployment Strategy](#18-deployment-strategy)
19. [Reporting Module](#19-reporting-module)
20. [Security & Compliance](#20-security--compliance)
21. [Performance Targets](#21-performance-targets)
22. [Risk & Mitigation](#22-risk--mitigation)
23. [Future Roadmap](#23-future-roadmap)
24. [ML Training Pipeline (OCR Accuracy)](#24-ml-training-pipeline-ocr-accuracy)

---

## 1. Project Overview

**Catalyx SmartForm Encoder** is an AI-assisted system that digitizes handwritten paper forms
used in Philippine City Hall operations. It scans handwritten forms, extracts probable field
values using OCR and AI, presents suggested data side-by-side with the form image for human
verification, saves structured data to a database, and generates reports.

**Core Principle:** Automation suggests. Humans confirm.

**Team Size:** 2–3 developers
**Timeline:** 6–8 weeks for MVP
**Budget:** Free to low-cost (development and early production)

---

## 2. Goals & Success Criteria

### Primary Goals

- Reduce manual encoding time by 70–90%
- Achieve near 100% final data accuracy (after human correction)
- Eliminate overtime caused by manual data entry backlogs
- Provide automated daily/monthly reporting with CSV export
- Support common Philippine City Hall form types

### Success Criteria

| Metric | Target |
|---|---|
| Encoding speed improvement | 70–90% faster than manual |
| OCR accuracy (before correction) | 70–85% |
| Final accuracy (after correction) | ~100% |
| OCR extraction time | < 5 seconds per form |
| Verification time | < 30 seconds per form |
| System uptime | 99% |
| MVP delivery | 6–8 weeks |

---

## 3. Constraints

### Budget

- **Free to low-cost** for development and early production
- Use free tiers wherever possible (Supabase, Cloudflare R2, open-source OCR)
- Pay-per-use for GPT-4o Vision only on low-confidence OCR fields
- No paid SaaS unless justified by critical need

### Technical

- Must run in Docker for portability across deployment targets
- Must support deployment to AWS, VPS, or on-premise City Hall servers
- Internet dependency: OCR fallback (GPT-4o) requires network; primary OCR (PaddleOCR) runs offline
- Must comply with the **Philippine Data Privacy Act (RA 10173)**

### Operational

- System must be usable by non-technical City Hall staff
- UI must be simple, intuitive, and responsive
- Forms are primarily in Filipino and English

---

## 4. Technology Stack

### Frontend

| Component | Technology |
|---|---|
| Framework | **Next.js** (Pages Router) |
| Language | **TypeScript** |
| UI Library | **Tailwind CSS + shadcn/ui** |
| State Management | **Redux Toolkit** |
| Package Manager | **npm** |
| Real-time | **WebSocket** (for OCR progress updates) |
| HTTP Client | **Axios** or **fetch** wrapper |

### Backend

| Component | Technology |
|---|---|
| Framework | **FastAPI** (Python) |
| Language | **Python 3.12** |
| Task Queue | **Celery + Redis** |
| WebSocket | **FastAPI WebSocket** |
| Validation | **Pydantic v2** |
| ORM | **SQLAlchemy 2.0** + **Alembic** (migrations) |

### OCR & AI

| Component | Technology |
|---|---|
| Primary OCR | **PaddleOCR** (free, high-quality handwriting recognition) |
| Fallback OCR | **EasyOCR** (backup engine) |
| AI Enhancement | **GPT-4o Vision** (for low-confidence fields, pay-per-use) |
| Confidence Scoring | Custom scoring based on OCR output probabilities |

### Database

| Component | Technology |
|---|---|
| Database | **PostgreSQL** |
| Hosting | **Supabase** (free tier: 500MB, 2 projects) |
| Migrations | **Alembic** |

### File Storage

| Component | Technology |
|---|---|
| Object Storage | **Cloudflare R2** (S3-compatible, free: 10GB storage, 10M reads/mo) |
| Image Formats | JPG, PNG, PDF |

### Infrastructure

| Component | Technology |
|---|---|
| Containerization | **Docker + Docker Compose** |
| Message Broker | **Redis** |
| Reverse Proxy | **Nginx** or **Caddy** |
| Deployment | AWS / VPS / On-premise (Docker-based) |

---

## 5. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                         │
│                    Next.js (Pages Router)                        │
│              Tailwind CSS + shadcn/ui + Redux                   │
└──────────────┬──────────────────────┬───────────────────────────┘
               │ REST API             │ WebSocket
               ▼                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                      API GATEWAY / NGINX                         │
└──────┬──────────────────┬──────────────────┬─────────────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌─────────────┐  ┌────────────────┐  ┌─────────────────┐
│  API Service │  │  OCR Worker    │  │ Report Service  │
│  (FastAPI)   │  │  (Celery)      │  │ (FastAPI)       │
│              │  │                │  │                 │
│ - Auth       │  │ - PaddleOCR    │  │ - CSV export    │
│ - CRUD       │  │ - EasyOCR      │  │ - PDF export    │
│ - Form mgmt  │  │ - GPT-4o Vision│  │ - Aggregations  │
│ - WebSocket  │  │ - Preprocessing│  │                 │
└──────┬───────┘  └───────┬────────┘  └────────┬────────┘
       │                  │                     │
       ▼                  ▼                     ▼
┌──────────────────────────────────────────────────────────────────┐
│                         SHARED DATA LAYER                        │
│                                                                  │
│   ┌──────────────┐  ┌───────────┐  ┌──────────────────┐         │
│   │  PostgreSQL   │  │   Redis   │  │  Cloudflare R2   │         │
│   │  (Supabase)   │  │  (Broker  │  │  (Image Storage) │         │
│   │              │  │   + Cache) │  │                  │         │
│   └──────────────┘  └───────────┘  └──────────────────┘         │
└──────────────────────────────────────────────────────────────────┘
```

### Microservices Breakdown

| Service | Responsibility | Port |
|---|---|---|
| **API Service** | Auth, CRUD, form management, WebSocket notifications | 8000 |
| **OCR Worker** | Image preprocessing, OCR extraction, AI enhancement | Celery worker (no port) |
| **Report Service** | Report generation, CSV/PDF export, aggregations | 8001 |

### Communication

- **Client ↔ API Service:** REST + WebSocket
- **API Service → OCR Worker:** Celery task queue (via Redis)
- **OCR Worker → API Service:** Celery result backend (Redis) + WebSocket notification
- **API Service ↔ Report Service:** Internal REST API

---

## 6. Frontend Architecture

### 4-Layer Architecture

```
src/
├── presentation/      ← Layer 1: UI Components & Pages
├── application/       ← Layer 2: Hooks, State, Form Logic
├── domain/            ← Layer 3: Types, Interfaces, Validation, Business Logic
└── infrastructure/    ← Layer 4: API Clients, Storage Adapters, External Services
```

#### Layer 1 — Presentation Layer

- **Pages** (`pages/`): Next.js page routes
- **Layouts** (`presentation/layouts/`): Page shells, navigation, sidebars
- **Components** (`presentation/components/`): Reusable UI components (shadcn/ui wrappers)
- **Views** (`presentation/views/`): Page-specific composed views

**Rules:**
- Components receive data via props only
- No direct API calls in this layer
- No business logic — only rendering and event forwarding

#### Layer 2 — Application Layer

- **Hooks** (`application/hooks/`): Custom React hooks
- **State** (`application/state/`): Redux slices, selectors, thunks
- **Forms** (`application/forms/`): Form schemas, validation, submission logic

**Rules:**
- Orchestrates Domain and Infrastructure layers
- Manages side effects (data fetching, state updates)
- Contains no UI rendering code

#### Layer 3 — Domain Layer

- **Types** (`domain/types/`): TypeScript interfaces and type definitions
- **Models** (`domain/models/`): Domain entity definitions
- **Validation** (`domain/validation/`): Business rule validators (Zod schemas)
- **Constants** (`domain/constants/`): Business constants, enums, form field maps

**Rules:**
- Zero dependencies on other layers
- Pure TypeScript — no React, no API, no side effects
- Portable and testable in isolation

#### Layer 4 — Infrastructure Layer

- **API** (`infrastructure/api/`): REST API clients (Axios instances, endpoint definitions)
- **WebSocket** (`infrastructure/ws/`): WebSocket connection manager
- **Storage** (`infrastructure/storage/`): Local storage, session storage adapters
- **Config** (`infrastructure/config/`): Environment variables, feature flags

**Rules:**
- Handles all external communication
- Returns domain types (transforms API responses to domain models)
- Encapsulates third-party library specifics

### Frontend Project Structure

```
smart-form-encoder-web/
├── public/
│   ├── favicon.ico
│   └── assets/
├── src/
│   ├── pages/                          # Next.js Pages Router
│   │   ├── _app.tsx
│   │   ├── _document.tsx
│   │   ├── index.tsx                   # Landing / Dashboard
│   │   ├── login.tsx
│   │   ├── forms/
│   │   │   ├── index.tsx               # Form list
│   │   │   ├── upload.tsx              # Upload new form
│   │   │   └── [id]/
│   │   │       ├── verify.tsx          # Side-by-side verification
│   │   │       └── detail.tsx          # Form detail view
│   │   ├── reports/
│   │   │   └── index.tsx               # Reports page
│   │   └── admin/
│   │       ├── users.tsx               # User management
│   │       └── templates.tsx           # Form template config
│   │
│   ├── presentation/
│   │   ├── layouts/
│   │   │   ├── MainLayout.tsx
│   │   │   ├── AuthLayout.tsx
│   │   │   └── Sidebar.tsx
│   │   ├── components/
│   │   │   ├── ui/                     # shadcn/ui components
│   │   │   ├── common/
│   │   │   │   ├── LoadingSpinner.tsx
│   │   │   │   ├── ErrorBoundary.tsx
│   │   │   │   └── ConfidenceBadge.tsx
│   │   │   ├── forms/
│   │   │   │   ├── FormUploader.tsx
│   │   │   │   ├── FormImageViewer.tsx
│   │   │   │   ├── FieldEditor.tsx
│   │   │   │   └── VerificationPanel.tsx
│   │   │   └── reports/
│   │   │       ├── ReportTable.tsx
│   │   │       └── ReportExport.tsx
│   │   └── views/
│   │       ├── DashboardView.tsx
│   │       ├── VerificationView.tsx
│   │       └── ReportView.tsx
│   │
│   ├── application/
│   │   ├── hooks/
│   │   │   ├── useAuth.ts
│   │   │   ├── useFormUpload.ts
│   │   │   ├── useOcrProgress.ts
│   │   │   └── useFormVerification.ts
│   │   ├── state/
│   │   │   ├── store.ts
│   │   │   ├── slices/
│   │   │   │   ├── authSlice.ts
│   │   │   │   ├── formsSlice.ts
│   │   │   │   ├── ocrSlice.ts
│   │   │   │   └── reportsSlice.ts
│   │   │   └── selectors/
│   │   │       └── formSelectors.ts
│   │   └── forms/
│   │       ├── verificationFormSchema.ts
│   │       └── loginFormSchema.ts
│   │
│   ├── domain/
│   │   ├── types/
│   │   │   ├── form.ts
│   │   │   ├── user.ts
│   │   │   ├── ocrResult.ts
│   │   │   ├── report.ts
│   │   │   └── api.ts
│   │   ├── models/
│   │   │   ├── FormEntry.ts
│   │   │   └── OcrField.ts
│   │   ├── validation/
│   │   │   ├── formValidation.ts
│   │   │   └── userValidation.ts
│   │   └── constants/
│   │       ├── formTemplates.ts
│   │       ├── roles.ts
│   │       └── ocrConfidence.ts
│   │
│   ├── infrastructure/
│   │   ├── api/
│   │   │   ├── client.ts               # Axios instance + interceptors
│   │   │   ├── authApi.ts
│   │   │   ├── formsApi.ts
│   │   │   ├── ocrApi.ts
│   │   │   └── reportsApi.ts
│   │   ├── ws/
│   │   │   └── ocrWebSocket.ts         # WebSocket for OCR progress
│   │   ├── storage/
│   │   │   └── tokenStorage.ts
│   │   └── config/
│   │       └── env.ts
│   │
│   ├── lib/
│   │   └── utils.ts                    # shadcn/ui utility (cn function)
│   │
│   └── styles/
│       └── globals.css                 # Tailwind base styles
│
├── .env.local
├── .env.example
├── next.config.js
├── tailwind.config.ts
├── tsconfig.json
├── package.json
├── Dockerfile
├── .dockerignore
├── .eslintrc.json
├── .prettierrc
└── README.md
```

---

## 7. Backend Architecture

### Microservices Structure

Each service is a standalone FastAPI application with its own Dockerfile.

#### Service 1: API Service (`smart-form-encoder-api`)

Main gateway — handles auth, CRUD, form management, and WebSocket.

```
smart-form-encoder-api/
├── app/
│   ├── main.py                        # FastAPI app entry point
│   ├── config.py                      # Settings (pydantic-settings)
│   ├── database.py                    # SQLAlchemy engine + session
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                    # Dependency injection (get_db, get_current_user)
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py              # Main v1 router
│   │       ├── auth.py                # Login, register, refresh token
│   │       ├── forms.py               # Form CRUD endpoints
│   │       ├── ocr.py                 # OCR trigger + status endpoints
│   │       ├── users.py               # User management (admin)
│   │       └── ws.py                  # WebSocket for OCR progress
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py                    # User SQLAlchemy model
│   │   ├── form_entry.py              # FormEntry model
│   │   ├── form_field.py              # FormField extracted data
│   │   ├── form_template.py           # FormTemplate model
│   │   └── audit_log.py               # AuditLog model
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── auth.py                    # Login/Register request/response
│   │   ├── form.py                    # Form schemas
│   │   ├── ocr.py                     # OCR result schemas
│   │   └── user.py                    # User schemas
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py            # JWT creation, password hashing
│   │   ├── form_service.py            # Form business logic
│   │   ├── ocr_service.py             # Celery task dispatch
│   │   ├── storage_service.py         # Cloudflare R2 upload/download
│   │   └── user_service.py            # User CRUD logic
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── security.py                # JWT utils, password hashing
│   │   ├── exceptions.py              # Custom exceptions
│   │   └── middleware.py              # CORS, logging middleware
│   │
│   └── utils/
│       ├── __init__.py
│       └── helpers.py
│
├── alembic/
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│
├── tests/
│   ├── conftest.py
│   ├── test_auth.py
│   └── test_forms.py
│
├── requirements.txt
├── Dockerfile
├── .env
├── .env.example
└── README.md
```

#### Service 2: OCR Worker (`smart-form-encoder-ocr`)

Background worker — processes images, runs OCR, enhances with AI.

```
smart-form-encoder-ocr/
├── app/
│   ├── main.py                        # Celery app initialization
│   ├── config.py                      # Worker settings
│   │
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── ocr_task.py                # Main OCR extraction task
│   │   └── preprocess_task.py         # Image preprocessing task
│   │
│   ├── engines/
│   │   ├── __init__.py
│   │   ├── paddle_engine.py           # PaddleOCR wrapper
│   │   ├── easy_engine.py             # EasyOCR wrapper (fallback)
│   │   └── gpt4o_engine.py            # GPT-4o Vision API (enhancement)
│   │
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── preprocessor.py            # Crop, deskew, denoise, enhance
│   │   ├── extractor.py               # OCR orchestration logic
│   │   ├── field_mapper.py            # Map OCR output → form fields
│   │   └── confidence_scorer.py       # Score confidence per field
│   │
│   ├── templates/
│   │   ├── __init__.py
│   │   └── field_definitions.py       # Form template field regions & labels
│   │
│   └── utils/
│       ├── __init__.py
│       ├── image_utils.py             # Image manipulation helpers
│       └── text_utils.py              # Text cleanup, normalization
│
├── tests/
│   └── test_ocr_pipeline.py
│
├── requirements.txt
├── Dockerfile
└── README.md
```

#### Service 3: Report Service (`smart-form-encoder-reports`)

Report generation service — aggregates data and exports.

```
smart-form-encoder-reports/
├── app/
│   ├── main.py                        # FastAPI app
│   ├── config.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── reports.py             # Report endpoints
│   │       └── exports.py             # CSV/PDF export endpoints
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── report_service.py          # Aggregation logic
│   │   ├── csv_exporter.py            # CSV generation
│   │   └── pdf_exporter.py            # PDF generation
│   │
│   └── schemas/
│       ├── __init__.py
│       └── report.py
│
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## 8. Database Design

### Entity Relationship

```
┌─────────────┐       ┌──────────────────┐       ┌──────────────────┐
│    users     │       │  form_templates  │       │   form_entries   │
├─────────────┤       ├──────────────────┤       ├──────────────────┤
│ id (PK)     │       │ id (PK)          │       │ id (PK)          │
│ email       │       │ name             │       │ template_id (FK) │
│ password    │       │ description      │       │ uploaded_by (FK) │
│ full_name   │       │ field_schema     │       │ verified_by (FK) │
│ role        │       │ sample_image_url │       │ image_url        │
│ is_active   │       │ created_at       │       │ status           │
│ created_at  │       │ updated_at       │       │ raw_ocr_data     │
│ updated_at  │       └──────────────────┘       │ verified_data    │
└─────────────┘                                  │ confidence_score │
                                                 │ processing_time  │
       ┌──────────────────┐                      │ created_at       │
       │   form_fields    │                      │ updated_at       │
       ├──────────────────┤                      └──────────────────┘
       │ id (PK)          │
       │ entry_id (FK)    │       ┌──────────────────┐
       │ field_name       │       │   audit_logs     │
       │ ocr_value        │       ├──────────────────┤
       │ verified_value   │       │ id (PK)          │
       │ confidence       │       │ user_id (FK)     │
       │ was_corrected    │       │ action           │
       │ created_at       │       │ entity_type      │
       └──────────────────┘       │ entity_id        │
                                  │ changes          │
                                  │ ip_address       │
                                  │ created_at       │
                                  └──────────────────┘
```

### Key Fields

**form_entries.status** enum: `uploaded` → `processing` → `extracted` → `verified` → `archived`

**form_fields.confidence** float: 0.0–1.0 (threshold for highlighting: < 0.7)

**users.role** enum: `admin`, `encoder`

---

## 9. OCR & AI Pipeline

### Processing Flow

```
Image Upload
     │
     ▼
┌─────────────────┐
│ 1. Preprocess    │  ← Crop, deskew, denoise, contrast enhance
└────────┬────────┘
         ▼
┌─────────────────┐
│ 2. Template      │  ← Detect which form type (MVP: manual selection)
│    Detection     │
└────────┬────────┘
         ▼
┌─────────────────┐
│ 3. Region        │  ← Identify field bounding boxes from template definition
│    Extraction    │
└────────┬────────┘
         ▼
┌─────────────────┐
│ 4. PaddleOCR     │  ← Primary OCR engine (free, self-hosted)
│    Extraction    │
└────────┬────────┘
         ▼
┌─────────────────┐
│ 5. Confidence    │  ← Score each field (0.0 – 1.0)
│    Scoring       │
└────────┬────────┘
         ▼
┌─────────────────────────┐
│ 6. Low Confidence?       │
│    (< 0.7 threshold)    │
└────┬───────────┬────────┘
     │ YES       │ NO
     ▼           ▼
┌──────────┐  ┌──────────────┐
│ GPT-4o   │  │ Return       │
│ Vision   │  │ Results      │
│ (enhance)│  │              │
└────┬─────┘  └──────┬───────┘
     │               │
     ▼               ▼
┌──────────────────────────┐
│ 7. Field Mapping          │  ← Map OCR text to structured form fields
└───────────┬──────────────┘
            ▼
┌──────────────────────────┐
│ 8. Store + Notify         │  ← Save to DB, send WebSocket notification
└──────────────────────────┘
```

### Confidence Scoring Strategy

| Score | Label | Action |
|---|---|---|
| 0.9–1.0 | High | Auto-filled, normal display |
| 0.7–0.89 | Medium | Auto-filled, subtle highlight |
| 0.0–0.69 | Low | Auto-filled, **red highlight**, routed to GPT-4o first |

---

## 10. API Design

### Base URL

```
API Service:    /api/v1/
Report Service: /api/v1/reports/
WebSocket:      /ws/ocr/{form_entry_id}
```

### Core Endpoints

#### Authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/auth/login` | User login → returns JWT |
| POST | `/api/v1/auth/register` | Register new user (admin only) |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| GET | `/api/v1/auth/me` | Get current user profile |

#### Forms

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/forms` | List all form entries (paginated, filterable) |
| POST | `/api/v1/forms/upload` | Upload scanned form image |
| GET | `/api/v1/forms/{id}` | Get form entry details + OCR results |
| PUT | `/api/v1/forms/{id}/verify` | Submit verified/corrected data |
| DELETE | `/api/v1/forms/{id}` | Delete form entry (admin only) |

#### OCR

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/ocr/{form_entry_id}/process` | Trigger OCR processing |
| GET | `/api/v1/ocr/{form_entry_id}/status` | Get OCR processing status |
| GET | `/api/v1/ocr/{form_entry_id}/results` | Get OCR extraction results |

#### Reports

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/reports/daily` | Daily form processing summary |
| GET | `/api/v1/reports/monthly` | Monthly form processing summary |
| GET | `/api/v1/reports/export/csv` | Download CSV export |

#### Users (Admin)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/users` | List all users |
| POST | `/api/v1/users` | Create user |
| PUT | `/api/v1/users/{id}` | Update user |
| DELETE | `/api/v1/users/{id}` | Deactivate user |

#### WebSocket

| Endpoint | Description |
|---|---|
| `ws://host/ws/ocr/{form_entry_id}` | Real-time OCR progress updates |

**WebSocket message format:**
```json
{
  "type": "ocr_progress",
  "form_entry_id": "uuid",
  "stage": "preprocessing | extracting | enhancing | mapping | complete",
  "progress": 75,
  "message": "Extracting text from fields..."
}
```

---

## 11. Authentication & Authorization

### Strategy: Custom JWT (Backend-Managed)

- **Access Token:** Short-lived (30 minutes), sent in `Authorization: Bearer <token>` header
- **Refresh Token:** Long-lived (7 days), stored in httpOnly cookie
- **Password Hashing:** bcrypt via `passlib`
- **Token Library:** `python-jose` (JWT encoding/decoding)

### Flow

```
1. User submits email + password → POST /api/v1/auth/login
2. Backend validates credentials
3. Backend returns { access_token, token_type } + sets refresh_token cookie
4. Frontend stores access_token in memory (Redux state, NOT localStorage)
5. Frontend attaches token to all API requests via Axios interceptor
6. On 401 → Frontend calls /api/v1/auth/refresh → gets new access_token
7. On refresh failure → redirect to login
```

---

## 12. File Storage

### Cloudflare R2 Configuration

- **Bucket:** `smartform-uploads`
- **Path Structure:** `forms/{year}/{month}/{form_entry_id}/{filename}`
- **Example:** `forms/2026/03/uuid-1234/scan.jpg`
- **Access:** Pre-signed URLs for upload and download
- **SDK:** `boto3` (S3-compatible API)

### Upload Flow

1. Frontend requests pre-signed upload URL from API
2. Frontend uploads directly to Cloudflare R2
3. Frontend confirms upload to API with the file key
4. API stores the R2 object key in the database

---

## 13. Project Structure

### Repository Layout (Separate Repos)

| Repository | Description |
|---|---|
| `smart-form-encoder-web` | Next.js frontend application |
| `smart-form-encoder-api` | FastAPI main API service |
| `smart-form-encoder-ocr` | OCR worker service (Celery) |
| `smart-form-encoder-reports` | Report generation service |
| `smart-form-encoder-infra` | Docker Compose, Nginx config, deployment scripts |

### Infrastructure Repo

```
smart-form-encoder-infra/
├── docker-compose.yml              # Full stack orchestration
├── docker-compose.dev.yml          # Development overrides
├── nginx/
│   └── nginx.conf                  # Reverse proxy config
├── scripts/
│   ├── setup.sh                    # First-time setup script
│   ├── seed-db.sh                  # Seed database with test data
│   └── backup.sh                   # Database backup script
├── .env.example
└── README.md
```

### Docker Compose Services

```yaml
services:
  web:        # Next.js frontend
  api:        # FastAPI API service
  ocr-worker: # Celery OCR worker
  reports:    # Report service
  redis:      # Message broker + cache
  db:         # PostgreSQL (local dev only)
  nginx:      # Reverse proxy
```

---

## 14. Form Templates (MVP)

### Supported Philippine City Hall Forms

| # | Form Name | Department | Key Fields |
|---|---|---|---|
| 1 | **Business Permit Application** | Business Permits & Licensing | Business name, owner, address, type of business, capitalization, date |
| 2 | **Community Tax Certificate (Cedula)** | Treasury | Full name, address, birthdate, occupation, income, tax amount |
| 3 | **Birth Certificate Application** | Civil Registry | Child name, parents, date/place of birth, attendant |
| 4 | **Marriage Certificate Application** | Civil Registry | Bride/Groom names, date/place of marriage, witnesses |
| 5 | **Death Certificate Application** | Civil Registry | Deceased name, date/place/cause of death, informant |
| 6 | **Barangay Clearance** | Barangay Office | Full name, address, purpose, date issued |
| 7 | **Building Permit Application** | Engineering | Owner, location, building type, area, estimated cost |
| 8 | **Real Property Tax Declaration** | Assessor's Office | Owner, property location, classification, assessed value |

> **MVP Scope:** Start with 2–3 most common forms, expand in Phase 2.

---

## 15. User Roles & Permissions

### Role Definitions

| Role | Description |
|---|---|
| **Admin** | Full system access — manage users, templates, view all data, generate reports |
| **Encoder** | Upload forms, view OCR results, verify/correct data, view own submissions |

### Permission Matrix

| Action | Admin | Encoder |
|---|---|---|
| Upload form | ✅ | ✅ |
| View OCR results | ✅ | ✅ (own) |
| Verify/correct data | ✅ | ✅ (own) |
| View all form entries | ✅ | ❌ |
| Generate reports | ✅ | ❌ |
| Export CSV | ✅ | ❌ |
| Manage users | ✅ | ❌ |
| Manage templates | ✅ | ❌ |
| View audit logs | ✅ | ❌ |
| Delete entries | ✅ | ❌ |

---

## 16. Implementation Plan

### Phase 1 — MVP (Weeks 1–4)

#### Week 1: Foundation

- [x] Set up all repositories and Docker Compose infrastructure
- [x] Initialize Next.js project with Pages Router, Tailwind, shadcn/ui
- [x] Initialize FastAPI project with SQLAlchemy, Alembic
- [x] Set up PostgreSQL on Supabase
- [x] Set up Cloudflare R2 bucket
- [x] Implement user authentication (JWT)
- [x] Build login page

#### Week 2: Core Upload & OCR

- [x] Build form upload page (drag-and-drop, camera capture)
- [x] Implement image upload to Cloudflare R2 (pre-signed URLs)
- [x] Set up Celery + Redis for OCR worker
- [x] Integrate PaddleOCR engine
- [ ] Build image preprocessing pipeline (deskew, denoise)
- [x] Implement basic field extraction for 1 form template

#### Week 3: Verification UI

- [x] Build side-by-side verification interface
  - Left panel: zoomable scanned image
  - Right panel: editable form fields with confidence indicators
- [ ] Implement WebSocket for real-time OCR progress
- [x] Build form field editor with confidence highlighting
- [x] Implement verify/save workflow
- [x] Database storage for verified data

#### Week 4: Polish & Reports

- [x] Build dashboard page (basic — form list, status overview)
- [ ] Implement basic daily/monthly report endpoints
- [ ] Build CSV export functionality
- [ ] Admin: user management page
- [ ] Error handling, loading states, edge cases
- [ ] End-to-end testing of full workflow
- [ ] Bug fixes and UX polish

### Phase 2 — Production (Weeks 5–6)

- [x] Add GPT-4o Vision for low-confidence enhancement
- [x] Add 2–3 more form templates
- [ ] Confidence scoring system tuning
- [ ] Role-based access enforcement (middleware)
- [ ] Audit logging
- [ ] Security hardening (rate limiting, input sanitization, CORS)
- [ ] Reporting dashboard with filters

### Phase 3 — Advanced (Weeks 7–8)

- [ ] Automatic form template detection
- [ ] Batch upload support (multiple forms)
- [ ] PDF report generation
- [ ] Performance optimization (caching, lazy loading)
- [ ] Deployment automation scripts
- [ ] Documentation and user guide
- [ ] UAT with City Hall staff

### Phase 4 — ML Training Pipeline (Weeks 9–12)

#### 4A: Data Pipeline + Evaluation Baseline

- [ ] Add training data export API endpoint (`GET /api/v1/ml/export-training-data`)
- [ ] Build data export script (images + verified fields from DB → labeled dataset)
- [ ] Create Colab notebook: `01_data_export.ipynb` — download dataset from API/DB
- [ ] Create Colab notebook: `02_preprocessing_experiments.ipynb` — test deskew, denoise, binarization, contrast
- [ ] Create Colab notebook: `07_evaluation_baseline.ipynb` — benchmark current pipeline (field accuracy, CER, WER per template)
- [ ] Establish accuracy baselines per form template

#### 4B: Model Training + Fine-tuning

- [ ] Create Colab notebook: `03_layout_detection.ipynb` — train YOLOv8 for field region detection
- [ ] Create Colab notebook: `04_ocr_finetuning.ipynb` — fine-tune PaddleOCR on PH handwriting samples
- [ ] Create Colab notebook: `05_field_mapping_model.ipynb` — train LayoutLMv3 for field classification (replace LLM dependency)
- [ ] Create Colab notebook: `06_post_correction.ipynb` — text correction model for Filipino/English names, addresses
- [ ] Export trained models as artifacts (ONNX / pickle / safetensors)

#### 4C: Integration + Deployment

- [ ] Integrate fine-tuned PaddleOCR into OCR worker (`_get_paddle_ocr()` swap)
- [ ] Integrate LayoutLMv3 field mapper into `ocr_service.py` (replace `_map_fields_with_ai()`)
- [ ] Add model versioning + A/B testing support (compare old vs new pipeline)
- [ ] Continuous learning loop: new verified entries auto-added to training pool
- [ ] Accuracy regression tests (ensure new models don't degrade on existing templates)

---

## 17. Development Workflow & Rules

### Code Rules

#### General

- All code must be in **TypeScript** (frontend) and **Python 3.12** (backend)
- Use **strict TypeScript** (`strict: true` in tsconfig)
- Use **type hints** everywhere in Python
- Write meaningful commit messages (conventional commits: `feat:`, `fix:`, `docs:`, etc.)
- No `any` types in TypeScript (use `unknown` if necessary)
- No `# type: ignore` in Python unless justified with comment

#### Frontend Rules

- Follow the 4-layer architecture — no layer may skip levels
- Components must be **functional** (no class components)
- Use **named exports** (no default exports except pages)
- One component per file
- shadcn/ui components go in `presentation/components/ui/`
- Custom hooks must start with `use` prefix
- All API calls go through Infrastructure Layer only
- Forms use **Zod** for validation schemas
- Use **Redux Toolkit** for global state — no prop drilling beyond 2 levels

#### Backend Rules

- Every endpoint must have **Pydantic schemas** for request/response
- Use **dependency injection** for DB sessions and auth
- Business logic lives in **services/** — not in route handlers
- All database operations go through **SQLAlchemy models**
- Use **Alembic** for all schema changes — never modify DB manually
- Celery tasks must be **idempotent** (safe to retry)
- All sensitive config via **environment variables** (never hardcoded)
- Log all errors with structured logging

#### API Rules

- RESTful conventions: proper HTTP methods and status codes
- All responses follow consistent shape:
  ```json
  {
    "success": true,
    "data": { ... },
    "message": "Optional message",
    "errors": []
  }
  ```
- Pagination format: `?page=1&per_page=20`
- Filtering via query params: `?status=verified&date_from=2026-01-01`
- API versioning: `/api/v1/`

### Git Workflow

- **Main branch:** `main` (production-ready)
- **Development branch:** `develop` (integration)
- **Feature branches:** `feature/description` (from `develop`)
- **Bugfix branches:** `fix/description` (from `develop`)
- **Pull requests** required for all merges to `develop` and `main`

### Environment Variables

Each service uses `.env` files. Template provided as `.env.example`.

```env
# API Service
DATABASE_URL=postgresql://user:pass@host:5432/smartform
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
R2_ACCOUNT_ID=your-account-id
R2_ACCESS_KEY_ID=your-key
R2_SECRET_ACCESS_KEY=your-secret
R2_BUCKET_NAME=smartform-uploads
R2_ENDPOINT_URL=https://your-account.r2.cloudflarestorage.com
OPENAI_API_KEY=your-openai-key  # For GPT-4o Vision fallback
```

---

## 18. Deployment Strategy

### Primary: Docker-Based (Portable)

All services containerized for consistent deployment across environments.

#### Development

```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```

- Hot-reloading for frontend and backend
- Local PostgreSQL and Redis containers
- Volume mounts for code changes

#### Production Options

| Option | Setup | Cost | Best For |
|---|---|---|---|
| **AWS (EC2 + Docker)** | Single EC2 instance running Docker Compose | ~$10–20/mo (t3.small) | Cloud deployment |
| **VPS (Hetzner/DigitalOcean)** | Docker Compose on VPS | ~$5–15/mo | Budget-friendly cloud |
| **On-Premise** | Docker on City Hall server | Hardware cost only | Data sovereignty |

#### Recommended MVP Deployment

- **1 VPS** (4GB RAM, 2 vCPU) running Docker Compose
- **Supabase** for PostgreSQL (free tier)
- **Cloudflare R2** for file storage (free tier)
- **Cloudflare** for DNS + CDN (free tier)
- **Total cost: ~$5–15/month**

---

## 19. Reporting Module

### MVP Reports

| Report | Description | Export |
|---|---|---|
| Daily Summary | Forms processed today, by status, by encoder | CSV |
| Monthly Summary | Forms processed this month, trends, totals | CSV |
| Form List | Filterable list of all form entries | CSV |

### Filters

- Date range (from, to)
- Department
- Form template type
- Status (uploaded, processing, extracted, verified, archived)
- Encoder (admin only)

---

## 20. Security & Compliance

### Security Measures

- **HTTPS** enforced (TLS 1.2+)
- **JWT** with short expiry + refresh tokens
- **bcrypt** password hashing (12 rounds)
- **CORS** restricted to frontend domain only
- **Rate limiting** on auth endpoints (5 attempts/minute)
- **Input sanitization** on all user inputs
- **SQL injection protection** via SQLAlchemy parameterized queries
- **File validation** (type, size limits: max 10MB per image)
- **Audit logging** for all data modifications

### Philippine Data Privacy Act (RA 10173) Compliance

- Personal data encrypted at rest (Supabase encryption + R2 encryption)
- Access restricted by role-based permissions
- Audit trail for all data access and modifications
- Data retention policies configurable per form type
- Right to erasure support (soft delete + hard delete after retention)
- Privacy impact assessment documentation

---

## 21. Performance Targets

| Metric | Target | How |
|---|---|---|
| OCR extraction | < 5 seconds | PaddleOCR optimized, GPU optional |
| Image upload | < 3 seconds | Direct-to-R2 pre-signed upload |
| Page load | < 2 seconds | Next.js SSR + code splitting |
| Verification save | < 1 second | Optimistic UI + async DB write |
| Report generation | < 5 seconds | Pre-computed aggregations + Redis cache |
| Concurrent users | 20+ | Async FastAPI + connection pooling |

---

## 22. Risk & Mitigation

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Poor OCR on messy handwriting | High | High | GPT-4o fallback, human verification as safety net |
| Supabase free tier limits | Medium | Medium | Monitor usage, upgrade plan or migrate to self-hosted |
| GPT-4o API costs spike | Medium | Low | Budget cap, rate limiting, batch processing |
| City Hall internet outage | High | Medium | PaddleOCR runs offline, queue uploads for sync |
| Data breach | Critical | Low | Encryption, RBAC, audit logs, compliance measures |
| Scope creep | Medium | High | Strict MVP scope, Phase 2/3 boundaries |
| Team availability | Medium | Medium | Modular architecture allows parallel work |

---

## 23. Future Roadmap

### Post-MVP Enhancements

- ~~Template learning (AI improves per form type over time)~~ → **Moved to Phase 4 (ML Training Pipeline)**
- Multi-department support with department-specific dashboards
- Analytics dashboard with trend visualization
- Mobile-optimized upload app (PWA or React Native)
- Batch processing (upload folder of scanned forms)
- Barcode/QR code reading for form identification
- Integration with existing City Hall systems (ERP, accounting)
- Multi-language OCR improvement (Tagalog, Bisaya, etc.)
- Barangay-level deployments
- Full LGU digital operations suite

---

## Appendix: Tech Requirements Summary

### Development Machine

- Node.js 20 LTS
- Python 3.12
- Docker Desktop / Docker Engine + Docker Compose
- Git
- Code editor (VS Code recommended)

### Production Server (Minimum)

- 4GB RAM
- 2 vCPU
- 40GB SSD
- Ubuntu 22.04 LTS or similar
- Docker Engine + Docker Compose

### External Services (Free Tier)

| Service | Purpose | Free Tier Limit |
|---|---|---|
| Supabase | PostgreSQL database | 500MB, 2 projects |
| Cloudflare R2 | Image storage | 10GB storage, 10M reads/mo |
| OpenAI API | GPT-4o Vision (fallback OCR) | Pay-per-use (~$0.01–0.03/page) |

---

## 24. ML Training Pipeline (OCR Accuracy)

### Overview

A Google Colab-based ML training pipeline that uses human-verified form data to iteratively
improve OCR accuracy. The system creates a **continuous learning loop**: forms are verified by
human encoders → corrections become labeled training data → ML models are fine-tuned →
future extractions become more accurate → fewer corrections needed.

**Core Principle:** Every human correction makes the system smarter.

### Why This Pipeline

| Problem | Solution |
|---|---|
| Generic PaddleOCR not optimized for PH handwriting | Fine-tune OCR recognition model on collected samples |
| LLM API dependency for field mapping (cost, latency, rate limits) | Train local LayoutLMv3 model (free, fast, offline) |
| No learning from human corrections | Continuous feedback loop from verified data |
| Inconsistent accuracy across form templates | Per-template model specialization |

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PRODUCTION SYSTEM                         │
│                                                             │
│  Upload → OCR → Human Verify → Save (ocr_value + verified) │
│                                    │                        │
│                                    ▼                        │
│                           Training Data Pool                │
│                          (form_fields table:                │
│                           ocr_value vs verified_value)      │
└──────────────────────────────┬──────────────────────────────┘
                               │ Export API
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    GOOGLE COLAB PIPELINE                     │
│                                                             │
│  ┌──────────┐  ┌────────────┐  ┌───────────┐  ┌─────────┐  │
│  │ 01 Data   │→│ 02 Preproc │→│ 03 Layout  │→│ 04 OCR  │  │
│  │ Export    │  │ Experiment │  │ Detection  │  │ Finetune│  │
│  └──────────┘  └────────────┘  └───────────┘  └─────────┘  │
│                                                             │
│  ┌──────────┐  ┌────────────┐  ┌───────────────────────┐   │
│  │ 05 Field  │→│ 06 Post    │→│ 07 Evaluation +       │   │
│  │ Mapping   │  │ Correction │  │ Benchmark             │   │
│  └──────────┘  └────────────┘  └───────────────────────┘   │
│                                         │                   │
│                                         ▼                   │
│                                  Trained Model Artifacts    │
│                                  (ONNX / safetensors)       │
└─────────────────────────────────────────┬───────────────────┘
                                          │ Deploy
                                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    OCR WORKER (Updated)                      │
│                                                             │
│  Fine-tuned PaddleOCR → LayoutLMv3 Field Mapper → Results  │
│  (replaces generic OCR)  (replaces Groq API calls)         │
└─────────────────────────────────────────────────────────────┘
```

### Colab Notebooks

| Notebook | Purpose | Key Libraries |
|---|---|---|
| `01_data_export.ipynb` | Download verified entries (images + field labels) from DB/API as training dataset | `requests`, `psycopg2`, `boto3` |
| `02_preprocessing_experiments.ipynb` | Compare preprocessing techniques: deskew, denoise, binarization, contrast enhancement | `OpenCV`, `PIL`, `scikit-image` |
| `03_layout_detection.ipynb` | Train YOLOv8 to detect field bounding boxes on specific PH City Hall form types | `ultralytics`, `roboflow` |
| `04_ocr_finetuning.ipynb` | Fine-tune PaddleOCR recognition model on Philippine handwriting samples | `paddleocr`, `paddlepaddle-gpu` |
| `05_field_mapping_model.ipynb` | Train LayoutLMv3 to map OCR text → form field names (replaces LLM API calls) | `transformers`, `datasets`, `torch` |
| `06_post_correction.ipynb` | Train text correction model for Filipino/English names, addresses, common form terms | `transformers` (T5), custom rules |
| `07_evaluation.ipynb` | Benchmark accuracy: field-level accuracy, CER, WER per template; compare old vs new | `editdistance`, `sklearn`, custom metrics |

### Training Data Source

The `form_fields` table already contains the labeled data:

| Column | Role |
|---|---|
| `ocr_value` | Model input (what OCR extracted) |
| `verified_value` | Ground truth label (what the human confirmed) |
| `was_corrected` | Flag for error analysis (which fields need improvement) |
| `confidence` | Current model's self-reported certainty |
| `field_name` | Target label for field classification |

Linked via `form_entries` → `form_templates` for template-specific training.

### ML Models

| Model | Purpose | Replaces |
|---|---|---|
| **Fine-tuned PaddleOCR** | Better handwriting recognition for PH forms | Generic PaddleOCR |
| **YOLOv8** | Field region detection (bounding boxes) | Manual template regions |
| **LayoutLMv3** | Field classification (text + spatial layout → field name) | Groq/LLM API calls |
| **T5 / Rule-based** | Post-OCR text correction (Filipino names, addresses) | None (new capability) |

### Data Export API

```
GET /api/v1/ml/export-training-data?template_id=xxx&status=verified&limit=1000
```

Returns:
```json
{
  "entries": [
    {
      "entry_id": "uuid",
      "template_name": "Business Permit Application",
      "image_url": "presigned-download-url",
      "fields": [
        {
          "field_name": "business_name",
          "ocr_value": "JOLLIBEE FOODS",
          "verified_value": "JOLLIBEE FOODS CORP.",
          "was_corrected": true,
          "confidence": 0.72
        }
      ]
    }
  ],
  "total": 150,
  "export_date": "2026-03-05"
}
```

### Evaluation Metrics

| Metric | Description | Target |
|---|---|---|
| **Field Accuracy** | % of fields where OCR value matches verified value exactly | > 85% |
| **Character Error Rate (CER)** | Edit distance / total characters per field | < 5% |
| **Word Error Rate (WER)** | Edit distance at word level | < 10% |
| **Template Accuracy** | Per-template breakdown of field accuracy | Track per template |
| **Correction Rate** | % of fields requiring human correction | < 15% |

### Integration Points

Trained models integrate back into the existing codebase:

| File | Change |
|---|---|
| `backend/app/services/ocr_service.py` → `_get_paddle_ocr()` | Load fine-tuned PaddleOCR model instead of generic |
| `backend/app/services/ocr_service.py` → `_map_fields_with_ai()` | Replace with local LayoutLMv3 inference |
| `backend/app/services/ocr_service.py` → new `_post_correct()` | Add post-OCR text correction step |
| `backend/app/api/v1/` → new `ml.py` | Training data export endpoint |
| `backend/app/config.py` | Add ML model path settings |

### Resource Requirements

| Resource | Source | Cost |
|---|---|---|
| GPU for training | Google Colab (free T4 GPU) | Free |
| Training data | Existing verified entries in production DB | Free |
| Model storage | Cloudflare R2 or Git LFS | Free tier |
| Colab Pro (optional) | Faster GPUs, longer sessions | ~$10/month |

---

---

## Appendix: Agent Instructions Sync

The AI agent instructions file at `.github/copilot-instructions.md` is a condensed version
of this project plan. It provides agents with the context they need to follow the project's
architecture, rules, and constraints.

**When updating this project plan, always update `.github/copilot-instructions.md` to reflect the changes.**

---

## Appendix: Progress Tracking Rule

**Every time implementation progress is made, the agent MUST:**

1. Update the checkboxes in [Section 16: Implementation Plan](#16-implementation-plan) — mark completed items with `[x]`.
2. Update the **Progress Log** below with a dated summary of what was done.
3. Update `.github/copilot-instructions.md` if any architectural decisions, rules, or tech stack changes occurred.

This ensures the project plan is always the single source of truth for project status.

---

## Appendix: Progress Log

| Date | Summary |
|---|---|
| 2026-03-04 | Project plan created. Backend API service scaffolded (FastAPI, SQLAlchemy models, JWT auth, form CRUD endpoints, Pydantic schemas, services layer). Frontend scaffolded (Next.js Pages Router, 4-layer architecture, Redux Toolkit, Axios client with auto-refresh, login page, dashboard page). Docker Compose configured (PostgreSQL, Redis, API, Web). All dependencies installed. |
| 2026-03-04 | Environment configured: PostgreSQL connected (localhost), Redis installed, Cloudflare R2 verified (smart-form-encoder bucket), Groq API connected (Llama 4 Scout). Alembic initial migration applied (5 tables). Admin user seeded + 3 form templates (Business Permit, Cedula, Barangay Clearance). R2 storage service built (upload, presigned URL, delete). OCR pipeline implemented: Celery task → PaddleOCR extraction → field mapping → Groq Vision enhancement for low-confidence fields. Frontend: upload page (drag-and-drop, template selection), forms list page (with status/confidence), verification page (side-by-side image + editable OCR fields with confidence highlighting). Full end-to-end API verified (login, templates, upload). |
| 2026-03-04 | OCR pipeline end-to-end tested: upload → R2 storage → Celery worker → PaddleOCR extraction → field mapping → DB save (status: extracted). Added PDF-to-image conversion (PyMuPDF). Fixed PaddleOCR v2.x/v3.x compatibility (pinned to 2.10.0). Fixed SQLAlchemy lazy-loading in upload endpoint. Fixed Celery task discovery (autodiscover). Created 3 sample form markdown templates (Business Permit, Cedula, Barangay Clearance) for screenshot-based OCR testing. |
| 2026-03-04 | Upgraded OCR field mapping from naive label-matching to AI-powered extraction (Groq Llama 4 Scout). New pipeline: PaddleOCR extracts raw text → Groq AI maps text+image to structured fields (handles table layouts, multi-line addresses, complex forms). Naive matching kept as fallback. Created backend start script (start-backend.sh). Cleared test data for fresh re-test. |
| 2026-03-05 | **Architecture pivot: Data-driven DynamicFormRenderer.** Replaced side-by-side verification with editable digital form replicas. Created `FormLayoutSchema` types (sections, field widths, headers/footers). Updated 3 seed templates with rich layout schemas. Built `DynamicFormRenderer` component (paper-like rendering, section grouping, confidence badges, grid layout). Rewrote `[id].tsx` verification page to use DynamicFormRenderer with toggleable reference image panel. Added `GET /templates/{id}` and `POST /templates` backend endpoints. Built AI template generator: `POST /templates/generate` accepts sample form image → Groq Vision analyzes layout → returns FormLayoutSchema JSON. Created admin template builder page (`/templates/create`) with upload → AI generate → preview → edit → save workflow. |
| 2026-03-05 | **ML Training Pipeline planned (Section 24).** Designed Google Colab-based ML training pipeline for OCR accuracy improvement. Architecture: continuous learning loop from human-verified data → 7 Colab notebooks (data export, preprocessing, layout detection, OCR fine-tuning, field mapping, post-correction, evaluation). Models: fine-tuned PaddleOCR, YOLOv8 for layout detection, LayoutLMv3 for field mapping (replaces LLM API), T5 for post-correction. Added Phase 4 to implementation plan. Added training data export API design. |
| 2026-03-05 | **ML Training Pipeline implemented (Phase 4A).** Built 3 backend ML endpoints (admin-only): training data export, training stats, evaluation metrics — registered on `/api/v1/ml/`. Created all 7 Colab notebooks with full implementations: `01_data_export` (API auth, batch fetch, image download), `02_preprocessing_experiments` (13 preprocessing methods, PaddleOCR benchmark, CER/WER comparison), `03_layout_detection` (YOLOv8 training, annotation tools, data augmentation, ONNX export), `04_ocr_finetuning` (PaddleOCR rec fine-tuning on PH handwriting, baseline comparison), `05_field_mapping_model` (LayoutLMv3 token classification, BIO labeling, seqeval metrics), `06_post_correction` (rule-based + dictionary + T5 seq2seq correction pipeline, synthetic error generation, evaluation), `07_evaluation` (CER/WER/exact match, per-template/per-field breakdown, confidence calibration). Prepared sample training data: DTI-BNR form image + 46-field ground truth JSON. |

---

*Document Version: 1.7*
*Created: March 4, 2026*
*Last Updated: March 5, 2026 (Session 7 — ML Notebooks Implementation)*
