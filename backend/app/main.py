import logging

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Response, Request, Cookie
from pymongo.errors import DuplicateKeyError
from fastapi.middleware.cors import CORSMiddleware

from app.services.resume_parser import (
    extract_text_from_pdf,
    extract_text_from_docx,
)

from app.services.ai_service import extract_resume_data
from app.services.resume_classifier import ResumeClassificationError, classify_resume_document
from app.services.resume_analyzer import analyze_resume as calculate_resume_score
from app.services.job_matcher import match_resume_to_job
from app.services.universal_ai_matcher import match_resume_to_job_universal
from app.services.resume_optimizer import generate_resume_optimizations
from app.services.resume_document_optimizer import ResumeDocumentOptimizationError, optimize_resume_for_job
from app.services.optimized_resume_documents import (
    DocumentPreservationError,
    render_ats_docx,
    render_docx_preserving_format,
)
from app.schemas.optimizer import ResumeOptimizationResponse
from app.services.bullet_improver import (
    BulletImprovementGenerationError,
    improve_resume_bullet,
)
from app.schemas.bullet_improvement import BulletImprovementResponse
from app.services.auth import hash_password, verify_password, token, current_user, optional_user
from app.services.persistence import repo
from app.core.config import AUTH_COOKIE_SECURE, FRONTEND_ORIGINS, MAX_UPLOAD_BYTES, MAX_RESUME_TEXT_CHARS, validate_production_config

import tempfile
import os
import hashlib
import hmac
import secrets
import httpx
import time
import uuid
from urllib.parse import urlencode
from app.core.config import AUTH_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI
from app.core.config import AUTH_RATE_LIMIT, ANALYSIS_RATE_LIMIT
from app.services.rate_limit import rate_limiter


LOGGER = logging.getLogger(__name__)


app = FastAPI(
    title="AI Resume Analyzer API",
    description="Backend API for the AI Resume Analyzer",
    version="0.1.0",
)

@app.on_event("startup")
def production_startup_validation():
    validate_production_config()

@app.middleware("http")
async def security_headers(request: Request, call_next):
    started = time.perf_counter()
    request_id = uuid.uuid4().hex
    rate_group = (
        "auth" if request.url.path.startswith("/api/auth/") else
        "analysis" if request.url.path in {"/api/resume/analyze", "/api/resume/analyze-score", "/api/resume/improve-bullet", "/api/resume/match-ai"} else
        None
    )
    if rate_group:
        limit = AUTH_RATE_LIMIT if rate_group == "auth" else ANALYSIS_RATE_LIMIT
        remote_ip = request.client.host if request.client else "unknown"
        secret = (AUTH_SECRET or "development-rate-limit").encode()
        key = hmac.new(secret, f"{rate_group}:{remote_ip}".encode(), hashlib.sha256).hexdigest()
        if not rate_limiter.allow(key, limit, 60):
            from fastapi.responses import JSONResponse
            LOGGER.warning("event=rate_limit_rejected route=%s group=%s request_id=%s", request.url.path, rate_group, request_id)
            return JSONResponse(status_code=429, content={"detail": "Too many requests. Please try again shortly."}, headers={"Retry-After": "60", "X-Request-ID": request_id})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Request-ID"] = request_id
    if response.status_code >= 500:
        LOGGER.warning("event=server_error route=%s status=%s request_id=%s duration_ms=%d", request.url.path, response.status_code, request_id, (time.perf_counter() - started) * 1000)
    return response

def _anonymous_identity(request: Request, anonymous_visitor: str | None):
    """Return non-reversible quota keys; the client never supplies a trusted count."""
    visitor = None
    if anonymous_visitor:
        try:
            candidate, signature = anonymous_visitor.rsplit(".", 1)
            signing_secret = (AUTH_SECRET or "development-anonymous-quota").encode()
            expected = hmac.new(signing_secret, candidate.encode(), hashlib.sha256).hexdigest()
            if hmac.compare_digest(signature, expected):
                visitor = candidate
        except ValueError:
            pass
    visitor = visitor or secrets.token_urlsafe(32)
    remote_ip = request.client.host if request.client else "unknown"
    secret = (AUTH_SECRET or "development-anonymous-quota").encode()
    digest = lambda value: hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()
    return visitor, digest(f"visitor:{visitor}"), digest(f"ip:{remote_ip}")

