"""Codex app-server JSON-RPC stdio client (newline-delimited JSON)."""
import itertools, json, os, queue, shutil, subprocess, sys, threading, time
from pathlib import Path

class CodexError(RuntimeError): pass

class CodexAdapter:
    def __init__(self,executable=None,process_factory=subprocess.Popen):
        self.executable=executable or shutil.which("codex"); self.process_factory=process_factory
        self.proc=None; self.version=None; self.reason="Codex desconectado"; self._id=itertools.count(1); self._pending={}; self._lock=threading.RLock(); self._events=queue.Queue(); self._reader=None; self.thread_id=None; self.turn_id=None; self.connected=False
        self.runtime_env=os.environ.copy(); self.runtime_note=""
        self.authenticated=None
    def _preload_candidates(self):
        prefix=os.environ.get("PREFIX") or str(Path(sys.executable).resolve().parent.parent)
        for path in (Path(prefix)/"lib/libc++_shared.so",Path(prefix)/"lib/libc++_shared.so.30"):
            if path.is_file(): yield str(path)
    def status(self):
        if self.connected and self.proc and self.proc.poll() is None: return {"connected":True,"authenticated":self.authenticated,"reason":"app-server conectado"+self.runtime_note,"version":self.version}
        if not self.executable: return {"connected":False,"reason":"CLI do Codex não encontrado no PATH.","version":None}
        if self.proc and self.proc.poll() is not None: self.connected=False
        if not self.version:
            try:
                result=subprocess.run([self.executable,"--version"],capture_output=True,text=True,timeout=5)
                if result.returncode and "__hash_memory" in (result.stderr+result.stdout):
                    for library in self._preload_candidates():
                        candidate_env=self.runtime_env.copy(); existing=candidate_env.get("LD_PRELOAD","")
                        candidate_env["LD_PRELOAD"]=(existing+":" if existing else "")+library
                        retry=subprocess.run([self.executable,"--version"],capture_output=True,text=True,timeout=5,env=candidate_env)
                        if retry.returncode==0:
                            self.runtime_env=candidate_env; result=retry; self.runtime_note="; Termux libc++ preload ativo para compatibilidade ABI"
                            break
                if result.returncode: self.reason=(result.stderr or result.stdout or "codex --version falhou")[:400]
                else:
                    self.version=result.stdout.strip()[:160]
                    auth=subprocess.run([self.executable,"login","status"],capture_output=True,text=True,timeout=5,env=self.runtime_env)
                    self.authenticated=auth.returncode==0
                    self.reason="Codex CLI pronto"+self.runtime_note+"; "+("usuário autenticado" if self.authenticated else "usuário não autenticado")+"; app-server ainda não conectado."
            except (OSError,subprocess.TimeoutExpired) as exc: self.reason=str(exc)[:400]
        return {"connected":False,"authenticated":self.authenticated,"reason":self.reason,"version":self.version}
    def _send(self,obj):
        if not self.proc or self.proc.poll() is not None: raise CodexError("app-server não está em execução")
        self.proc.stdin.write(json.dumps(obj,separators=(",",":"),ensure_ascii=False)+"\n"); self.proc.stdin.flush()
    def _read_loop(self):
        try:
            for line in self.proc.stdout:
                try: obj=json.loads(line)
                except (json.JSONDecodeError,TypeError): continue
                if "method" in obj and "id" in obj:
                    # Decline all local command approvals: this app never grants Codex shell execution.
                    if obj["method"] in ("item/commandExecution/requestApproval","item/fileChange/requestApproval"):
                        self._send({"jsonrpc":"2.0","id":obj["id"],"result":{"decision":"decline"}})
                    else: self._send({"jsonrpc":"2.0","id":obj["id"],"error":{"code":-32601,"message":"Request method is not approved by OFFTEC AI HUNTER"}})
                    continue
                if "id" in obj:
                    with self._lock: waiter=self._pending.get(str(obj["id"]))
                    if waiter:
                        waiter["response"]=obj; waiter["event"].set()
                    continue
                if "method" in obj: self._events.put(obj)
        except (OSError,ValueError): pass
        finally: self._events.put({"method":"offtec/processExited"}); self.connected=False
    def connect(self,timeout=10):
        if self.connected and self.proc and self.proc.poll() is None: return True
        if not self.executable: self.reason="CLI do Codex não encontrado no PATH."; return False
        status=self.status()
        if not status["version"]: return False
        try:
            # `--listen stdio://` is the documented app-server transport.
            self.proc=self.process_factory([self.executable,"app-server","--listen","stdio://","-c","sandbox_mode=\"read-only\""],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1,env=self.runtime_env.copy())
            self._reader=threading.Thread(target=self._read_loop,name="codex-app-server-reader",daemon=True); self._reader.start()
            self.request("initialize",{"clientInfo":{"name":"offtec_ai_hunter","title":"OFFTEC AI HUNTER","version":"0.2.0"},"capabilities":{"experimentalApi":False}},timeout)
            self._send({"jsonrpc":"2.0","method":"initialized","params":{}})
            self.connected=True; self.reason="app-server conectado"; return True
        except Exception as exc:
            self.reason=f"Falha no handshake app-server: {type(exc).__name__}: {str(exc)[:240]}"; self.close(); return False
    def request(self,method,params,timeout=15):
        reqid=next(self._id); holder={"event":threading.Event()}
        with self._lock: self._pending[str(reqid)]=holder
        try:
            self._send({"jsonrpc":"2.0","id":reqid,"method":method,"params":params})
            if not holder["event"].wait(timeout): raise TimeoutError(f"app-server timeout: {method}")
            response=holder["response"]
            if "error" in response: raise CodexError(response["error"].get("message",method+" failed"))
            return response.get("result",{})
        finally:
            with self._lock: self._pending.pop(str(reqid),None)
    def start_thread(self,cwd,language,context="",resume_id=None):
        language_prompt={"pt_BR":"Responda sempre em português brasileiro.","en":"Always reply in English.","es":"Responde siempre en español.","ar":"أجب دائمًا باللغة العربية.","hi":"हमेशा हिंदी में उत्तर दें।"}.get(language,"Responda sempre em português brasileiro.")
        instructions=language_prompt+" Você é assistente de análise defensiva. Não amplie o escopo; não execute nem sugira ações fora da autorização explícita. O host aplica verificações e operações aprovadas separadamente. Contexto do projeto: "+context[:10000]
        if resume_id:
            result=self.request("thread/resume",{"threadId":resume_id,"cwd":cwd,"sandbox":"read-only","approvalPolicy":"on-request"})
        else:
            result=self.request("thread/start",{"cwd":cwd,"sandbox":"read-only","approvalPolicy":"on-request","baseInstructions":instructions})
        self.thread_id=(result.get("thread") or {}).get("id")
        if not self.thread_id: raise CodexError("app-server não retornou thread id")
        return self.thread_id
    def stream_turn(self,message,timeout=300,cancel=None):
        if not self.thread_id: raise CodexError("Nenhuma thread Codex ativa")
        self.request("turn/start",{"threadId":self.thread_id,"input":[{"type":"text","text":message}],"approvalPolicy":"on-request","sandboxPolicy":{"type":"readOnly","networkAccess":False}},timeout=20)
        deadline=time.monotonic()+timeout; text=[]
        while time.monotonic()<deadline:
            if cancel and cancel.is_set():
                self.interrupt(); raise InterruptedError("cancelled")
            try: event=self._events.get(timeout=.2)
            except queue.Empty: continue
            method=event.get("method"); params=event.get("params",{})
            if method=="item/agentMessage/delta":
                delta=params.get("delta","")
                if delta: text.append(delta); yield delta
            elif method=="turn/started": self.turn_id=(params.get("turn") or {}).get("id")
            elif method=="turn/completed":
                turn=params.get("turn",{}); self.turn_id=turn.get("id",self.turn_id)
                if turn.get("status")!="completed": raise CodexError("Codex turn status: "+str(turn.get("status")))
                return
            elif method=="offtec/processExited": raise CodexError("Codex app-server encerrou a conexão")
            elif method=="error": raise CodexError(str(params)[:400])
        self.interrupt(); raise TimeoutError("Codex turn timed out")
    def interrupt(self):
        if self.thread_id:
            try: self.request("turn/interrupt",{"threadId":self.thread_id,"turnId":self.turn_id},timeout=3)
            except Exception: pass
    def close(self):
        self.connected=False
        if self.proc and self.proc.poll() is None:
            try: self.proc.terminate(); self.proc.wait(timeout=2)
            except Exception:
                try: self.proc.kill()
                except Exception: pass
        self.proc=None
