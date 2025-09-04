# src/recon/util.py
import os, sys, json, time, math
from typing import Any, Dict, Optional, Tuple
from datetime import datetime

DEFAULT_TIMEOUT = 30
RETRY_STATUS = {429, 500, 502, 503, 504}

def load_env() -> Dict[str, str]:
    # Do NOT silently read .env in prod; expect shell exports or a launcher to load dotenv.
    cfg = {
        "OKTA_BASE_URL": os.getenv("OKTA_BASE_URL", "").rstrip("/"),
        "OKTA_API_TOKEN": os.getenv("OKTA_API_TOKEN", ""),
        "OKTA_SCIM_GROUP_ID": os.getenv("OKTA_SCIM_GROUP_ID", ""),
        "OP_SCIM_BASE_URL": os.getenv("OP_SCIM_BASE_URL", "").rstrip("/"),
        "OP_SCIM_BEARER_TOKEN": os.getenv("OP_SCIM_BEARER_TOKEN", ""),
        "OP_ACCOUNT": os.getenv("OP_ACCOUNT", ""),  # optional
    }
    return cfg

def require(cfg: Dict[str, str], keys: Tuple[str, ...]) -> None:
    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        err = f"Missing required environment: {', '.join(missing)}"
        print(err, file=sys.stderr)
        sys.exit(2)

class JsonLogger:
    def __init__(self, enable: bool = False, file_path: Optional[str] = None, quiet: bool = False):
        self.enable = enable
        self.file_path = file_path
        self.quiet = quiet
        self._fh = None
        if self.enable and self.file_path:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            self._fh = open(self.file_path, "a", encoding="utf-8")

    def _emit(self, rec: Dict[str, Any]) -> None:
        if not self.enable:
            return
        s = json.dumps(rec, ensure_ascii=False)
        if not self.quiet:
            print(s, file=sys.stderr)
        if self._fh:
            self._fh.write(s + "\n")
            self._fh.flush()

    def info(self, msg: str, **kw):  self._emit({"ts": datetime.utcnow().isoformat()+"Z","lvl":"info","msg":msg, **kw})
    def warn(self, msg: str, **kw):  self._emit({"ts": datetime.utcnow().isoformat()+"Z","lvl":"warn","msg":msg, **kw})
    def error(self, msg: str, **kw): self._emit({"ts": datetime.utcnow().isoformat()+"Z","lvl":"error","msg":msg, **kw})

def backoff_sleep(i: int, retry_after: Optional[str]) -> None:
    if retry_after and retry_after.isdigit():
        time.sleep(int(retry_after))
        return
    # capped exponential backoff (0.5,1,2,4,8)
    time.sleep(min(8, 0.5 * (2 ** i)))
