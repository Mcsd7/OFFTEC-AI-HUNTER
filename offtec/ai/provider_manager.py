"""Streaming Gemini, Groq and OpenAI-compatible provider adapters."""
import json, os, socket, time, urllib.error, urllib.parse, urllib.request
from offtec.ai.secrets import SecretStore

PROVIDERS={
    "gemini":{"base":"https://generativelanguage.googleapis.com/v1beta","endpoint":"gemini"},
    "groq":{"base":"https://api.groq.com/openai/v1","endpoint":"openai"},
    "openai":{"base":"https://api.openai.com/v1","endpoint":"openai"},
    "compatible":{"base":"","endpoint":"openai"},
}
LANGUAGE_INSTRUCTIONS={"pt_BR":"Responda sempre em português brasileiro (pt-BR).","en":"Always respond in English.","es":"Responde siempre en español.","ar":"أجب دائمًا باللغة العربية.","hi":"हमेशा हिंदी में उत्तर दें।"}

class ProviderError(RuntimeError): pass

class ProviderManager:
    def __init__(self,repo=None,secrets=None): self.repo=repo; self.secrets=secrets or SecretStore(); self.health={}
    def configure(self,provider_id,kind,name,base_url,model,api_key):
        if kind not in PROVIDERS: raise ValueError("unsupported provider")
        base_url=(base_url or PROVIDERS[kind]["base"]).rstrip("/")
        parsed=urllib.parse.urlparse(base_url)
        if parsed.scheme not in ("https","http") or not parsed.netloc or (parsed.scheme=="http" and parsed.hostname not in ("localhost","127.0.0.1","::1")):
            raise ValueError("provider URL must use HTTPS (HTTP only allowed for localhost)")
        if not model.strip() or not api_key.strip(): raise ValueError("model and API key are required")
        if not self.repo: raise RuntimeError("provider profile persistence unavailable")
        self.repo.save_provider(provider_id,name.strip(),kind,base_url,model.strip(),True)
        self.secrets.set("provider:"+provider_id,api_key.strip())
        self.repo.set_setting("active_provider",provider_id)
        return provider_id
    def configured_profiles(self):
        profiles=[dict(r) for r in self.repo.providers() if r["enabled"]] if self.repo else []
        if os.getenv("OFFTEC_AI_API_KEY") and os.getenv("OFFTEC_AI_MODEL") and os.getenv("OFFTEC_AI_BASE_URL"):
            if not any(p["id"]=="environment" for p in profiles):
                profiles.append({"id":"environment","name":"Environment provider","kind":"compatible","base_url":os.environ["OFFTEC_AI_BASE_URL"],"model":os.environ["OFFTEC_AI_MODEL"],"enabled":1})
        return profiles
    def profile(self,provider_id=None):
        pid=provider_id or (self.repo.get_setting("active_provider","codex") if self.repo else "environment")
        profiles=self.configured_profiles()
        if pid=="environment" and not any(p["id"]==pid for p in profiles):
            if os.getenv("OFFTEC_AI_API_KEY") and os.getenv("OFFTEC_AI_MODEL") and os.getenv("OFFTEC_AI_BASE_URL"):
                return {"id":"environment","name":"Environment provider","kind":"compatible","base_url":os.environ["OFFTEC_AI_BASE_URL"].rstrip("/"),"model":os.environ["OFFTEC_AI_MODEL"]}
        return next((p for p in profiles if p["id"]==pid),None)
    def name(self):
        p=self.profile()
        if not p: return "Codex"
        return p["name"]+" · "+p["model"]
    def display_name(self,tr):
        p=self.profile()
        if not p:return tr.t("status.disconnected")
        if p["id"] in self.health: state=tr.t("status.connected") if self.health[p["id"]] else tr.t("status.disconnected")
        else: state=tr.t("status.untested")
        name=tr.t("provider.environment") if p["id"]=="environment" else p["name"]
        return name+" · "+p["model"]+" ("+state+")"
    def _key(self,p):
        if p["id"]=="environment": return os.getenv("OFFTEC_AI_API_KEY","")
        return self.secrets.get("provider:"+p["id"]) or ""
    def test(self,provider_id=None,timeout=12):
        p=self.profile(provider_id)
        if not p: return {"connected":False,"reason":"provider is not configured"}
        key=self._key(p)
        if not key: return {"connected":False,"reason":"API key is unavailable"}
        if p["kind"]=="gemini":
            url=p["base_url"].rstrip("/")+"/models/"+urllib.parse.quote(p["model"],safe="")
            req=urllib.request.Request(url,headers={"x-goog-api-key":key})
        else:
            req=urllib.request.Request(p["base_url"].rstrip("/")+"/models",headers={"Authorization":"Bearer "+key})
        try:
            with urllib.request.urlopen(req,timeout=timeout) as response: response.read(1024)
            self.health[p["id"]]=True
            return {"connected":True,"provider":p["name"],"model":p["model"]}
        except Exception as exc:
            self.health[p["id"]]=False
            return {"connected":False,"reason":type(exc).__name__+": provider check failed"}
    def stream_chat(self,messages,language,provider_id=None,timeout=90,system_context="",cancel_event=None):
        p=self.profile(provider_id)
        if not p: raise ProviderError("Nenhum provedor configurado. Configure Gemini, Groq ou um endpoint OpenAI-compatible.")
        key=self._key(p)
        if not key: raise ProviderError("Credencial ausente para o provedor selecionado.")
        instruction=LANGUAGE_INSTRUCTIONS.get(language,LANGUAGE_INSTRUCTIONS["pt_BR"])
        if p["kind"]=="gemini":
            url=p["base_url"].rstrip("/")+"/models/"+urllib.parse.quote(p["model"],safe="")+":streamGenerateContent?alt=sse"
            contents=[]
            for m in messages:
                if m["role"] not in ("user","assistant"): continue
                contents.append({"role":"model" if m["role"]=="assistant" else "user","parts":[{"text":m["content"]}]})
            body={"systemInstruction":{"parts":[{"text":instruction+"\n\n"+system_context}]},"contents":contents,"generationConfig":{"maxOutputTokens":4096}}
            headers={"x-goog-api-key":key,"Content-Type":"application/json"}
        else:
            url=p["base_url"].rstrip("/")+"/chat/completions"
            body={"model":p["model"],"stream":True,"messages":[{"role":"system","content":instruction+"\n\n"+system_context},*[m for m in messages if m["role"] in ("user","assistant")]]}
            headers={"Authorization":"Bearer "+key,"Content-Type":"application/json","Accept":"text/event-stream"}
        request=urllib.request.Request(url,data=json.dumps(body,ensure_ascii=False).encode(),headers=headers)
        try:
            deadline=time.monotonic()+timeout
            with urllib.request.urlopen(request,timeout=1) as response:
                self.health[p["id"]]=True
                while time.monotonic()<deadline:
                    if cancel_event and cancel_event.is_set(): return
                    try: raw=response.readline()
                    except (TimeoutError,socket.timeout): continue
                    if not raw: break
                    line=raw.decode("utf-8",errors="replace").strip()
                    if not line.startswith("data:"): continue
                    payload=line[5:].strip()
                    if not payload or payload=="[DONE]": continue
                    try: chunk=json.loads(payload)
                    except json.JSONDecodeError: continue
                    if p["kind"]=="gemini":
                        candidates=chunk.get("candidates",[])
                        delta="".join(part.get("text","") for part in (candidates[0].get("content",{}).get("parts",[]) if candidates else []))
                    else:
                        choices=chunk.get("choices",[]); delta=(choices[0].get("delta",{}).get("content") or "") if choices else ""
                    if delta: yield delta
        except urllib.error.HTTPError as exc:
            self.health[p["id"]]=False
            raise ProviderError(f"Provider HTTP status {exc.code}; credentials and model were not logged.") from None
        except (urllib.error.URLError,TimeoutError,OSError) as exc:
            self.health[p["id"]]=False
            raise ProviderError(f"Provider connection failed: {type(exc).__name__}.") from None
    def chat(self,messages,language,provider_id=None): return "".join(self.stream_chat(messages,language,provider_id))
