from urllib.parse import urlparse
import ipaddress, re

def normalize_target(target):
    value=target.strip()
    if not value: raise ValueError("empty target")
    if ":" in value and "://" not in value: raise ValueError("invalid scheme")
    parsed=urlparse(value if "://" in value else "https://"+value)
    if parsed.scheme not in ("http","https") or not parsed.hostname: raise ValueError("invalid target")
    host=parsed.hostname.lower().rstrip(".")
    if not re.fullmatch(r"[a-z0-9.-]+",host): raise ValueError("invalid host")
    try: ipaddress.ip_address(host)
    except ValueError:
        if len(host)>253 or any(not p or len(p)>63 or p.startswith("-") or p.endswith("-") for p in host.split(".")): raise ValueError("invalid host")
    return parsed,host

class ScopeManager:
    """Exact host authorization: no wildcard expansion or AI scope growth."""
    def validate(self,target,authorized_hosts):
        parsed,host=normalize_target(target)
        allowed={x.strip().lower().rstrip(".") for x in authorized_hosts if x.strip()}
        if host not in allowed: raise PermissionError("outside authorized scope")
        return parsed,host
