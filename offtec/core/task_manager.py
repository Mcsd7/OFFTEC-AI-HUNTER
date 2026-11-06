from concurrent.futures import ThreadPoolExecutor
from threading import Event, RLock
import json
from offtec.database.repository import Repository
from offtec.modules.native_analysis import RUNNERS
from offtec.core.i18n import Translator
from offtec.modules.tooling import sanitize_value

class TaskManager:
    """Small bounded worker pool; task state and checkpoints survive restarts."""
    def __init__(self,repo:Repository,max_workers=2):
        self.repo=repo; self.pool=ThreadPoolExecutor(max_workers=max_workers,thread_name_prefix="offtec-task"); self.lock=RLock(); self.cancel_tokens={}; self.futures={}
    def submit(self,project_id,module,target,authorized_hosts,language="pt_BR",authorized=False):
        if module not in RUNNERS: raise ValueError("Unsupported module")
        if module not in ("sql_review","xss_review") and not authorized:
            raise PermissionError("explicit user authorization confirmation is required")
        if module not in ("sql_review","xss_review"):
            persisted=set(self.repo.scopes(project_id))
            supplied=set(authorized_hosts)
            if not persisted or not supplied.issubset(persisted):
                raise PermissionError("authorization hosts must come from the persisted project scope")
            from offtec.core.scope_manager import ScopeManager
            ScopeManager().validate(target,persisted)
        tid=self.repo.create_task(project_id,module,target); token=Event()
        with self.lock:
            self.cancel_tokens[tid]=token
            self.repo.log_task(tid,"queued",0)
            future=self.pool.submit(self._run,tid,project_id,module,target,tuple(authorized_hosts),language,token)
            self.futures[tid]=future
        return tid
    def _run(self,tid,pid,module,target,hosts,language,cancel):
        try:
            self.repo.update_task(tid,status="running"); self.repo.log_task(tid,"started",5)
            from offtec.core.scope_manager import ScopeManager
            if module not in ("sql_review","xss_review"):
                ScopeManager().validate(target,hosts)
            if cancel.is_set(): raise InterruptedError("cancelled")
            runner=RUNNERS[module]
            last_progress=[5]
            def report_progress(value,event="running"):
                value=max(last_progress[0],min(95,int(value)))
                if value-last_progress[0]<5 and event=="running": return
                self.repo.update_task(tid,progress=value)
                self.repo.log_task(tid,event,value); last_progress[0]=value
            evidence,findings=runner(target,cancel=cancel,progress=report_progress)
            evidence=sanitize_value(evidence); findings=sanitize_value(findings)
            self.repo.log_task(tid,"saving evidence",90)
            tr=Translator(language)
            for finding in findings:
                title=tr.t(finding.get("title_key","")) if finding.get("title_key") else finding.get("title",module)
                details=tr.t(finding.get("details_key","")) if finding.get("details_key") else finding.get("details","")
                recommendation=tr.t(finding.get("recommendation_key","")) if finding.get("recommendation_key") else finding.get("recommendation","")
                self.repo.add_finding(pid,tid,finding["severity"],title,details,finding.get("evidence",{}),finding.get("confidence",.5),recommendation,finding.get("title_key"),finding.get("details_key"),finding.get("recommendation_key"))
            self.repo.update_task(tid,status="completed",progress=100,result=json.dumps(evidence,ensure_ascii=False),error=None)
            self.repo.log_task(tid,"completed",100)
        except InterruptedError:
            self.repo.update_task(tid,status="cancelled",error="cancelled")
            self.repo.log_task(tid,"cancelled",0)
        except Exception as exc:
            self.repo.update_task(tid,status="failed",error=f"{type(exc).__name__}: {str(exc)[:500]}")
            self.repo.log_task(tid,"failed: "+type(exc).__name__,0)
        finally:
            with self.lock:
                self.cancel_tokens.pop(tid,None); self.futures.pop(tid,None)
    def cancel(self,task_id):
        with self.lock:
            token=self.cancel_tokens.get(task_id)
            if token:
                token.set(); self.repo.update_task(task_id,cancel_requested=True); self.repo.log_task(task_id,"cancellation requested",0); return True
            row=next((r for r in self.repo.all_tasks() if r["id"]==task_id),None)
            if row and row["status"]=="queued": self.repo.update_task(task_id,status="cancelled",cancel_requested=True,error="cancelled"); return True
            return False
    def shutdown(self):
        with self.lock:
            for token in self.cancel_tokens.values(): token.set()
        self.pool.shutdown(wait=False,cancel_futures=True)
