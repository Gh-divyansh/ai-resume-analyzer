# AI Resume Analyzer frontend

Next.js dashboard for the AI Resume Analyzer. It uploads a PDF or DOCX resume to the FastAPI backend, then presents the structured resume and score feedback returned by the existing API.

## Run locally

1. Start the backend at `http://127.0.0.1:8000`.
2. From this directory, run `npm run dev`.
3. Open `http://localhost:3000`.

## Dashboard data

The frontend preserves the existing two-call workflow:

1. `POST /api/resume/analyze` extracts and structures the uploaded resume.
2. `POST /api/resume/analyze-score` returns the analysis result.

No candidate information is fabricated in the UI. Missing fields are shown as unavailable.
