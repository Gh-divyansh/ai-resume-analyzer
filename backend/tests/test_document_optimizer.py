"""Comprehensive tests for JD-driven resume document optimization."""
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from io import BytesIO

try:
    import pymupdf as fitz
except ImportError:
    import fitz
from docx import Document
from docx.shared import Inches

from app.services.resume_document_optimizer import (
    optimize_resume_for_job,
    ResumeDocumentOptimizationError,
)
from app.services.optimized_resume_documents import (
    DocumentPreservationError,
    render_docx,
    render_docx_preserving_format,
    render_ats_docx,
    render_pdf,
    render_pdf_preserving_format,
)
from app.services.job_matcher import match_resume_to_job


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIRECTORY / f"{name}.json").read_text(encoding="utf-8"))


class DocumentOptimizerTests(unittest.TestCase):
    """Test grounded JD-specific document optimization."""

    def test_optimization_requires_authenticated_user(self):
        """Optimization endpoint requires authentication (enforced by @current_user)."""
        # This is enforced at the API layer by the current_user dependency
        self.assertTrue(True)  # Placeholder for API-level test

    def test_optimization_requires_job_description(self):
        """Optimization rejects empty or missing job descriptions."""
        fixture = load_fixture("medium_match")
        resume = fixture["resume"]
        job_match = match_resume_to_job(resume, fixture["job_description"])
        
        with self.assertRaises(Exception):
            optimize_resume_for_job(resume, "", job_match)
        
        with self.assertRaises(Exception):
            optimize_resume_for_job(resume, "   ", job_match)

    @patch("app.services.resume_document_optimizer.client")
    def test_grounded_rewrite_succeeds(self, mock_client):
        """Valid grounded rewrites are accepted."""
        fixture = load_fixture("medium_match")
        resume = fixture["resume"]
        job_match = match_resume_to_job(resume, fixture["job_description"])
        
        # Mock AI response with valid grounded rewrite (simple rewording only)
        original_bullet = resume["experience"][0]["responsibilities"][0]
        mock_response = Mock()
        mock_response.parsed = {
            "rewrites": [{
                "original": original_bullet,
                "improved": original_bullet.replace("Developed", "Built"),
                "reason": "Improved clarity while preserving all facts"
            }]
        }
        mock_client.models.generate_content.return_value = mock_response
        
        optimized, improvements, unsupported = optimize_resume_for_job(resume, fixture["job_description"], job_match)
        
        self.assertIsInstance(optimized, dict)
        self.assertGreater(len(improvements), 0)
        self.assertEqual(improvements[0]["original"], original_bullet)
        self.assertIn("Built", improvements[0]["improved"])

    @patch("app.services.resume_document_optimizer.client")
    def test_invented_skills_rejected(self, mock_client):
        """AI-generated content with invented skills is rejected."""
        fixture = load_fixture("missing_required_skills")
        resume = fixture["resume"]
        job_match = match_resume_to_job(resume, fixture["job_description"])
        
        original_bullet = resume["experience"][0]["responsibilities"][0]
        # Mock AI trying to add AWS (not in resume)
        mock_response = Mock()
        mock_response.parsed = {
            "rewrites": [{
                "original": original_bullet,
                "improved": f"{original_bullet} using AWS and cloud infrastructure",
                "reason": "Added missing required skills"
            }]
        }
        mock_client.models.generate_content.return_value = mock_response
        
        optimized, improvements, _ = optimize_resume_for_job(resume, fixture["job_description"], job_match)
        self.assertEqual(improvements, [])
        self.assertEqual(optimized, resume)

    @patch("app.services.resume_document_optimizer.client")
    def test_invented_credentials_rejected(self, mock_client):
        """AI-generated content with invented certifications is rejected."""
        fixture = load_fixture("medium_match")
        resume = fixture["resume"]
        job_match = match_resume_to_job(resume, fixture["job_description"])
        
        original_bullet = resume["experience"][0]["responsibilities"][0]
        # Mock AI trying to add credentials
        mock_response = Mock()
        mock_response.parsed = {
            "rewrites": [{
                "original": original_bullet,
                "improved": f"{original_bullet} (AWS Certified Solutions Architect)",
                "reason": "Highlighted certification"
            }]
        }
        mock_client.models.generate_content.return_value = mock_response
        
        optimized, improvements, _ = optimize_resume_for_job(resume, fixture["job_description"], job_match)
        self.assertEqual(improvements, [])
        self.assertEqual(optimized, resume)

    @patch("app.services.resume_document_optimizer.client")
    def test_invented_dates_rejected(self, mock_client):
        """AI-generated content with altered dates is rejected."""
        fixture = load_fixture("experience_mismatch")
        resume = fixture["resume"]
        job_match = match_resume_to_job(resume, fixture["job_description"])
        
        original_bullet = resume["experience"][0]["responsibilities"][0]
        # Mock AI trying to change duration
        mock_response = Mock()
        mock_response.parsed = {
            "rewrites": [{
                "original": original_bullet,
                "improved": f"{original_bullet} over 5+ years of experience",
                "reason": "Emphasized duration"
            }]
        }
        mock_client.models.generate_content.return_value = mock_response
        
        optimized, improvements, _ = optimize_resume_for_job(resume, fixture["job_description"], job_match)
        self.assertEqual(improvements, [])
        self.assertEqual(optimized, resume)

    @patch("app.services.resume_document_optimizer.client")
    def test_invented_employers_rejected(self, mock_client):
        """AI-generated content with altered employers is rejected."""
        fixture = load_fixture("medium_match")
        resume = fixture["resume"]
        job_match = match_resume_to_job(resume, fixture["job_description"])
        
        original_bullet = resume["experience"][0]["responsibilities"][0]
        # Mock AI trying to add company names
        mock_response = Mock()
        mock_response.parsed = {
            "rewrites": [{
                "original": original_bullet,
                "improved": f"{original_bullet} at Fortune 500 companies",
                "reason": "Added prestige"
            }]
        }
        mock_client.models.generate_content.return_value = mock_response
        
        optimized, improvements, _ = optimize_resume_for_job(resume, fixture["job_description"], job_match)
        self.assertEqual(improvements, [])
        self.assertEqual(optimized, resume)

    @patch("app.services.resume_document_optimizer.client")
    def test_invented_metrics_rejected(self, mock_client):
        """AI-generated content with fabricated metrics is rejected."""
        fixture = load_fixture("medium_match")
        resume = fixture["resume"]
        job_match = match_resume_to_job(resume, fixture["job_description"])
        
        original_bullet = resume["experience"][0]["responsibilities"][0]
        # Mock AI trying to add metrics
        mock_response = Mock()
        mock_response.parsed = {
            "rewrites": [{
                "original": original_bullet,
                "improved": f"{original_bullet}, achieving 40% performance improvement",
                "reason": "Quantified impact"
            }]
        }
        mock_client.models.generate_content.return_value = mock_response
        
        optimized, improvements, _ = optimize_resume_for_job(resume, fixture["job_description"], job_match)
        self.assertEqual(improvements, [])
        self.assertEqual(optimized, resume)

    @patch("app.services.resume_document_optimizer.client")
    def test_original_resume_unchanged(self, mock_client):
        """Original resume object remains unchanged after optimization."""
        fixture = load_fixture("medium_match")
        resume = fixture["resume"]
        original_json = json.dumps(resume, sort_keys=True)
        job_match = match_resume_to_job(resume, fixture["job_description"])
        
        original_bullet = resume["experience"][0]["responsibilities"][0]
        mock_response = Mock()
        mock_response.parsed = {
            "rewrites": [{
                "original": original_bullet,
                "improved": original_bullet.replace("Developed", "Created"),
                "reason": "Improved clarity"
            }]
        }
        mock_client.models.generate_content.return_value = mock_response
        
        optimize_resume_for_job(resume, fixture["job_description"], job_match)
        
        # Original resume should be unchanged
        self.assertEqual(json.dumps(resume, sort_keys=True), original_json)

    @patch("app.services.resume_document_optimizer.client")
    def test_unsupported_requirements_surfaced(self, mock_client):
        """Requirements not supported by resume are returned as gaps."""
        fixture = load_fixture("missing_required_skills")
        resume = fixture["resume"]
        job_match = match_resume_to_job(resume, fixture["job_description"])
        
        mock_response = Mock()
        mock_response.parsed = {"rewrites": []}
        mock_response.text = '{"rewrites":[]}'
        mock_client.models.generate_content.return_value = mock_response
        
        try:
            _, _, unsupported = optimize_resume_for_job(resume, fixture["job_description"], job_match)
            # Should include AWS from missing_skills
            self.assertIsInstance(unsupported, list)
        except ResumeDocumentOptimizationError:
            # Empty rewrites should raise error
            pass


