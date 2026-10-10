"""Offline endpoint coverage for Phase 12 identity, isolation, and quota boundaries."""
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from app.main import app
from app.services.rate_limit import rate_limiter


class FakeRepo:
    def __init__(self):
        self.users, self.usage_counts, self.analyses, self.matches = {}, {}, [], []
        self.anonymous = {}
        self.staged_uploads = {}

    def create_user(self, email, password_hash, name=""):
        if email in self.users:
            raise DuplicateKeyError("duplicate")
        user = {"_id": f"u{len(self.users)+1}", "email": email, "name": name, "password_hash": password_hash}
        self.users[email] = user; self.usage_counts[user["_id"]] = 0
        return user

    def user_by_email(self, email): return self.users.get(email)
    def user_by_google_id(self, google_id): return next((u for u in self.users.values() if u.get("google_id") == google_id), None)
    def link_google(self, identifier, google_id): self.user_by_id(identifier)["google_id"] = google_id
    def create_google_user(self, email, name, google_id):
        user = self.create_user(email, "", name); user["google_id"] = google_id; return user
    def user_by_id(self, identifier): return next((u for u in self.users.values() if u["_id"] == identifier), None)
    def usage(self, identifier): return {"analysis_count": self.usage_counts[identifier]}

    def save_analysis_with_quota(self, identifier, filename, file_type, resume, analysis, original_file_id=None):
        analysis_id = f"analysis-{len(self.analyses)+1}"
        self.analyses.append({"id": analysis_id, "user_id": identifier, "filename": filename,
                              "file_type": file_type, "original_file_id": original_file_id})
        return analysis_id

    def stage_original_upload(self, identifier, filename, file_type, file_bytes):
        upload_id = f"upload-{len(self.staged_uploads)+1}"
        self.staged_uploads[upload_id] = {"user_id": identifier, "filename": filename, "file_type": file_type}
        return upload_id

    def claim_staged_original(self, identifier, upload_id):
        item = self.staged_uploads.get(upload_id)
        if not item or item["user_id"] != identifier:
            raise PermissionError("The uploaded resume is unavailable.")
        return upload_id

    def get_original_file_for_optimization(self, identifier, analysis_id):
        return None, None, None

    def consume_anonymous_analysis(self, visitor_hash, ip_hash):
        key = ip_hash  # mirrors the fallback: resetting the cookie does not reset quota.
        count = self.anonymous.get(key, 0)
        if count >= 2:
            raise PermissionError("You've used your 2 free analyses. Create an account or log in to continue.")
        self.anonymous[key] = count + 1
        return count + 1

    def anonymous_quota_available(self, visitor_hash, ip_hash):
        return self.anonymous.get(ip_hash, 0) < 2

    def anonymous_usage(self, visitor_hash, ip_hash):
        return {"analysis_count": self.anonymous.get(ip_hash, 0)}

    def save_match(self, identifier, resume, job_description, result):
        self.matches.append({"user_id": identifier, "job_description": job_description, "result": result})

    def history(self, identifier):
        return {
            "analyses": [{"id": str(index), "filename": item["filename"], "file_type": "pdf", "created_at": "2026-01-01T00:00:00+00:00"}
                         for index, item in enumerate(self.analyses) if item["user_id"] == identifier],
            "matches": [{"id": str(index), "job_description": item["job_description"], "match_score": item["result"].get("match_score"), "created_at": "2026-01-01T00:00:00+00:00"}
                        for index, item in enumerate(self.matches) if item["user_id"] == identifier],
        }

    def clear_history(self, identifier):
        before_analyses, before_matches = len(self.analyses), len(self.matches)
        self.analyses = [item for item in self.analyses if item["user_id"] != identifier]
        self.matches = [item for item in self.matches if item["user_id"] != identifier]
        return {"analyses_deleted": before_analyses - len(self.analyses), "matches_deleted": before_matches - len(self.matches)}