def _set_anonymous_cookie(response: Response, visitor: str):
    secret = (AUTH_SECRET or "development-anonymous-quota").encode()
    signed_visitor = f"{visitor}.{hmac.new(secret, visitor.encode(), hashlib.sha256).hexdigest()}"
    response.set_cookie("anonymous_visitor", signed_visitor, httponly=True, samesite="lax",
                        secure=AUTH_COOKIE_SECURE, max_age=60 * 60 * 24 * 30)

def _signed_value(value: str):
    secret=(AUTH_SECRET or "development-anonymous-quota").encode()
    return f"{value}.{hmac.new(secret,value.encode(),hashlib.sha256).hexdigest()}"

def _verified_value(value: str | None):
    if not value: return None
    try:
        raw, signature=value.rsplit(".",1)
        return raw if hmac.compare_digest(_signed_value(raw), value) else None
    except ValueError: return None

def _oauth_frontend_redirect(error: str | None = None):
    frontend = FRONTEND_ORIGINS[0].rstrip("/")
    # Successful authentication resumes the analyzer. Errors return to an auth
    # page that can show a safe, actionable message without leaking provider data.
    return f"{frontend}/login?oauth_error={error}" if error else f"{frontend}/dashboard/analyzer"


def _session_cookie(response: Response, user_id: str) -> None:
    """Issue a new signed session after every successful authentication event."""
    response.set_cookie("session", token(user_id), httponly=True, samesite="lax", secure=AUTH_COOKIE_SECURE, max_age=604800)

@app.post("/api/auth/signup")
def signup(payload: dict, response: Response):
    email = str(payload.get("email", "")).strip().casefold(); password = payload.get("password", ""); name = str(payload.get("name", "")).strip()
    if not name or len(name) > 120: raise HTTPException(400, "Use a valid name.")
    if len(email) > 254 or "@" not in email or not isinstance(password, str) or not 8 <= len(password) <= 256: raise HTTPException(400, "Use a valid email and an 8–256 character password.")
    try: user = repo().create_user(email, hash_password(password), name)
    except DuplicateKeyError: raise HTTPException(409, "An account with that email already exists.")
    _session_cookie(response, str(user["_id"]))
    LOGGER.info("event=auth_signup_success")
    return {"user":{"id":str(user["_id"]),"email":email},"usage":{"analysis_count":0,"limit":None,"authenticated":True}}

@app.post("/api/auth/login")
def login(payload: dict, response: Response):
    email = str(payload.get("email", "")).strip().casefold(); password = payload.get("password", "")
    if len(email) > 254 or not isinstance(password, str) or len(password) > 256:
        raise HTTPException(401,"Invalid email or password.")
    user=repo().user_by_email(email)
    if not user or not user.get("password_hash") or not verify_password(password,user["password_hash"]): raise HTTPException(401,"Invalid email or password.")
    _session_cookie(response, str(user["_id"]))
    LOGGER.info("event=auth_login_success")
    return {"user":{"id":str(user["_id"]),"email":user["email"]},"usage":{"analysis_count":0,"limit":None,"authenticated":True}}

@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie("session", httponly=True, samesite="lax", secure=AUTH_COOKIE_SECURE)
    LOGGER.info("event=auth_logout")
    return {"ok":True}

@app.get("/api/auth/google")
def google_login():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not GOOGLE_OAUTH_REDIRECT_URI:
        raise HTTPException(503,"Google sign-in is not configured.")
    state=secrets.token_urlsafe(32)
    query=urlencode({"client_id":GOOGLE_CLIENT_ID,"redirect_uri":GOOGLE_OAUTH_REDIRECT_URI,"response_type":"code","scope":"openid email profile","state":state,"prompt":"select_account"})
    from fastapi.responses import RedirectResponse
    redirect=RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{query}")
    redirect.set_cookie("oauth_state", _signed_value(state), httponly=True, samesite="lax", secure=AUTH_COOKIE_SECURE, max_age=600)
    return redirect