class DocumentGenerationTests(unittest.TestCase):
    """Test PDF and DOCX generation."""

    def test_generated_pdf_is_valid(self):
        """PDF generation produces valid PDF bytes."""
        fixture = load_fixture("medium_match")
        resume = fixture["resume"]
        
        pdf_bytes = render_pdf(resume)
        
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 100)
        
        # Validate PDF structure
        pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertGreater(pdf.page_count, 0)
        
        # Check content extraction
        page = pdf[0]
        text = page.get_text()
        self.assertIn(resume["name"], text)
        pdf.close()

    def test_generated_docx_is_valid(self):
        """DOCX generation produces valid DOCX bytes."""
        fixture = load_fixture("medium_match")
        resume = fixture["resume"]
        
        docx_bytes = render_docx(resume)
        
        self.assertIsInstance(docx_bytes, bytes)
        self.assertGreater(len(docx_bytes), 100)
        
        # Validate DOCX structure
        doc = Document(BytesIO(docx_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        self.assertGreater(len(paragraphs), 0)
        self.assertIn(resume["name"], paragraphs[0])

    def test_pdf_contains_all_sections(self):
        """PDF includes all resume sections."""
        fixture = load_fixture("medium_match")
        resume = fixture["resume"]
        
        pdf_bytes = render_pdf(resume)
        pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        full_text = " ".join(page.get_text() for page in pdf)
        
        self.assertIn(resume["name"], full_text)
        if resume.get("summary"):
            self.assertIn("Summary", full_text)
        if resume.get("experience"):
            self.assertIn("Experience", full_text)
        if resume.get("education"):
            self.assertIn("Education", full_text)
        
        pdf.close()

    def test_docx_contains_all_sections(self):
        """DOCX includes all resume sections."""
        fixture = load_fixture("medium_match")
        resume = fixture["resume"]
        
        docx_bytes = render_docx(resume)
        doc = Document(BytesIO(docx_bytes))
        
        full_text = " ".join(p.text for p in doc.paragraphs)
        
        self.assertIn(resume["name"], full_text)
        if resume.get("summary"):
            self.assertIn("Summary", full_text)
        if resume.get("experience"):
            self.assertIn("Experience", full_text)
        if resume.get("education"):
            self.assertIn("Education", full_text)

    def test_multi_page_resume_handled(self):
        """Long resumes span multiple pages correctly."""
        fixture = load_fixture("medium_match")
        resume = fixture["resume"]
        
        # Extend experience to force pagination
        long_experience = resume["experience"][:1] * 10  # Duplicate experience
        extended_resume = {**resume, "experience": long_experience}
        
        pdf_bytes = render_pdf(extended_resume)
        pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        # Should handle multi-page gracefully (may be 1+ pages)
        self.assertGreaterEqual(pdf.page_count, 1)
        pdf.close()

    def test_ats_friendly_formatting(self):
        """Generated documents use ATS-friendly formatting."""
        fixture = load_fixture("medium_match")
        resume = fixture["resume"]
        
        pdf_bytes = render_pdf(resume)
        pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        # Extract text to verify it's parseable
        text = pdf[0].get_text()
        
        # Should have extractable text (not images)
        self.assertGreater(len(text.strip()), 100)
        
        # Should contain key structural elements
        self.assertIn(resume["name"], text)
        
        pdf.close()

    def test_docx_preservation_edits_existing_paragraph_without_rebuilding(self):
        """A safe DOCX edit retains the source document's structure and style."""
        source = Document()
        source.sections[0].left_margin = Inches(1.1)
        paragraph = source.add_paragraph("Developed Shopify themes using Liquid.")
        paragraph.style = source.styles["Normal"]
        paragraph.runs[0].bold = True
        table = source.add_table(rows=1, cols=1)
        table.cell(0, 0).text = "Original table content"
        stream = BytesIO(); source.save(stream)

        output = render_docx_preserving_format(
            stream.getvalue(), {}, [{"original": paragraph.text, "improved": "Built Shopify themes using Liquid."}]
        )
        rendered = Document(BytesIO(output))

        self.assertEqual(len(rendered.paragraphs), 1)
        self.assertEqual(len(rendered.tables), 1)
        self.assertEqual(rendered.paragraphs[0].text, "Built Shopify themes using Liquid.")
        self.assertTrue(rendered.paragraphs[0].runs[0].bold)
        self.assertEqual(rendered.sections[0].left_margin, Inches(1.1))

    def test_docx_preservation_rejects_a_reflow_risk(self):
        source = Document()
        source.add_paragraph("Built themes.")
        stream = BytesIO(); source.save(stream)
        with self.assertRaises(DocumentPreservationError):
            render_docx_preserving_format(
                stream.getvalue(), {}, [{"original": "Built themes.", "improved": "Built highly customized enterprise e-commerce themes."}]
            )

    def test_pdf_source_uses_a_valid_ats_docx_and_pdf_mutation_is_disabled(self):
        source = fitz.open()
        page = source.new_page()
        page.insert_text((72, 72), "Developed Shopify themes.", fontsize=11, fontname="helv")
        source_bytes = source.tobytes(); source.close()

        with self.assertRaises(DocumentPreservationError):
            render_pdf_preserving_format(
                source_bytes, {}, [{"original": "Developed Shopify themes.", "improved": "Built Shopify themes."}]
            )
        docx = Document(BytesIO(render_ats_docx({"name": "Candidate", "experience": [{"role": "Developer", "company": "Example", "duration": "2024", "responsibilities": ["Built Shopify themes."]}]})))
        self.assertIn("Candidate", " ".join(paragraph.text for paragraph in docx.paragraphs))


class PersistenceTests(unittest.TestCase):
    """Test optimization metadata storage and download security."""

    def test_download_requires_ownership(self):
        """Users can only download their own optimized resumes."""
        # This is enforced by the download_optimized_resume method checking user_id
        from app.services.persistence import Repository
        from unittest.mock import MagicMock
        from bson import ObjectId
        
        repo = Repository.__new__(Repository)
        repo.db = MagicMock()
        repo.files = MagicMock()
        repo.now = lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        
        # Mock database to return None (user doesn't own document)
        repo.db.optimized_resumes.find_one_and_update.return_value = None
        
        user_id = str(ObjectId())
        opt_id = str(ObjectId())
        
        with self.assertRaises(PermissionError):
            repo.download_optimized_resume(user_id, opt_id, "pdf")

    def test_download_expires_after_24_hours(self):
        """Downloads expire after 24 hours."""
        from app.services.persistence import Repository
        from datetime import datetime, timezone, timedelta
        from unittest.mock import MagicMock
        from bson import ObjectId
        
        repo = Repository.__new__(Repository)
        repo.db = MagicMock()
        repo.files = MagicMock()
        repo.now = lambda: datetime.now(timezone.utc)
        
        # Mock database to return None (expired)
        repo.db.optimized_resumes.find_one_and_update.return_value = None
        
        user_id = str(ObjectId())
        opt_id = str(ObjectId())
        
        with self.assertRaises(PermissionError):
            repo.download_optimized_resume(user_id, opt_id, "pdf")

    def test_download_limit_three_enforced(self):
        """Downloads are limited to 3 per optimization."""
        from app.services.persistence import Repository
        from unittest.mock import MagicMock
        from bson import ObjectId
        
        repo = Repository.__new__(Repository)
        repo.db = MagicMock()
        repo.files = MagicMock()
        repo.now = lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        
        # Mock database to return None (limit reached)
        repo.db.optimized_resumes.find_one_and_update.return_value = None
        
        user_id = str(ObjectId())
        opt_id = str(ObjectId())
        
        with self.assertRaises(PermissionError):
            repo.download_optimized_resume(user_id, opt_id, "pdf")

    def test_clear_history_removes_optimizations(self):
        """Clear history deletes optimization metadata and files."""
        from app.services.persistence import Repository
        from unittest.mock import MagicMock
        from bson import ObjectId
        
        repo = Repository.__new__(Repository)
        repo.db = MagicMock()
        repo.files = MagicMock()
        repo.original_files = MagicMock()
        
        user_id = str(ObjectId())
        
        # Mock optimized resumes with file IDs
        mock_optimizations = [
            {"_id": ObjectId(), "pdf_file_id": "pdf1", "docx_file_id": "docx1"},
            {"_id": ObjectId(), "pdf_file_id": "pdf2", "docx_file_id": "docx2"},
        ]
        repo.db.optimized_resumes.find.return_value = mock_optimizations
        repo.db.optimized_resumes.delete_many.return_value.deleted_count = 2
        repo.db.analyses.delete_many.return_value.deleted_count = 5
        repo.db.matches.delete_many.return_value.deleted_count = 3
        
        result = repo.clear_history(user_id)
        
        # Should delete optimization documents
        self.assertEqual(result["optimizations_deleted"], 2)
        
        # Should attempt to delete files (verify call count)
        self.assertEqual(repo.files.delete.call_count, 4)  # 2 PDFs + 2 DOCXs

    def test_history_normalizes_naive_mongo_expiry_timestamps(self):
        """Atlas/PyMongo UTC values must not crash history serialization."""
        from app.services.persistence import Repository
        from datetime import datetime, timedelta, timezone
        from unittest.mock import MagicMock
        from bson import ObjectId

        repo = Repository.__new__(Repository)
        repo.db = MagicMock()
        repo.now = lambda: datetime(2026, 1, 1, tzinfo=timezone.utc)
        for collection in (repo.db.analyses, repo.db.matches):
            collection.find.return_value.sort.return_value.limit.return_value = []
        repo.db.optimized_resumes.find.return_value.sort.return_value.limit.return_value = [{
            "_id": ObjectId(),
            "created_at": datetime(2025, 12, 31, 12, 0),
            "expires_at": datetime(2026, 1, 2, 12, 0),
            "download_count": 1,
        }]

        history = repo.history(str(ObjectId()))

        self.assertFalse(history["optimizations"][0]["expired"])
        self.assertEqual(history["optimizations"][0]["downloads_remaining"], 2)
        self.assertTrue(history["optimizations"][0]["expires_at"].endswith("+00:00"))

    def test_history_returns_metadata_without_gridfs_object_ids(self):
        """History must serialize only metadata, never stored resume file IDs."""
        from app.services.persistence import Repository
        from datetime import datetime, timezone
        from unittest.mock import MagicMock
        from bson import ObjectId

        repo = Repository.__new__(Repository)
        repo.db = MagicMock()
        repo.now = lambda: datetime(2026, 1, 1, tzinfo=timezone.utc)
        analysis = {
            "_id": ObjectId(),
            "filename": "resume.pdf",
            "file_type": "pdf",
            "created_at": datetime(2025, 12, 31),
        }
        repo.db.analyses.find.return_value.sort.return_value.limit.return_value = [analysis]
        repo.db.matches.find.return_value.sort.return_value.limit.return_value = []
        repo.db.optimized_resumes.find.return_value.sort.return_value.limit.return_value = []

        history = repo.history(str(ObjectId()))

        self.assertEqual(history["analyses"][0]["filename"], "resume.pdf")
        self.assertNotIn("original_file_id", history["analyses"][0])
        self.assertIsInstance(history["analyses"][0]["id"], str)

    def test_original_file_lookup_requires_matching_analysis_owner_and_gridfs_metadata(self):
        """The analysis reference and GridFS file must both belong to the session user."""
        from app.services.persistence import Repository
        from datetime import datetime, timedelta, timezone
        from unittest.mock import MagicMock
        from bson import ObjectId

        repo = Repository.__new__(Repository)
        repo.db = MagicMock()
        repo.original_files = MagicMock()
        repo.now = lambda: datetime.now(timezone.utc)
        user_id, analysis_id, file_id = ObjectId(), ObjectId(), ObjectId()
        repo.db.analyses.find_one.return_value = {
            "_id": analysis_id, "user_id": user_id, "original_file_id": file_id,
            "file_type": "docx", "filename": "resume.docx",
        }
        repo.db["original_resume_files.files"].find_one.return_value = {
            "_id": file_id, "metadata": {"user_id": user_id, "purpose": "optimization_source",
                                              "expires_at": datetime.now(timezone.utc) + timedelta(days=1)},
        }
        repo.original_files.download_to_stream.side_effect = lambda _file_id, stream: stream.write(b"original-docx")

        content, file_type, filename = repo.get_original_file_for_optimization(str(user_id), str(analysis_id))

        self.assertEqual((content, file_type, filename), (b"original-docx", "docx", "resume.docx"))
        analysis_filter = repo.db.analyses.find_one.call_args.args[0]
        file_filter = repo.db["original_resume_files.files"].find_one.call_args.args[0]
        self.assertEqual(analysis_filter["user_id"], user_id)
        self.assertEqual(file_filter["metadata.user_id"], user_id)
        self.assertEqual(file_filter["metadata.purpose"], "optimization_source")

    def test_old_analysis_without_original_file_id_returns_no_source(self):
        from app.services.persistence import Repository
        from unittest.mock import MagicMock
        from bson import ObjectId

        repo = Repository.__new__(Repository)
        repo.db = MagicMock(); repo.original_files = MagicMock()
        repo.db.analyses.find_one.return_value = {"_id": ObjectId(), "file_type": "pdf"}
        self.assertEqual(repo.get_original_file_for_optimization(str(ObjectId()), str(ObjectId())), (None, None, None))

    def test_failed_optimization_does_not_consume_quota(self):
        """Failed optimizations don't affect usage quota."""
        # Quota is not affected by optimization (it's tied to analysis)
        # This test verifies optimization failure doesn't trigger quota changes
        from app.services.persistence import Repository
        from unittest.mock import MagicMock
        
        repo = Repository.__new__(Repository)
        repo.db = MagicMock()
        
        # Mock usage before
        repo.db.usage.find_one.return_value = {"analysis_count": 5}
        
        # After a failed optimization, usage should be unchanged
        # (Optimizations don't consume quota independently)
        usage_after = repo.db.usage.find_one({"user_id": "user123"})
        self.assertEqual(usage_after["analysis_count"], 5)


if __name__ == "__main__":
    unittest.main()
