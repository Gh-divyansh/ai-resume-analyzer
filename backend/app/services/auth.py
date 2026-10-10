import base64, hashlib, hmac, json, secrets, time
from fastapi import Cookie, HTTPException
from app.core.config import AUTH_SECRET
from app.services.persistence import repo

def hash_password(password):
    salt=secrets.token_bytes(16); digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,310000)
    return base64.b64encode(salt+digest).decode()
def verify_password(password, stored):
    raw=base64.b64decode(stored); return hmac.compare_digest(raw[16:],hashlib.pbkdf2_hmac("sha256",password.encode(),raw[:16],310000))
def token(user_id):
    if not AUTH_SECRET: raise RuntimeError("AUTH_SECRET is required.")
    body=base64.urlsafe_b64encode(json.dumps({"sub":str(user_id),"exp":int(time.time())+604800}).encode()).decode().rstrip("=")
    sig=hmac.new(AUTH_SECRET.encode(),body.encode(),hashlib.sha256).hexdigest(); return f"{body}.{sig}"
def _session_user(session: str | None):
    if not session or not AUTH_SECRET:
        return None
    try:
        body,sig=session.split("."); expected=hmac.new(AUTH_SECRET.encode(),body.encode(),hashlib.sha256).hexdigest()
        payload=json.loads(base64.urlsafe_b64decode(body+"="*(-len(body)%4)))
        if not hmac.compare_digest(sig,expected) or payload["exp"]<time.time(): raise ValueError()
        user=repo().user_by_id(payload["sub"])
        if not user:
            return None
        return {"id":str(user["_id"]),"email":user["email"]}
    except Exception:
        return None

def current_user(session: str|None=Cookie(default=None)):
    user = _session_user(session)
    if not user:
        raise HTTPException(401,"Authentication required.")
    return user

def optional_user(session: str | None = Cookie(default=None)):
    """Return the signed-in user when present, without weakening protected routes."""
    return _session_user(session)