@app.get("/api/auth/google/callback")
def google_callback(code: str | None = None, state: str | None = None, oauth_state: str | None = Cookie(default=None)):
    from fastapi.responses import RedirectResponse
    if not code or not state or state != _verified_value(oauth_state):
        response = RedirectResponse(_oauth_frontend_redirect("invalid_state"))
        response.delete_cookie("oauth_state", httponly=True, samesite="lax", secure=AUTH_COOKIE_SECURE)
        LOGGER.warning("event=google_oauth_invalid_state")
        return response
    try:
        token_response=httpx.post("https://oauth2.googleapis.com/token",data={"code":code,"client_id":GOOGLE_CLIENT_ID,"client_secret":GOOGLE_CLIENT_SECRET,"redirect_uri":GOOGLE_OAUTH_REDIRECT_URI,"grant_type":"authorization_code"},timeout=10)
        token_response.raise_for_status()
        token_payload=token_response.json()
        access_token=token_payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ValueError("missing access token")
        identity_response=httpx.get("https://openidconnect.googleapis.com/v1/userinfo",headers={"Authorization":f"Bearer {access_token}"},timeout=10)
        identity_response.raise_for_status()
        identity=identity_response.json()
        google_id, email=str(identity.get("sub", "")),str(identity.get("email","")).strip().casefold()
        if not google_id or not email or not identity.get("email_verified"): raise ValueError()
        user=repo().user_by_google_id(google_id) or repo().user_by_email(email)
        if user:
            if not user.get("google_id"):
                repo().link_google(str(user["_id"]), google_id)
        else:
            try:
                user=repo().create_google_user(email,str(identity.get("name","")).strip()[:120] or "Google user",google_id)
            except DuplicateKeyError:
                # A parallel verified callback may have created or linked the account.
                user = repo().user_by_google_id(google_id) or repo().user_by_email(email)
                if not user:
                    raise
                if not user.get("google_id"):
                    repo().link_google(str(user["_id"]), google_id)
        response=RedirectResponse(_oauth_frontend_redirect())
        _session_cookie(response, str(user["_id"]))
        response.delete_cookie("oauth_state", httponly=True, samesite="lax", secure=AUTH_COOKIE_SECURE)
        LOGGER.info("event=google_oauth_success")
        return response
    except httpx.HTTPStatusError as error:
        # The status is sufficient to diagnose redirect/client setup without
        # logging OAuth responses, authorization codes, or provider payloads.
        stage = "token_exchange" if error.request.url.host == "oauth2.googleapis.com" else "identity_fetch"
        LOGGER.warning("event=google_oauth_provider_http_failure stage=%s status=%s", stage, error.response.status_code)
        failure_code = "google_token_exchange_failed" if stage == "token_exchange" else "google_identity_fetch_failed"
    except httpx.RequestError:
        LOGGER.warning("event=google_oauth_provider_network_failure")
        failure_code = "google_provider_network_failed"
    except ValueError:
        LOGGER.warning("event=google_oauth_identity_validation_failed")
        failure_code = "google_identity_validation_failed"
    except DuplicateKeyError:
        LOGGER.warning("event=google_oauth_account_conflict")
        failure_code = "google_account_conflict"
    except Exception:
        LOGGER.warning("event=google_oauth_persistence_failure")
        failure_code = "google_account_setup_failed"
    response = RedirectResponse(_oauth_frontend_redirect(failure_code))
    response.delete_cookie("oauth_state", httponly=True, samesite="lax", secure=AUTH_COOKIE_SECURE)
    return response

@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return {"user":user,"usage":{"analysis_count":0,"limit":None,"authenticated":True}}

@app.get("/api/history")
def history(user=Depends(current_user)): return repo().history(user["id"])

@app.delete("/api/history")
def clear_history(user=Depends(current_user)):
    return repo().clear_history(user["id"])

@app.get("/api/usage")
def usage_status(request: Request, response: Response, user=Depends(optional_user),
                 anonymous_visitor: str | None = Cookie(default=None)):
    """The sole server-authoritative usage view for both analyzer states."""
    if user:
        return {"analysis_count": 0, "limit": None, "authenticated": True}
    visitor, visitor_hash, ip_hash = _anonymous_identity(request, anonymous_visitor)
    _set_anonymous_cookie(response, visitor)
    count = repo().anonymous_usage(visitor_hash, ip_hash)["analysis_count"]
    return {"analysis_count": count, "limit": 2, "authenticated": False}


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(FRONTEND_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Health Check
# ---------------------------------------------------------

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "message": "AI Resume Analyzer API is running",
    }

@app.get("/api/ready")
def readiness_check():
    try:
        repo().client.admin.command("ping")
    except Exception:
        raise HTTPException(status_code=503, detail="Service dependencies are unavailable.")
    return {"status": "ready"}


# ---------------------------------------------------------
# Resume Upload
# ---------------------------------------------------------