class AuthPersistenceTests(unittest.TestCase):
    def setUp(self):
        rate_limiter.reset()
        self.store = FakeRepo()
        self.main = patch("app.main.repo", return_value=self.store)
        self.auth = patch("app.services.auth.repo", return_value=self.store)
        self.score = patch("app.main.calculate_resume_score", return_value={"score": 50, "strengths": [], "weaknesses": [], "suggestions": [], "missing_skills": []})
        self.main.start(); self.auth.start(); self.score.start(); self.client = TestClient(app)

    def tearDown(self):
        self.score.stop(); self.auth.stop(); self.main.stop()

    def test_auth_validation_session_and_isolation(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/signup", json={"name":"", "email":"bad", "password":"short"}).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/signup", json={"name":"A", "email":"a@example.com", "password":"password123"}).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/signup", json={"name":"A", "email":"a@example.com", "password":"password123"}).status_code, 409)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json={"email":"a@example.com", "password":"wrong"}).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json={"email":"a@example.com", "password":"password123"}).status_code, 200)
        self.store.save_match("u1", {}, "Role A", {"match_score": 70})
        self.client.post("/api/auth/logout")
        self.client.post("/api/auth/signup", json={"name":"B", "email":"b@example.com", "password":"password123"})
        self.assertEqual(self.client.get("/api/history").json(), {"analyses": [], "matches": []})

    def test_anonymous_two_successes_and_authenticated_quota_are_independent(self):
        payload = {"resume": {"name": "Candidate"}}
        self.assertEqual(self.client.post("/api/resume/analyze-score", json=payload).status_code, 200)
        self.assertEqual(self.client.post("/api/resume/analyze-score", json=payload).status_code, 200)
        self.assertEqual(self.client.post("/api/resume/analyze-score", json=payload).status_code, 403)
        # A new cookie on the same client IP does not reset the server-side fallback quota.
        self.client.cookies.delete("anonymous_visitor")
        self.assertEqual(self.client.post("/api/resume/analyze-score", json=payload).status_code, 403)
        self.assertEqual(self.client.post("/api/auth/signup", json={"name":"A", "email":"a@example.com", "password":"password123"}).status_code, 200)
        self.assertEqual(self.client.post("/api/resume/analyze-score", json=payload).status_code, 200)
        self.assertEqual(self.client.post("/api/resume/analyze-score", json=payload).status_code, 200)
        self.assertEqual(self.client.post("/api/resume/analyze-score", json=payload).status_code, 200)

    def test_invalid_payload_and_scoring_failure_do_not_consume_anonymous_quota(self):
        self.assertEqual(self.client.post("/api/resume/analyze-score", json={}).status_code, 400)
        with patch("app.main.calculate_resume_score", side_effect=RuntimeError("Gemini unavailable")):
            self.assertEqual(self.client.post("/api/resume/analyze-score", json={"resume": {"name":"C"}}).status_code, 500)
        self.assertEqual(self.client.post("/api/resume/analyze-score", json={"resume": {"name":"C"}}).status_code, 200)

    def test_document_validation_rejects_non_resumes_without_consuming_anonymous_quota(self):
        files = {"file": ("invoice.pdf", b"not a resume", "application/pdf")}
        with patch("app.main.extract_text_from_pdf", return_value="Invoice number 42"), patch("app.main.classify_resume_document", return_value="not_resume"):
            response = self.client.post("/api/resume/analyze", files=files)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.store.anonymous, {})

    def test_document_validation_allows_resume_to_continue_without_consuming_quota_yet(self):
        files = {"file": ("candidate.pdf", b"resume", "application/pdf")}
        with patch("app.main.extract_text_from_pdf", return_value="Candidate work history"), patch("app.main.classify_resume_document", return_value="resume"), patch("app.main.extract_resume_data", return_value={"name":"Candidate"}):
            response = self.client.post("/api/resume/analyze", files=files)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.anonymous, {})

    def test_authenticated_upload_is_staged_without_base64_relay(self):
        self.client.post("/api/auth/signup", json={"name":"A", "email":"a@example.com", "password":"password123"})
        files = {"file": ("candidate.pdf", b"resume", "application/pdf")}
        with patch("app.main.extract_text_from_pdf", return_value="Candidate work history"), patch("app.main.classify_resume_document", return_value="resume"), patch("app.main.extract_resume_data", return_value={"name":"Candidate"}):
            response = self.client.post("/api/resume/analyze", files=files)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("upload_id", payload)
        self.assertNotIn("file_bytes_b64", payload)
        self.assertEqual(self.store.staged_uploads[payload["upload_id"]]["user_id"], "u1")

        score = self.client.post("/api/resume/analyze-score", json={
            "resume": payload["resume"], "filename": payload["filename"], "file_type": payload["file_type"],
            "upload_id": payload["upload_id"],
        })
        self.assertEqual(score.status_code, 200)
        stored = self.store.analyses[0]
        self.assertEqual(stored["user_id"], "u1")
        self.assertEqual(stored["filename"], "candidate.pdf")
        self.assertEqual(stored["file_type"], "pdf")
        self.assertEqual(stored["original_file_id"], payload["upload_id"])

    def test_old_analysis_without_original_reference_gets_safe_reanalyze_error(self):
        self.client.post("/api/auth/signup", json={"name":"A", "email":"a@example.com", "password":"password123"})
        with patch("app.main.optimize_resume_for_job", return_value=({"name":"Candidate"}, [], [])), patch("app.main.match_resume_to_job", return_value={"match_score": 50}):
            response = self.client.post("/api/resume/optimize-document", json={
                "resume": {"name": "Candidate"}, "job_description": "Role requirements", "job_match": {"match_score": 50},
                "analysis_id": "legacy-analysis",
            })
        self.assertEqual(response.status_code, 422)
        self.assertIn("Original file unavailable", response.json()["detail"])

    def test_uncertain_or_unavailable_document_classification_does_not_consume_quota(self):
        from app.services.resume_classifier import ResumeClassificationError
        files = {"file": ("document.pdf", b"document", "application/pdf")}
        with patch("app.main.extract_text_from_pdf", return_value="incomplete scan"), patch("app.main.classify_resume_document", return_value="uncertain"):
            self.assertEqual(self.client.post("/api/resume/analyze", files=files).status_code, 422)
        with patch("app.main.extract_text_from_pdf", return_value="candidate profile"), patch("app.main.classify_resume_document", side_effect=ResumeClassificationError("unavailable")):
            self.assertEqual(self.client.post("/api/resume/analyze", files=files).status_code, 503)
        self.assertEqual(self.store.anonymous, {})

    def test_clear_history_is_authenticated_and_user_scoped(self):
        self.assertEqual(self.client.delete("/api/history").status_code, 401)
        self.client.post("/api/auth/signup", json={"name":"A", "email":"a@example.com", "password":"password123"})
        self.store.analyses.append({"user_id":"u1", "filename":"a.pdf"}); self.store.save_match("u1", {}, "Role A", {"match_score":70})
        self.client.post("/api/auth/logout")
        self.client.post("/api/auth/signup", json={"name":"B", "email":"b@example.com", "password":"password123"})
        self.store.analyses.append({"user_id":"u2", "filename":"b.pdf"}); self.store.save_match("u2", {}, "Role B", {"match_score":80})
        self.assertEqual(self.client.delete("/api/history").json(), {"analyses_deleted":1,"matches_deleted":1})
        self.assertEqual(len(self.store.history("u1")["analyses"]), 1)
        self.assertEqual(len(self.store.history("u1")["matches"]), 1)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

    def test_google_oauth_state_failures_and_verified_account_creation(self):
        import app.main as main
        from unittest.mock import Mock
        with patch.object(main, "GOOGLE_CLIENT_ID", "client"), patch.object(main, "GOOGLE_CLIENT_SECRET", "secret"), patch.object(main, "GOOGLE_OAUTH_REDIRECT_URI", "http://test/callback"):
            start = self.client.get("/api/auth/google", follow_redirects=False)
            self.assertEqual(start.status_code, 307)
            self.assertIn("accounts.google.com", start.headers["location"])
            self.assertIn("invalid_state", self.client.get("/api/auth/google/callback?code=x&state=bad", follow_redirects=False).headers["location"])
            # Invalid state consumes the one-time state cookie, so a new flow is required.
            start = self.client.get("/api/auth/google", follow_redirects=False)
            token_response, identity_response = Mock(), Mock(); token_response.json.return_value={"access_token":"access"}; identity_response.json.return_value={"sub":"google-1","email":"g@example.com","email_verified":True,"name":"Google User"}
            with patch("app.main.httpx.post", return_value=token_response), patch("app.main.httpx.get", return_value=identity_response):
                callback=self.client.get("/api/auth/google/callback?code=x&state=" + start.headers["location"].split("state=")[1].split("&")[0], follow_redirects=False)
            self.assertEqual(callback.status_code, 307)
            self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

    def test_google_oauth_provider_identity_linking_and_google_only_password_rules(self):
        import app.main as main
        from unittest.mock import Mock
        with patch.object(main, "GOOGLE_CLIENT_ID", "client"), patch.object(main, "GOOGLE_CLIENT_SECRET", "secret"), patch.object(main, "GOOGLE_OAUTH_REDIRECT_URI", "http://test/callback"):
            # A provider failure is safely redirected and does not create a session.
            start = self.client.get("/api/auth/google", follow_redirects=False)
            state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
            failed = Mock(); failed.raise_for_status.side_effect = RuntimeError("provider error")
            with patch("app.main.httpx.post", return_value=failed):
                response = self.client.get(f"/api/auth/google/callback?code=x&state={state}", follow_redirects=False)
            self.assertIn("google_account_setup_failed", response.headers["location"])
            self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

            # A verified Google identity with an existing password account links it.
            self.client.post("/api/auth/signup", json={"name":"Existing", "email":"existing@example.com", "password":"password123"})
            self.client.post("/api/auth/logout")
            start = self.client.get("/api/auth/google", follow_redirects=False)
            state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
            token_response, identity_response = Mock(), Mock()
            token_response.json.return_value = {"access_token":"access"}
            identity_response.json.return_value = {"sub":"google-existing", "email":"existing@example.com", "email_verified":True}
            with patch("app.main.httpx.post", return_value=token_response), patch("app.main.httpx.get", return_value=identity_response):
                self.client.get(f"/api/auth/google/callback?code=x&state={state}", follow_redirects=False)
            self.assertEqual(self.store.user_by_email("existing@example.com")["google_id"], "google-existing")

            # An existing Google identity signs in without duplicating its account.
            start = self.client.get("/api/auth/google", follow_redirects=False)
            state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
            with patch("app.main.httpx.post", return_value=token_response), patch("app.main.httpx.get", return_value=identity_response):
                self.client.get(f"/api/auth/google/callback?code=x&state={state}", follow_redirects=False)
            self.assertEqual(len(self.store.users), 1)

            # Google-only accounts have no password fallback.
            self.store.create_google_user("google-only@example.com", "Google", "google-only")
            self.client.post("/api/auth/logout")
            self.assertEqual(self.client.post("/api/auth/login", json={"email":"google-only@example.com", "password":"password123"}).status_code, 401)

    def test_google_oauth_requires_verified_email(self):
        import app.main as main
        from unittest.mock import Mock
        with patch.object(main, "GOOGLE_CLIENT_ID", "client"), patch.object(main, "GOOGLE_CLIENT_SECRET", "secret"), patch.object(main, "GOOGLE_OAUTH_REDIRECT_URI", "http://test/callback"):
            start = self.client.get("/api/auth/google", follow_redirects=False)
            state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
            token_response, identity_response = Mock(), Mock()
            token_response.json.return_value = {"access_token":"access"}
            identity_response.json.return_value = {"sub":"google-1", "email":"unverified@example.com", "email_verified":False}
            with patch("app.main.httpx.post", return_value=token_response), patch("app.main.httpx.get", return_value=identity_response):
                response = self.client.get(f"/api/auth/google/callback?code=x&state={state}", follow_redirects=False)
            self.assertIn("google_identity_validation_failed", response.headers["location"])
            self.assertEqual(self.store.users, {})

    def test_security_headers_and_rate_limiter(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertTrue(response.headers["x-request-id"])
        for _ in range(20):
            self.assertNotEqual(self.client.post("/api/auth/login", json={"email":"missing@example.com", "password":"password123"}).status_code, 429)
        self.assertEqual(self.client.post("/api/auth/login", json={"email":"missing@example.com", "password":"password123"}).status_code, 429)

    def test_production_configuration_requires_safe_secrets_and_origins(self):
        import app.core.config as config
        safe = {
            "APP_ENV": "production", "MONGODB_URI": "mongodb://example", "GEMINI_API_KEY": "key",
            "AUTH_SECRET": "x" * 32, "FRONTEND_ORIGINS": ("https://app.example.com",),
            "GOOGLE_CLIENT_ID": None, "GOOGLE_CLIENT_SECRET": None, "GOOGLE_OAUTH_REDIRECT_URI": None,
        }
        with patch.multiple(config, **safe):
            config.validate_production_config()
        with patch.multiple(config, **(safe | {"AUTH_SECRET": "short"})):
            with self.assertRaises(RuntimeError): config.validate_production_config()


if __name__ == "__main__":
    unittest.main()
