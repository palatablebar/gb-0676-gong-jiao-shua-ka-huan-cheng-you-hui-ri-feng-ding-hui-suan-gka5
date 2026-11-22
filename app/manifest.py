import hashlib,json,time
from datetime import datetime,timezone
from app.config import RULE_VERSION
def content(value):
    """Canonical text for evidence, so the same evidence always seeds one batch."""
    if value is None: return ""
    if isinstance(value,bytes): return value.decode("utf-8-sig","replace")
    if isinstance(value,str): return value
    return json.dumps(value,sort_keys=True,ensure_ascii=False,default=str)
def digest(raw,params=None,dispatch=None):
    seed=raw+json.dumps(params or {},sort_keys=True,ensure_ascii=False).encode()+content(dispatch).encode()+RULE_VERSION.encode()
    return hashlib.sha256(seed).hexdigest()
def manifest(raw,params,started,dispatch=None):
    dispatch_text=content(dispatch)
    return {"input_sha256":hashlib.sha256(raw).hexdigest(),"dispatch_sha256":hashlib.sha256(dispatch_text.encode()).hexdigest() if dispatch_text else None,"dispatch_provided":bool(dispatch_text),"rule_version":RULE_VERSION,"parameters":params,"generated_at":datetime.now(timezone.utc).isoformat(),"elapsed_ms":round((time.monotonic()-started)*1000,2)}