@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)):

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file provided.",
        )

    allowed_extensions = {".pdf", ".docx"}

    file_extension = os.path.splitext(
        file.filename
    )[1].lower()

    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are supported.",
        )

    file_content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(file_content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Resume file is too large.")

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=file_extension,
    ) as temp_file:

        temp_file.write(file_content)
        temp_file_path = temp_file.name

    try:

        if file_extension == ".pdf":
            text = extract_text_from_pdf(
                temp_file_path
            )

        else:
            text = extract_text_from_docx(
                temp_file_path
            )

    finally:

        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="Could not extract text from the resume.",
        )

    return {
        "filename": file.filename,
        "file_type": file_extension.replace(".", ""),
        "text": text,
    }


# ---------------------------------------------------------
# Structure Resume
# ---------------------------------------------------------

@app.post("/api/resume/structure")
async def structure_resume(payload: dict):

    resume_text = payload.get("text")

    if not isinstance(resume_text, str) or not resume_text.strip() or len(resume_text) > MAX_RESUME_TEXT_CHARS:
        raise HTTPException(
            status_code=400,
            detail="Resume text is required.",
        )

    try:

        classification = classify_resume_document(resume_text)
        if classification == "not_resume":
            raise HTTPException(status_code=422, detail="This document does not appear to be a resume or CV. Please upload your resume to continue.")
        if classification == "uncertain":
            raise HTTPException(status_code=422, detail="We could not confidently identify this document as a resume or CV. Please upload a clearer resume or CV.")

        result = extract_resume_data(resume_text)

        return {
            "data": result,
        }

    except Exception as error:

        LOGGER.warning("event=resume_structuring_failed")

        raise HTTPException(
            status_code=500,
            detail="Failed to analyze resume with AI.",
        )


# ---------------------------------------------------------
# Analyze Resume
# ---------------------------------------------------------

@app.post("/api/resume/analyze")
async def analyze_resume(response: Response, request: Request, file: UploadFile = File(...), user=Depends(optional_user),
                         anonymous_visitor: str | None = Cookie(default=None)):
    if not user:
        visitor, visitor_hash, ip_hash = _anonymous_identity(request, anonymous_visitor)
        _set_anonymous_cookie(response, visitor)
        if not repo().anonymous_quota_available(visitor_hash, ip_hash):
            raise HTTPException(status_code=403, detail="You've used your 2 free analyses. Create an account or log in to continue.")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    allowed_extensions = {".pdf", ".docx"}
    file_extension = os.path.splitext(file.filename)[1].lower()

    if file_extension not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported.")

    # Read uploaded file
    file_content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(file_content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Resume file is too large.")

    # Create temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
        temp_file.write(file_content)
        temp_file_path = temp_file.name

    try:
        # Extract text
        if file_extension == ".pdf":
            text = extract_text_from_pdf(temp_file_path)
        else:
            text = extract_text_from_docx(temp_file_path)
    finally:
        # Always remove temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

    # Validate extracted text
    if not text.strip() or len(text) > MAX_RESUME_TEXT_CHARS:
        raise HTTPException(status_code=400, detail="Could not extract text from the resume.")

    # Resume classification before quota consumption
    try:
        classification = classify_resume_document(text)
    except ResumeClassificationError:
        LOGGER.warning("event=resume_classification_failed")
        raise HTTPException(status_code=503, detail="We could not validate this document right now. Please try again.")

    if classification == "not_resume":
        LOGGER.info("event=resume_document_rejected classification=not_resume")
        raise HTTPException(status_code=422, detail="This document does not appear to be a resume or CV. Please upload your resume to continue.")
    if classification == "uncertain":
        LOGGER.info("event=resume_document_rejected classification=uncertain")
        raise HTTPException(status_code=422, detail="We could not confidently identify this document as a resume or CV. Please upload a clearer resume or CV.")

    # AI Analysis
    try:
        resume_data = extract_resume_data(text)
    except Exception as error:
        LOGGER.warning("event=resume_extraction_failed")
        raise HTTPException(status_code=500, detail="Failed to analyze resume with AI.")

    # Authenticated uploads are staged server-side. The browser receives only
    # an owner-scoped opaque ID, never raw/base64 resume bytes.
    upload_id = None
    if user:
        try:
            upload_id = repo().stage_original_upload(
                user["id"], file.filename, file_extension.replace(".", ""), file_content
            )
        except Exception:
            LOGGER.warning("event=resume_upload_staging_failed")
            raise HTTPException(status_code=503, detail="We could not securely prepare this resume for analysis. Please try again.")

    # Response
    return {
        "filename": file.filename,
        "file_type": file_extension.replace(".", ""),
        "resume": resume_data,
        "upload_id": upload_id,
    }

@app.post("/api/resume/analyze-score")
async def analyze_resume_score(payload: dict, request: Request, response: Response,
                               user=Depends(optional_user), anonymous_visitor: str | None = Cookie(default=None)):
    resume_data = payload.get("resume")

    if not resume_data:
        raise HTTPException(
            status_code=400,
            detail="Resume data is required."
        )

    try:
        analysis = calculate_resume_score(resume_data)
        analysis_id = None
        try:
            if user:
                original_file_id = (
                    repo().claim_staged_original(user["id"], payload.get("upload_id"))
                    if payload.get("upload_id") else None
                )
                analysis_id = repo().save_analysis_with_quota(
                    user["id"],
                    payload.get("filename", "Resume"),
                    payload.get("file_type", ""),
                    resume_data,
                    analysis,
                    original_file_id
                )
                LOGGER.info(
                    "event=analysis_persisted has_original_file=%s file_type=%s",
                    bool(original_file_id), payload.get("file_type", ""),
                )
                usage = 0
            else:
                visitor, visitor_hash, ip_hash = _anonymous_identity(request, anonymous_visitor)
                usage = repo().consume_anonymous_analysis(visitor_hash, ip_hash)
                _set_anonymous_cookie(response, visitor)
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error))

        LOGGER.info("event=resume_analysis_success authenticated=%s", bool(user))

        return {
            "analysis": analysis,
            "analysis_id": analysis_id,
            "usage": {"analysis_count": usage, "limit": None if user else 2, "authenticated": bool(user)}
        }

    except ResumeClassificationError:
        LOGGER.warning("event=resume_classification_failed")
        raise HTTPException(status_code=503, detail="We could not validate this document right now. Please try again.")
    except HTTPException:
        raise
    except Exception as error:
        if isinstance(error, HTTPException): 
            raise
        LOGGER.warning("event=resume_analysis_failed")
        raise HTTPException(status_code=500, detail="Resume analysis failed. Please try again.")


