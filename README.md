# AI Resume Analyzer & Job Matcher

<div align="center">

![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Next.js](https://img.shields.io/badge/next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![React](https://img.shields.io/badge/React_19-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS_v4-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)
![Google Gemini](https://img.shields.io/badge/Google_Gemini_AI-4285F4?style=for-the-badge&logo=google&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB_Atlas-4EA94B?style=for-the-badge&logo=mongodb&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)

**An enterprise-grade, privacy-conscious AI Resume Analyzer, ATS Scorer, and Job-Matching SaaS platform.**

Developed with ❤️ by **Divyanshu Tailor**

[Features](#key-features) • [Architecture](#system-architecture) • [Tech Stack](#tech-stack) • [Quick Start](#getting-started) • [API Documentation](#api-reference) • [Configuration](#environment-variables)

</div>

---

## 📌 Overview

**AI Resume Analyzer** is a modern, full-stack application built to empower job seekers with objective, actionable resume evaluation and job alignment insights. Combining the semantic reasoning of **Google Gemini AI** with **deterministic, rubric-based ATS scoring**, the platform guarantees reliable, explainable metrics without hallucinations.

In addition to deep analysis, it provides **job-description semantic matching**, **factually grounded bullet-point rewriting**, and **format-preserving document optimization** (retaining original Word DOCX typography and layout).

---

## ✨ Key Features

### 📄 Intelligent Resume Ingestion & Classification
- **Multi-Format Parsing:** High-fidelity text extraction from both **PDF** (via PyMuPDF) and **DOCX** (via `python-docx`).
- **Universal Resume Classifier:** Validates document eligibility before quota consumption or deep analysis using Gemini. Rejects non-resume documents and requests clearer formats when uncertain.
- **Cross-Domain Adaptability:** Seamlessly handles resumes and CVs across engineering, healthcare, education, finance, marketing, and skilled trades.

### 🧠 Structured AI Extraction & Deterministic ATS Scoring
- **Rich Schema Extraction:** Maps raw resume text into typed schemas including candidate contact info, executive summary, categorized skills (technical, soft, tools), chronological work experience with quantifiable accomplishments, education, and projects.
- **100-Point Deterministic Rubric:** Transparent, reproducible ATS scoring assessing:
  - Section completeness and contact clarity
  - Action verb presence and active voice
  - Quantifiable metrics and impact indicators
  - Skill depth and categorized proficiency
  - Formatting and layout hygiene
- **Explainable Feedback:** Identifies top strengths, critical weaknesses, missing competencies, and prioritized improvements.

### 🎯 Semantic Job Description Matching
- **Ground-Truth Semantic Alignment:** Compares structured resume capabilities against target job descriptions.
- **Gap Analysis:** Pinpoints missing required skills, preferred qualifications, and domain tools.
- **Seniority & Experience Checking:** Evaluates role levels and years of experience against JD expectations.

### 🛠️ Format-Preserving Document Optimization
- **Fact-Grounded Bullet Rewriter:** Enhances resume achievements tailored to target roles while strictly prohibiting hallucination or fabrication of credentials, metrics, and dates.
- **In-Place DOCX Optimization:** Updates matched bullet points directly within the user's original Word document, preserving existing fonts, font sizes, colors, margins, headers, footers, and table layouts.
- **ATS Clean PDF/DOCX Export:** Generates clean, parser-friendly documents stored securely in MongoDB GridFS with atomic download tokens and automated 3-day retention policies.

### 🔒 Enterprise-Grade Security & Authentication
- **Dual Authentication Paths:** Email/password with salted PBKDF2 hashing, plus Google OAuth 2.0 (Authorization Code flow with signed HttpOnly state cookies).
- **Hardened Cookies:** Signed, HttpOnly, SameSite=Lax session management (Strict HTTPS enforcement in production).
- **HMAC Rate Limiting:** Sliding-window rate limiters per route group (`auth` and `analysis`) to prevent abuse and DDoS.
- **Abuse-Resistant Quotas:** Server-authoritative anonymous quota (2 free analyses via signed HttpOnly cookies and HMAC-hashed IP fallbacks) and unlimited accounts for signed-in users.
- **Privacy First:** Application logs never contain passwords, tokens, OAuth codes, raw IP addresses, or personal resume text. Authenticated users can permanently delete their application history at any time.

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    Client["Next.js 16 Frontend\n(React 19, Tailwind CSS v4)"]
    
    subgraph FastAPI Backend
        Gatekeeper["Security Middleware\n(HMAC Rate Limiter & Headers)"]
        Parser["Document Parser\n(PyMuPDF & python-docx)"]
        Classifier["Eligibility Classifier\n(Google Gemini)"]
        Extractor["Structured Extractor\n(Google Gemini)"]
        Scorer["Deterministic ATS Scorer\n(100-Point Rubric Engine)"]
        Matcher["Job Matcher Engine\n(Semantic & Domain Evidences)"]
        Optimizer["Document Optimizer\n(In-Place DOCX & GridFS Storage)"]
    end
    
    Database[("MongoDB Atlas\n(Auth, Sessions, History & GridFS)")]
    GeminiAPI["Google Gemini AI API"]

    Client -->|HTTP / REST with HttpOnly Cookies| Gatekeeper
    Gatekeeper --> Parser
    Parser --> Classifier
    Classifier -->|Verify Eligibility| GeminiAPI
    Classifier --> Extractor
    Extractor -->|Structured Extraction| GeminiAPI
    Extractor --> Scorer
    Scorer --> Database
    Client -->|Match Resume with Job Description| Matcher
    Matcher --> Database
    Client -->|Generate Optimized Document| Optimizer
    Optimizer --> Database
    Database -->|Stream Secure Download| Client
```

---

## 💻 Tech Stack

### Frontend
- **Framework:** [Next.js 16](https://nextjs.org/) (App Router)
- **Library:** [React 19](https://react.dev/)
- **Language:** [TypeScript](https://www.typescriptlang.org/)
- **Styling:** [Tailwind CSS v4](https://tailwindcss.com/)
- **Icons:** [Lucide React](https://lucide.dev/)

### Backend
- **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.12+)
- **Server:** [Uvicorn](https://www.uvicorn.org/)
- **Validation:** [Pydantic v2](https://docs.pydantic.dev/)
- **Document Processing:** [PyMuPDF](https://pymupdf.readthedocs.io/) & [python-docx](https://python-docx.readthedocs.io/)
- **HTTP Client:** [HTTPX](https://www.python-httpx.org/)

### Artificial Intelligence
- **LLM Provider:** [Google Gemini API](https://ai.google.dev/) via `google-genai` SDK

### Database & Storage
- **Database:** [MongoDB Atlas](https://www.mongodb.com/atlas) (PyMongo)
- **File Storage:** MongoDB GridFS (Isolated `original_resume_files` and `optimized_resume_files` buckets)

---

## 📂 Repository Structure

```text
ai-resume-analyzer/
├── backend/
│   ├── app/
│   │   ├── core/           # Configuration, environment loading, production validation
│   │   ├── models/         # Pydantic models and database representations
│   │   ├── schemas/        # Request and response schemas
│   │   ├── services/       # Core business logic:
│   │   │   ├── ai_service.py               # Gemini extraction service
│   │   │   ├── auth.py                     # PBKDF2 hashing and session management
│   │   │   ├── bullet_improver.py          # Grounded AI bullet rewriting
│   │   │   ├── job_matcher.py              # Semantic job alignment
│   │   │   ├── optimized_resume_documents.py# DOCX formatting preservation
│   │   │   ├── persistence.py              # MongoDB & GridFS repository layer
│   │   │   ├── rate_limit.py               # HMAC sliding-window limiter
│   │   │   ├── resume_analyzer.py          # 100-point rubric scoring engine
│   │   │   ├── resume_classifier.py        # Universal eligibility classifier
│   │   │   └── resume_parser.py            # PDF & DOCX text extraction
│   │   └── main.py         # FastAPI application routes & middleware
│   ├── tests/              # Test suites, evaluation fixtures, and validation runners
│   ├── .env.example        # Environment variable template for backend
│   └── requirements.txt    # Python dependencies
│
├── frontend/
│   ├── app/                # Next.js App Router:
│   │   ├── dashboard/      # Authenticated user dashboard & analyzer workspace
│   │   ├── login/          # User login page
│   │   ├── signup/         # User registration page
│   │   ├── layout.tsx      # Root layout & providers
│   │   └── page.tsx        # Public landing page with live analyzer
│   ├── components/         # Reusable UI components (AuthGate, PasswordField, etc.)
│   ├── lib/                # API client functions & TypeScript interfaces
│   ├── public/             # Static SVGs and web assets
│   ├── package.json        # Frontend scripts and npm dependencies
│   └── tsconfig.json       # TypeScript configuration
│
├── .gitignore              # Git ignore rules
└── README.md               # Main project documentation
```

---

## 🚀 Getting Started

### Prerequisites

Ensure you have the following installed on your machine:
- **Python 3.12+**
- **Node.js 20+** and **npm**
- **MongoDB** (Local instance or [MongoDB Atlas](https://www.mongodb.com/atlas) cluster)
- **Google Gemini API Key** (obtainable from [Google AI Studio](https://aistudio.google.com/))

---

### 1. Backend Setup

1. **Navigate to the backend directory:**
   ```bash
   cd backend
   ```

2. **Create and activate a virtual environment:**
   - **Windows:**
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and fill in your credentials (see [Configuration](#environment-variables)).

5. **Start the FastAPI server:**
   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   The backend will be available at `http://127.0.0.1:8000`. You can inspect the interactive OpenAPI documentation at `http://127.0.0.1:8000/docs`.

---

### 2. Frontend Setup

1. **Navigate to the frontend directory:**
   ```bash
   cd ../frontend
   ```

2. **Install npm dependencies:**
   ```bash
   npm install
   ```

3. **Start the development server:**
   ```bash
   npm run dev
   ```

4. **Launch the application:**
   Open your browser and visit `http://localhost:3000`.

---

## ⚙️ Environment Variables

The backend requires the following configuration in `backend/.env`:

| Variable | Description | Example / Default |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Google Gemini API Key | `AIzaSy...` |
| `MONGODB_URI` | MongoDB connection string | `mongodb+srv://user:pass@cluster.mongodb.net/` |
| `MONGODB_DATABASE` | Database name | `ai_resume_analyzer` |
| `AUTH_SECRET` | Secret key for signing sessions and HMAC tokens (32+ chars) | `your-secure-random-32-byte-secret` |
| `APP_ENV` | Application environment (`development` or `production`) | `development` |
| `FRONTEND_ORIGINS` | Allowed CORS origins (comma-separated for multiples) | `http://localhost:3000` |
| `MAX_UPLOAD_BYTES` | Maximum allowed upload file size in bytes | `5242880` (5 MB) |
| `MAX_RESUME_TEXT_CHARS` | Upper bound for extracted text characters | `200000` |
| `AUTH_RATE_LIMIT` | Auth routes requests per minute limit | `20` |
| `ANALYSIS_RATE_LIMIT` | Analysis routes requests per minute limit | `12` |
| `GOOGLE_CLIENT_ID` | *(Optional)* Google OAuth 2.0 Client ID | `your-google-client-id` |
| `GOOGLE_CLIENT_SECRET` | *(Optional)* Google OAuth 2.0 Client Secret | `your-google-client-secret` |
| `GOOGLE_OAUTH_REDIRECT_URI`| *(Optional)* Google OAuth Redirect URI | `http://localhost:8000/api/auth/google/callback` |

---

## 📡 API Reference

### 🔐 Authentication & Session
- `POST /api/auth/signup` — Create a new account with email, name, and password.
- `POST /api/auth/login` — Sign in and receive a secure HttpOnly session cookie.
- `POST /api/auth/logout` — Invalidate and clear session cookie.
- `GET /api/auth/me` — Retrieve the currently authenticated user and usage status.
- `GET /api/auth/google` — Initiate Google OAuth 2.0 flow.
- `GET /api/auth/google/callback` — Google OAuth redirect handler.

### 📄 Resume Analysis & Scoring
- `POST /api/resume/upload` — Upload PDF/DOCX file and extract raw text.
- `POST /api/resume/structure` — Extract structured candidate data using Gemini.
- `POST /api/resume/analyze` — Complete upload, classification, and structured extraction in one step.
- `POST /api/resume/analyze-score` — Compute 100-point ATS score and store analysis in database.
- `GET /api/usage` — Check remaining anonymous analyses or authenticated account status.

### 🎯 Job Matching & Document Optimization
- `POST /api/resume/match` — Compare structured resume with job description.
- `POST /api/resume/optimize` — Generate prioritized bullet-level improvement recommendations.
- `POST /api/resume/improve-bullet` — Factually grounded AI rewrite for an individual bullet point.
- `POST /api/resume/optimize-document` — Apply approved changes and generate format-preserved DOCX.
- `GET /api/optimized-resumes/{id}/{format}` — Stream optimized resume download (authenticated with ownership check).

### 🗄️ History & System Health
- `GET /api/history` — Fetch user's saved analysis, match, and optimization history.
- `DELETE /api/history` — Permanently purge user's history and associated GridFS files.
- `GET /api/health` — Application health status check.
- `GET /api/ready` — MongoDB readiness ping.

---

## 🛡️ Security & Privacy Guarantees

1. **Zero Hallucination Scoring:** The ATS score is strictly computed via a documented, deterministic 100-point algorithm. AI is used solely for qualitative semantic parsing, never for deciding numeric marks.
2. **Factual Grounding:** Bullet-point rewrites strictly reject fabricating companies, dates, degrees, certifications, or imaginary metrics.
3. **Data Isolation:** User documents stored in GridFS are strictly private and query-scoped by `user_id` with time-bound retention rules.
4. **Credential Protection:** Passwords use salted PBKDF2 hashes; OAuth tokens and secrets are processed server-side only and are never forwarded to the client.

---

## 👤 Author

**Divyanshu Tailor**
- GitHub: [@Gh-divyansh](https://github.com/Gh-divyansh)

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
