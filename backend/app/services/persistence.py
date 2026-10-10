"""Small MongoDB repository layer for user-owned SaaS data."""
from datetime import datetime, timezone
from datetime import timedelta
from io import BytesIO
from bson import ObjectId
import certifi
from gridfs import GridFSBucket
from pymongo import MongoClient, ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError
from app.core.config import MONGODB_URI, MONGODB_DATABASE

class Repository:
    def __init__(self):
        if not MONGODB_URI:
            raise RuntimeError("MONGODB_URI is required for persistent APIs.")
        # Atlas requires TLS. Use certifi's maintained CA bundle explicitly so
        # local Python/OpenSSL trust-store differences do not break Atlas handshakes.
        self.client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=8000, tlsCAFile=certifi.where())
        self.db = self.client[MONGODB_DATABASE]
        self.db.users.create_index([("email", ASCENDING)], unique=True)
        self.db.users.create_index([("google_id", ASCENDING)], unique=True, sparse=True)
        self.db.analyses.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.matches.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.usage.create_index([("user_id", ASCENDING)], unique=True)
        self.db.anonymous_usage.create_index([("visitor_id_hash", ASCENDING)], unique=True)
        self.db.anonymous_usage.create_index([("ip_hash", ASCENDING)])
        self.db.optimized_resumes.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.optimized_resumes.create_index([("expires_at", ASCENDING)])
        
        # GridFS buckets for file storage
        self.files = GridFSBucket(self.db, bucket_name="optimized_resume_files")
        self.original_files = GridFSBucket(self.db, bucket_name="original_resume_files")

    @staticmethod
    def now(): return datetime.now(timezone.utc)

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        """Normalize MongoDB's commonly naive UTC values before comparison."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    
    def create_user(self, email, password_hash, name=""):
        user={"email": email, "name": name, "password_hash": password_hash, "created_at": self.now()}
        result=self.db.users.insert_one(user); user["_id"]=result.inserted_id
        self.db.usage.insert_one({"user_id": result.inserted_id, "analysis_count": 0, "updated_at": self.now()})
        return user
    
    def user_by_email(self,email): return self.db.users.find_one({"email":email})
    def user_by_google_id(self, google_id): return self.db.users.find_one({"google_id": google_id})
    def link_google(self, user_id, google_id): self.db.users.update_one({"_id":ObjectId(user_id)}, {"$set":{"google_id":google_id}})
    
    def create_google_user(self, email, name, google_id):
        user={"email":email,"name":name,"google_id":google_id,"created_at":self.now()}
        result=self.db.users.insert_one(user); user["_id"]=result.inserted_id
        self.db.usage.insert_one({"user_id":result.inserted_id,"analysis_count":0,"updated_at":self.now()})
        return user
    
    def user_by_id(self,user_id): return self.db.users.find_one({"_id":ObjectId(user_id)})
    def usage(self,user_id): return self.db.usage.find_one({"user_id":ObjectId(user_id)}) or {"analysis_count":0}
    
    def consume_analysis(self,user_id):
        return self.db.usage.find_one_and_update({"user_id":ObjectId(user_id),"analysis_count":{"$lt":2}}, {"$inc":{"analysis_count":1},"$set":{"updated_at":self.now()}}, return_document=ReturnDocument.AFTER)
    
    def save_analysis(self,user_id,filename,file_type,resume,analysis):
        doc={"user_id":ObjectId(user_id),"filename":filename,"file_type":file_type,"resume":resume,"analysis":analysis,"created_at":self.now()}
        self.db.analyses.insert_one(doc)
    
    def stage_original_upload(self, user_id, filename, file_type, file_bytes: bytes) -> str:
        """Keep an authenticated upload server-side between analysis steps.

        The staging record is owner-scoped and short-lived. It avoids sending
        resume bytes back through JSON while preserving the existing two-step
        analysis API flow.
        """
        uid = ObjectId(user_id)
        file_id = self.original_files.upload_from_stream(
            filename,
            BytesIO(file_bytes),
            metadata={"user_id": uid, "purpose": "analysis_staging", "file_type": file_type,
                      "created_at": self.now(), "expires_at": self.now() + timedelta(hours=1)},
        )
        return str(file_id)

    def claim_staged_original(self, user_id, upload_id: str | None):
        """Promote a caller-owned staged file only after successful analysis."""
        if not upload_id:
            return None
        try:
            file_id = ObjectId(upload_id)
        except Exception as error:
            raise PermissionError("The uploaded resume reference is invalid.") from error
        uid = ObjectId(user_id)
        file_doc = self.db["original_resume_files.files"].find_one(
            {"_id": file_id, "metadata.user_id": uid, "metadata.purpose": "analysis_staging"}
        )
        if not file_doc:
            raise PermissionError("The uploaded resume is unavailable.")
        self.db["original_resume_files.files"].update_one(
            {"_id": file_id, "metadata.user_id": uid, "metadata.purpose": "analysis_staging"},
            {"$set": {"metadata.purpose": "optimization_source", "metadata.expires_at": self.now() + timedelta(days=3)}},
        )
        return file_id

    def save_analysis_with_quota(self, user_id, filename, file_type, resume, analysis, original_file_id=None):
        """Persist a successful authenticated analysis.

        Accounts are unlimited during the pre-payment phase. The legacy method
        name is retained so callers and API contracts do not need to change.
        
        The optional original file is a previously owner-validated GridFS ID.
        """
        uid = ObjectId(user_id)
        
        document = {
            "user_id": uid,
            "filename": filename,
            "file_type": file_type,
            "resume": resume,
            "analysis": analysis,
            "created_at": self.now(),
            "original_file_id": original_file_id
        }
        
        with self.client.start_session() as session:
            def operation(active_session):
                result = self.db.analyses.insert_one(document, session=active_session)
                return result.inserted_id
            analysis_id = session.with_transaction(operation)
        
        return str(analysis_id)

    def anonymous_usage(self, visitor_id_hash, ip_hash):
        """Find a visitor record by the signed-cookie identity or the hashed-IP fallback."""
        return self.db.anonymous_usage.find_one(
            {"$or": [{"visitor_id_hash": visitor_id_hash}, {"ip_hash": ip_hash}]}
        ) or {"analysis_count": 0}

    def anonymous_quota_available(self, visitor_id_hash, ip_hash):
        return self.anonymous_usage(visitor_id_hash, ip_hash).get("analysis_count", 0) < 2

    def consume_anonymous_analysis(self, visitor_id_hash, ip_hash):
        """Atomically consume an anonymous slot after analysis generation has succeeded.

        No raw IP or cookie value is retained. The HMAC values are only quota keys.
        """
        with self.client.start_session() as session:
            def operation(active_session):
                existing = self.db.anonymous_usage.find_one(
                    {"$or": [{"visitor_id_hash": visitor_id_hash}, {"ip_hash": ip_hash}]},
                    session=active_session,
                )
                if not existing:
                    try:
                        self.db.anonymous_usage.insert_one(
                            {"visitor_id_hash": visitor_id_hash, "ip_hash": ip_hash,
                             "analysis_count": 1, "updated_at": self.now()},
                            session=active_session,
                        )
                        return 1
                    except DuplicateKeyError:
                        existing = self.db.anonymous_usage.find_one(
                            {"$or": [{"visitor_id_hash": visitor_id_hash}, {"ip_hash": ip_hash}]},
                            session=active_session,
                        )
                updated = self.db.anonymous_usage.find_one_and_update(
                    {"_id": existing["_id"], "analysis_count": {"$lt": 2}},
                    {"$inc": {"analysis_count": 1}, "$set": {"updated_at": self.now()}},
                    return_document=ReturnDocument.AFTER, session=active_session,
                )
                if not updated:
                    raise PermissionError("You've used your 2 free analyses. Create an account or log in to continue.")
                return updated["analysis_count"]
            return session.with_transaction(operation)
    
    def save_match(self,user_id,resume,job_description,result):
        self.db.matches.insert_one({"user_id":ObjectId(user_id),"resume":resume,"job_description":job_description,"result":result,"created_at":self.now()})
    
    def history(self,user_id):
        uid=ObjectId(user_id)
        # Use an allow-list projection.  An exclusion projection can leak new
        # internal fields such as GridFS ObjectIds, which FastAPI cannot
        # serialize and which history should never expose in any case.
        analyses=list(self.db.analyses.find(
            {"user_id":uid},
            {"_id":1,"filename":1,"file_type":1,"created_at":1},
        ).sort("created_at",DESCENDING).limit(50))
        matches=list(self.db.matches.find(
            {"user_id":uid},
            {"_id":1,"job_description":1,"result.match_score":1,"created_at":1},
        ).sort("created_at",DESCENDING).limit(50))
        
        # Include optimized resumes in history
        optimizations=list(self.db.optimized_resumes.find(
            {"user_id":uid},
            {"_id":1,"job_description_snippet":1,"original_match_score":1,"optimized_match_score":1,"created_at":1,"expires_at":1,"download_count":1}
        ).sort("created_at",DESCENDING).limit(50))
        
        def out(x):
            x["id"] = str(x.pop("_id"))
            created_at = self._as_utc(x.get("created_at"))
            x["created_at"] = created_at.isoformat() if created_at else None
            return x
        def out_opt(x):
            x["id"] = str(x.pop("_id"))
            created_at = self._as_utc(x.get("created_at"))
            expires_at = self._as_utc(x.get("expires_at"))
            x["created_at"] = created_at.isoformat() if created_at else None
            x["expires_at"] = expires_at.isoformat() if expires_at else None
            x["expired"] = bool(expires_at and expires_at < self.now())
            x["downloads_remaining"] = max(0, 3 - x.get("download_count", 0))
            return x
        
        for match in matches:
            match["match_score"] = (match.pop("result", {}) or {}).get("match_score")
        
        return {
            "analyses":[out(x) for x in analyses],
            "matches":[out(x) for x in matches],
            "optimizations":[out_opt(x) for x in optimizations]
        }

    def clear_history(self, user_id):
        """Delete only persisted activity owned by the authenticated user."""
        uid = ObjectId(user_id)
        
        # Delete original files from analyses
        analyses_with_files = list(self.db.analyses.find({"user_id": uid}, {"original_file_id": 1}))
        for analysis in analyses_with_files:
            if analysis.get("original_file_id"):
                try:
                    self.original_files.delete(analysis["original_file_id"])
                except Exception:
                    pass
        
        analyses = self.db.analyses.delete_many({"user_id": uid}).deleted_count
        matches = self.db.matches.delete_many({"user_id": uid}).deleted_count
        
        optimized = list(self.db.optimized_resumes.find({"user_id": uid}, {"pdf_file_id": 1, "docx_file_id": 1}))
        for item in optimized:
            for file_id in (item.get("pdf_file_id"), item.get("docx_file_id")):
                if file_id:
                    try: self.files.delete(file_id)
                    except Exception: pass
        optimization_count = self.db.optimized_resumes.delete_many({"user_id": uid}).deleted_count
        return {"analyses_deleted": analyses, "matches_deleted": matches, "optimizations_deleted": optimization_count}

    def save_optimized_resume(self, user_id, analysis_id, jd, original_score, optimized_score, pdf_bytes, docx_bytes, improvements, unsupported):
        """Store only formats produced by a validated preservation path."""
        if not pdf_bytes and not docx_bytes:
            raise ValueError("At least one validated optimized document is required.")
        uid = ObjectId(user_id); now = self.now(); expires = now + timedelta(days=3)
        file_ids = {}
        if pdf_bytes:
            file_ids["pdf_file_id"] = self.files.upload_from_stream("optimized-resume.pdf", BytesIO(pdf_bytes), metadata={"user_id": uid, "format": "pdf"})
        if docx_bytes:
            file_ids["docx_file_id"] = self.files.upload_from_stream("optimized-resume.docx", BytesIO(docx_bytes), metadata={"user_id": uid, "format": "docx"})
        doc = {"user_id": uid, "analysis_id": analysis_id, "job_description_snippet": jd[:300], "original_match_score": original_score, "optimized_match_score": optimized_score, **file_ids, "improvements": improvements, "unsupported_requirements": unsupported, "download_count": 0, "created_at": now, "expires_at": expires}
        try:
            result = self.db.optimized_resumes.insert_one(doc); return str(result.inserted_id), expires
        except Exception:
            for file_id in file_ids.values():
                self.files.delete(file_id)
            raise

    def download_optimized_resume(self, user_id, optimization_id, document_format):
        if document_format not in {"pdf", "docx"}: raise ValueError("Unsupported document format.")
        doc = self.db.optimized_resumes.find_one_and_update(
            {"_id": ObjectId(optimization_id), "user_id": ObjectId(user_id), "expires_at": {"$gt": self.now()},
             "download_count": {"$lt": 3}, f"{document_format}_file_id": {"$exists": True}},
            {"$inc": {"download_count": 1}}, return_document=ReturnDocument.AFTER,
        )
        if not doc: raise PermissionError("This download is unavailable, expired, or has reached its download limit.")
        if not doc.get(f"{document_format}_file_id"):
            raise ValueError("This document format is unavailable for the preserved source file.")
        stream = BytesIO(); self.files.download_to_stream(doc[f"{document_format}_file_id"], stream)
        return stream.getvalue(), doc["download_count"]
    
    def get_original_file_for_optimization(self, user_id, analysis_id):
        """Retrieve original file bytes for format-preserving optimization."""
        uid = ObjectId(user_id)
        doc = self.db.analyses.find_one({"_id": ObjectId(analysis_id), "user_id": uid}, {"original_file_id": 1, "file_type": 1, "filename": 1})
        if not doc or not doc.get("original_file_id"):
            return None, None, None

        # GridFSBucket.find() returns GridOut, not a dictionary. Query the
        # files collection for metadata so expiry and ownership are checked
        # without causing an AttributeError that masquerades as a lost file.
        file_info = self.db["original_resume_files.files"].find_one(
            {"_id": doc["original_file_id"], "metadata.user_id": uid,
             "metadata.purpose": "optimization_source"}
        )
        if not file_info:
            return None, None, None
        expires_at = (file_info.get("metadata") or {}).get("expires_at")
        if self._as_utc(expires_at) and self._as_utc(expires_at) < self.now():
            return None, None, None
        stream = BytesIO()
        self.original_files.download_to_stream(doc["original_file_id"], stream)
        return stream.getvalue(), doc.get("file_type"), doc.get("filename")

_repo=None
def repo():
    global _repo
    if _repo is None: _repo=Repository()
    return _repo
