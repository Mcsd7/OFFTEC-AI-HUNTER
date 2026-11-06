"""Private file storage for provider secrets (never SQLite or logs)."""
import json, os, tempfile
from pathlib import Path
from offtec.core.config import APP_DIR, SECRETS_PATH

class SecretStore:
    def __init__(self,path=SECRETS_PATH): self.path=Path(path)
    def _read(self):
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError: return {}
    def get(self,key): return self._read().get(key)
    def set(self,key,value):
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        data=self._read(); data[key]=value
        fd,tmp=tempfile.mkstemp(prefix=".secrets-",dir=self.path.parent)
        try:
            os.fchmod(fd,0o600)
            with os.fdopen(fd,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,self.path); os.chmod(self.path,0o600)
        finally:
            try: os.unlink(tmp)
            except FileNotFoundError: pass
    def delete(self,key):
        data=self._read(); data.pop(key,None)
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.path.open("w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False)
        os.chmod(self.path,0o600)