# ---------------------------------------------------------
# Resume to Job Description Match
# ---------------------------------------------------------

@app.post("/api/resume/match")
async def match_resume(payload: dict, user=Depends(optional_user)):
    resume_data = payload.get("resume")
    job_description = payload.get("job_description")

    if not isinstance(resume_data, dict):
        raise HTTPException(
            status_code=400,
            detail="Resume data must be an object.",
        )

    if not isinstance(job_description, str) or not job_description.strip():
        raise HTTPException(
            status_code=400,
            detail="Job description is required.",
        )

    try:
        result = match_resume_to_job(resume_data, job_description)
        if user:
            repo().save_match(user["id"], resume_data, job_description, result)
        LOGGER.info("event=job_match_success authenticated=%s", bool(user))
        return result
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.post("/api/resume/optimize-document")
async def optimize_resume_document(payload: dict, user=Depends(current_user)):
    resume_data, job_description, job_match = payload.get("resume"), payload.get("job_description"), payload.get("job_match")
    analysis_id = payload.get("analysis_id")
    
    if not isinstance(resume_data, dict) or not isinstance(job_match, dict):
        raise HTTPException(status_code=400, detail="Analyze a resume and job description before optimizing it.")
    if not isinstance(job_description, str) or not job_description.strip():
        raise HTTPException(status_code=400, detail="A job description is required before optimizing a resume.")
    
    try:
        # Generate optimized content
        optimized, improvements, unsupported = optimize_resume_for_job(resume_data, job_description, job_match)
        optimized_match = match_resume_to_job(optimized, job_description)
        
        # Try to retrieve original file for format preservation
        original_file_bytes = None
        file_type = None
        
        if analysis_id:
            try:
                original_file_bytes, file_type, _ = repo().get_original_file_for_optimization(user["id"], analysis_id)
            except Exception:
                LOGGER.warning("event=original_file_lookup_failed")
        
        # DOCX inputs are edited in place. PDF text is never modified: its
        # optimized artifact is a fresh, clearly labelled ATS-friendly DOCX.
        if not original_file_bytes or file_type not in {"docx", "pdf"}:
            raise HTTPException(status_code=422, detail="Original file unavailable — re-analyze this resume and try again.")
        try:
            if file_type == "docx":
                docx_bytes = render_docx_preserving_format(original_file_bytes, optimized, improvements)
            else:
                docx_bytes = render_ats_docx(optimized)
            pdf_bytes = None
            available_formats = ["docx"]
        except DocumentPreservationError as error:
            LOGGER.info("event=format_preservation_rejected file_type=%s", file_type)
            raise HTTPException(status_code=422, detail="We could not apply these wording changes without risking the original document layout. Your original resume was not changed.") from error
        
        optimization_id, expires = repo().save_optimized_resume(
            user["id"],
            analysis_id,
            job_description,
            job_match.get("match_score"),
            optimized_match.get("match_score"),
            pdf_bytes,
            docx_bytes,
            improvements,
            unsupported
        )
        
        return {
            "id": optimization_id,
            "optimized_resume": optimized,
            "improvements": improvements,
            "safe_rewrites_generated": bool(improvements),
            "unsupported_requirements": unsupported,
            "original_match_score": job_match.get("match_score"),
            "optimized_match_score": optimized_match.get("match_score"),
            "expires_at": expires.isoformat(),
            "downloads_remaining": 3,
            "format_preserved": True,
            "available_formats": available_formats,
        }
    except ResumeDocumentOptimizationError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except HTTPException:
        raise
    except Exception:
        LOGGER.warning("event=resume_document_optimization_failed")
        raise HTTPException(status_code=503, detail="We could not generate an optimized resume right now. Please try again.")


