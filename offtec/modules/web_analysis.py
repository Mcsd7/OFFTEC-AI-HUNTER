import socket, ssl, time, urllib.request, urllib.error
from datetime import datetime, timezone

def analyze(target, timeout=8):
    """A single bounded HEAD request and certificate read; no crawling or probing."""
    findings=[]; evidence={"target":target,"checked_at":datetime.now(timezone.utc).isoformat(),"method":"passive HTTP HEAD + TLS certificate inspection"}
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs): return None
    opener=urllib.request.build_opener(NoRedirect)
    req=urllib.request.Request(target,method="HEAD",headers={"User-Agent":"OFFTEC-AI-HUNTER/0.1 (authorized passive assessment)"})
    try:
        with opener.open(req,timeout=timeout) as response:
            headers={k.lower():v for k,v in response.headers.items()}
            evidence["http_status"]=response.status
            evidence["headers"]={k:headers[k] for k in sorted(headers) if k in {"server","content-type","strict-transport-security","content-security-policy","x-frame-options","x-content-type-options","referrer-policy","permissions-policy","x-powered-by","x-generator"}}
            evidence["technology_fingerprint"]={k:headers[k] for k in ("server","x-powered-by","x-generator") if headers.get(k)}
            for header,title in (("content-security-policy","finding.csp"),("x-content-type-options","finding.xcto"),("x-frame-options","finding.frame")):
                if header not in headers:
                    findings.append({"severity":"low","title_key":title,"details_key":"finding.header_detail","confidence":0.7,"recommendation_key":"finding.recommendation_headers","evidence":{"header":header,"status":response.status}})
            evidence["server_header"]=headers.get("server")
    except (urllib.error.URLError,TimeoutError,OSError) as exc:
        evidence["http_error"]=type(exc).__name__
        evidence["http_error_detail"]=str(exc)[:240]
    from urllib.parse import urlparse
    p=urlparse(target)
    if p.scheme=="https":
        try:
            context=ssl.create_default_context()
            with socket.create_connection((p.hostname,p.port or 443),timeout=timeout) as sock:
                with context.wrap_socket(sock,server_hostname=p.hostname) as tls:
                    cert=tls.getpeercert(); expires=cert.get("notAfter"); seconds=ssl.cert_time_to_seconds(expires) if expires else None; days=int((seconds-time.time())/86400) if seconds else None
                    evidence["tls"]={"version":tls.version(),"cipher":tls.cipher()[0] if tls.cipher() else None,"not_after":expires,"subject":str(cert.get("subject",""))[:240],"verified":True,"days_to_expiry":days}
                    if days is not None and days<0: findings.append({"severity":"high","title_key":"finding.cert_expired","details_key":"finding.cert_expired_detail","confidence":.95,"recommendation_key":"finding.cert_recommendation","evidence":{"not_after":expires,"days_to_expiry":days}})
                    elif days is not None and days<=30: findings.append({"severity":"medium","title_key":"finding.cert_expiring","details_key":"finding.cert_expiring_detail","confidence":.95,"recommendation_key":"finding.cert_recommendation","evidence":{"not_after":expires,"days_to_expiry":days}})
        except (OSError,ssl.SSLError,ValueError) as exc:
            evidence["tls_error"]=type(exc).__name__
            try:
                with socket.create_connection((p.hostname,p.port or 443),timeout=timeout) as sock:
                    with ssl._create_unverified_context().wrap_socket(sock,server_hostname=p.hostname) as tls:
                        cert=tls.getpeercert(); expires=cert.get("notAfter"); seconds=ssl.cert_time_to_seconds(expires) if expires else None
                        days=int((seconds-time.time())/86400) if seconds else None
                        evidence["tls"]={"version":tls.version(),"cipher":tls.cipher()[0] if tls.cipher() else None,"not_after":expires,"subject":str(cert.get("subject",""))[:240],"verified":False,"verification_error":type(exc).__name__,"days_to_expiry":days}
                        if days is not None and days<0: findings.append({"severity":"high","title_key":"finding.cert_expired","details_key":"finding.cert_expired_detail","confidence":.95,"recommendation_key":"finding.cert_recommendation","evidence":{"not_after":expires,"days_to_expiry":days}})
                        elif days is not None and days<=30: findings.append({"severity":"medium","title_key":"finding.cert_expiring","details_key":"finding.cert_expiring_detail","confidence":.95,"recommendation_key":"finding.cert_recommendation","evidence":{"not_after":expires,"days_to_expiry":days}})
            except (OSError,ssl.SSLError,ValueError) as second: evidence["tls_certificate_unavailable"]=type(second).__name__
    else: evidence["tls"]="not_applicable_http"
    return evidence,findings
