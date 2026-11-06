import re, socket, ssl, time, urllib.error, urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from offtec.modules.web_analysis import analyze as web_analyze
from offtec.modules.tooling import inventory, run_tool
from offtec.core.config import EXPORT_DIR

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None
OPENER=urllib.request.build_opener(NoRedirect)

def recon(target,**_):
    parsed=urlparse(target); host=parsed.hostname
    records=sorted({x[4][0] for x in socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)})
    ptr={}
    for ip in records[:8]:
        try: ptr[ip]=socket.gethostbyaddr(ip)[0]
        except OSError: pass
    return {"target":target,"method":"local DNS resolver lookup","addresses":records,"reverse_dns":ptr,"timestamp":datetime.now(timezone.utc).isoformat()},[]

def web_check(target,cancel=None,progress=None,**_):
    if cancel and cancel.is_set(): raise InterruptedError("cancelled")
    if progress: progress(25,"HTTP/TLS request started")
    evidence,findings=web_analyze(target)
    evidence["tool"]="Python standard library HTTP/TLS"
    if progress: progress(85,"HTTP/TLS evidence collected")
    return evidence,findings

def api_check(target,cancel=None,progress=None,**_):
    candidates=("/.well-known/openapi.json","/openapi.json","/swagger.json")
    found=[]; evidence={"target":target,"method":"bounded unauthenticated HEAD checks","paths":[]}
    for path in candidates:
        if cancel and cancel.is_set(): raise InterruptedError("cancelled")
        url=urljoin(target.rstrip("/")+"/",path.lstrip("/"))
        req=urllib.request.Request(url,method="HEAD",headers={"User-Agent":"OFFTEC-AI-HUNTER/0.1"})
        try:
            with OPENER.open(req,timeout=5) as res:
                row={"path":path,"status":res.status,"content_type":res.headers.get("Content-Type")}; evidence["paths"].append(row)
                if res.status<400: found.append({"severity":"info","title_key":"finding.api_docs","details_key":"finding.api_detail","confidence":0.9,"recommendation_key":"finding.recommendation_headers","evidence":row})
        except urllib.error.HTTPError as exc: evidence["paths"].append({"path":path,"status":exc.code})
        except (OSError,urllib.error.URLError) as exc: evidence["paths"].append({"path":path,"error":type(exc).__name__})
        time.sleep(.25)
        if progress: progress(10+len(evidence["paths"])*25,"API documentation paths checked")
    cors_url=urljoin(target.rstrip("/")+"/","/")
    request=urllib.request.Request(cors_url,method="HEAD",headers={"Origin":"https://offtec.invalid","User-Agent":"OFFTEC-AI-HUNTER/0.1"})
    try:
        with OPENER.open(request,timeout=5) as res:
            origin=res.headers.get("Access-Control-Allow-Origin"); credentials=res.headers.get("Access-Control-Allow-Credentials")
            evidence["cors"]={"allow_origin":origin,"allow_credentials":credentials,"vary":res.headers.get("Vary")}
            if origin=="https://offtec.invalid" and credentials and credentials.lower()=="true":
                found.append({"severity":"medium","title_key":"finding.cors_reflect","details_key":"finding.cors_detail","confidence":.65,"recommendation_key":"finding.cors_recommendation","evidence":evidence["cors"]})
    except (OSError,urllib.error.URLError) as exc: evidence["cors_error"]=type(exc).__name__
    evidence["tool"]="Python standard library HTTP"
    return evidence,found

def asset_discovery(target,cancel=None,progress=None,**_):
    candidates=("/robots.txt","/sitemap.xml","/.well-known/security.txt","/favicon.ico")
    rows=[]; evidence={"target":target,"method":"four fixed low-rate HEAD requests","resources":rows}
    for path in candidates:
        if cancel and cancel.is_set(): raise InterruptedError("cancelled")
        req=urllib.request.Request(urljoin(target.rstrip("/")+"/",path.lstrip("/")),method="HEAD",headers={"User-Agent":"OFFTEC-AI-HUNTER/0.1"})
        try:
            with OPENER.open(req,timeout=5) as response: rows.append({"path":path,"status":response.status,"content_type":response.headers.get("Content-Type")})
        except urllib.error.HTTPError as exc: rows.append({"path":path,"status":exc.code})
        except (OSError,urllib.error.URLError) as exc: rows.append({"path":path,"error":type(exc).__name__})
        time.sleep(.5)
        if progress: progress(10+len(rows)*20,"fixed public resources checked")
    return evidence,[]

def vulnerability(target,cancel=None,progress=None,**kwargs):
    evidence,findings=web_analyze(target)
    evidence["method"]="passive headers/TLS; no CVE claim without confirmed product version"
    tools=inventory(); binary=tools.get("nuclei")
    if binary:
        result=run_tool([binary,"-u",target,"-tags","misconfig","-severity","info,low","-rate-limit","1","-concurrency","1","-bulk-size","1","-timeout","5","-retries","0","-no-interactsh","-disable-redirects","-disable-update-check","-jsonl"],timeout=90,cancel=cancel,progress=progress)
        evidence["nuclei"]={"returncode":result["returncode"],"output":result["output"][:16000]}
        evidence["method"]+="; Nuclei misconfiguration templates (active HTTP checks)"
        for line in result["output"].splitlines():
            try: item=__import__("json").loads(line)
            except ValueError: continue
            info=item.get("info",{}); severity=info.get("severity","info")
            findings.append({"severity":severity if severity in ("info","low") else "info","title":info.get("name",item.get("template-id","Nuclei finding")),"details":info.get("description","Nuclei misconfiguration template matched."),"confidence":.6,"recommendation":info.get("remediation","Review the matched template and verify evidence manually."),"evidence":{"template":item.get("template-id"),"matched_at":item.get("matched-at"),"matcher":item.get("matcher-name")}})
    else: evidence["optional_tool"]="nuclei unavailable; CVE correlation skipped"
    return evidence,findings