@app.get("/api/optimized-resumes/{optimization_id}/{document_format}")
def download_optimized_resume(optimization_id: str, document_format: str, user=Depends(current_user)):
    try:
        content, _ = repo().download_optimized_resume(user["id"], optimization_id, document_format)
    except (ValueError, PermissionError):
        raise HTTPException(status_code=404, detail="This download is unavailable.")
    media_type = "application/pdf" if document_format == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="optimized-resume.{document_format}"', "Cache-Control": "private, no-store"})


# ---------------------------------------------------------
# Universal AI evidence matcher (side-by-side rollout)
# ---------------------------------------------------------

@app.post("/api/resume/match-ai")
async def match_resume_ai(payload: dict, user=Depends(current_user)):
    resume_data = payload.get("resume")
    job_description = payload.get("job_description")
    if not isinstance(resume_data, dict):
        raise HTTPException(status_code=400, detail="Resume data must be an object.")
    if not isinstance(job_description, str) or not job_description.strip():
        raise HTTPException(status_code=400, detail="Job description is required.")
    try:
        return match_resume_to_job_universal(resume_data, job_description)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        LOGGER.warning("event=universal_ai_match_failed")
        raise HTTPException(status_code=502, detail="Universal AI matching is temporarily unavailable.")


# ---------------------------------------------------------
# Resume Optimization Intelligence
# ---------------------------------------------------------

@app.post("/api/resume/optimize", response_model=ResumeOptimizationResponse)
async def optimize_resume(payload: dict, user=Depends(current_user)):
    resume_data = payload.get("resume")
    job_description = payload.get("job_description")
    job_match = payload.get("job_match")

    if not isinstance(resume_data, dict):
        raise HTTPException(
            status_code=400,
            detail="Resume data must be an object.",
        )

    if not isinstance(job_description, str) or not job_description.strip():
        raise HTTPException(
            status_code=400,
            detail="Job description is required.",
        )

    if job_match is not None and not isinstance(job_match, dict):
        raise HTTPException(
            status_code=400,
            detail="Job match result must be an object when provided.",
        )

    try:
        return generate_resume_optimizations(resume_data, job_description, job_match)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


# ---------------------------------------------------------
# AI-assisted single bullet improvement
# ---------------------------------------------------------

@app.post("/api/resume/improve-bullet", response_model=BulletImprovementResponse)
async def improve_bullet(payload: dict):
    resume_data = payload.get("resume")
    job_description = payload.get("job_description")
    bullet = payload.get("bullet")

    if not isinstance(resume_data, dict):
        raise HTTPException(status_code=400, detail="Resume data must be an object.")
    if not isinstance(job_description, str) or not job_description.strip():
        raise HTTPException(status_code=400, detail="Job description is required.")
    if not isinstance(bullet, str) or not bullet.strip():
        raise HTTPException(status_code=400, detail="An existing resume bullet is required.")

    try:
        return improve_resume_bullet(
            resume_data=resume_data,
            job_description=job_description,
            bullet=bullet,
            context=payload.get("context"),
            job_match=payload.get("job_match"),
            optimization_recommendations=payload.get("optimization_recommendations"),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except BulletImprovementGenerationError as error:
        LOGGER.warning("Bullet improvement rejected: %s", error)
        raise HTTPException(status_code=502, detail=str(error))