def network(target,cancel=None,progress=None,**_):
    from offtec.core.scope_manager import normalize_target
    _,host=normalize_target(target); binary=inventory().get("nmap")
    if not binary:
        ports=(21,22,25,53,80,110,443,3306,8080,8443); open_ports=[]; errors=[]
        for i,port in enumerate(ports):
            if cancel and cancel.is_set(): raise InterruptedError("cancelled")
            try:
                with socket.create_connection((host,port),timeout=.75): open_ports.append({"protocol":"tcp","port":port,"state":"open"})
            except (TimeoutError,ConnectionRefusedError): pass
            except OSError as exc: errors.append(type(exc).__name__)
            time.sleep(.12)
            if progress: progress(10+(i+1)*8,"bounded common TCP ports checked")
        return {"target":host,"method":"native bounded TCP connect checks; top 10 common ports, no Nmap installed","ports":open_ports,"errors":sorted(set(errors))},[]
    result=run_tool([binary,"-n","-Pn","-sT","-T2","--top-ports","20","--max-retries","1","--scan-delay","100ms","--host-timeout","60s","--reason","-oX","-",host],timeout=75,cancel=cancel,max_output=500000,progress=progress)
    ports=re.findall(r'<port protocol="([^"]+)" portid="(\d+)"[\s\S]*?<state state="([^"]+)"',result["output"])
    evidence={"target":host,"tool":"nmap","returncode":result["returncode"],"ports":[{"protocol":p,"port":int(n),"state":s} for p,n,s in ports],"raw_output":result["output"][:20000],"elapsed":result["elapsed"]}
    return evidence,[]

def sqlmap_scan(target,cancel=None,progress=None,**_):
    binary=inventory().get("sqlmap")
    if not binary: raise FileNotFoundError("sqlmap")
    outdir=EXPORT_DIR/"sqlmap"; outdir.mkdir(parents=True,exist_ok=True,mode=0o700)
    result=run_tool([binary,"-u",target,"--batch","--risk=1","--level=1","--technique=BEUSTQ","--threads=1","--timeout=5","--retries=0","--delay=1","--ignore-redirects","--output-dir="+str(outdir)],timeout=180,cancel=cancel,max_output=500000,progress=progress)
    output=result["output"]
    hits=[line.strip() for line in output.splitlines() if "is vulnerable" in line.lower() or "parameter '" in line.lower() and "injectable" in line.lower()]
    findings=[{"severity":"high","title_key":"finding.sqlmap","details_key":"finding.sqlmap_detail","confidence":.55,"recommendation_key":"finding.recommendation_sql","evidence":{"lines":hits[:20]}}] if hits else []
    return {"target":target,"tool":"sqlmap","returncode":result["returncode"],"output":output[:30000],"safe_profile":"risk 1, level 1, one thread, 1-second delay, 5-second request timeout"},findings

def sql_error_review(text,**_):
    patterns={"MySQL":r"you have an error in your sql syntax|mysql_fetch|mysqli?_[a-z]+","PostgreSQL":r"postgresql.*error|pg_query\(","SQLite":r"sqlite.*(error|exception)|near .+ syntax error","Microsoft SQL Server":r"sql server.*error|unclosed quotation mark|odbc sql server","Oracle":r"ora-\d{4,5}|oracle.*error"}
    matches=[name for name,pattern in patterns.items() if re.search(pattern,text,re.I)]
    findings=[{"severity":"medium","title_key":"finding.sql_error","details_key":"finding.sql_detail","confidence":.45,"recommendation_key":"finding.recommendation_sql","evidence":{"families":matches,"sample":text[:500]}}] if matches else []
    return {"method":"offline signature review; no network request or injection payload","database_error_families":matches},findings

def xss_review(reflection,**_):
    findings=[]
    if reflection:
        escaped=bool(re.search(r"&lt;|&#(?:x0*3c|0*60);",reflection,re.I))
        if re.search(r"<script(?:\s|>)|onerror\s*=|onload\s*=|javascript:",reflection,re.I) and not escaped:
            findings.append({"severity":"medium","title_key":"finding.xss","details_key":"finding.xss_detail","confidence":.35,"recommendation_key":"finding.recommendation_xss","evidence":{"sample":reflection[:500]}})
    return {"method":"offline review of user-supplied response fragment","sample_length":len(reflection)},findings

def sql_review(target,**kwargs): return sql_error_review(target,**kwargs)

RUNNERS={"web":web_check,"tls":web_check,"recon":recon,"api":api_check,"assets":asset_discovery,"vulnerability":vulnerability,"network":network,"sqlmap":sqlmap_scan,"sql_review":sql_error_review,"xss_review":xss_review}
