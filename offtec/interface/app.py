"""Keyboard-first Termux command center; Rich is optional at runtime."""
import getpass, json, os, queue, select, shlex, shutil, sys, threading, time
from pathlib import Path
try:
    import readline  # Enables normal line editing, including cursor arrows, when available.
except ImportError:
    readline=None
from offtec.core.i18n import Translator, LANGUAGES
from offtec.core.config import EXPORT_DIR, APP_DIR
from offtec.database.repository import Repository
from offtec.core.scope_manager import ScopeManager, normalize_target
from offtec.core.task_manager import TaskManager
from offtec.ai.codex_adapter import CodexAdapter
from offtec.ai.provider_manager import ProviderManager
from offtec.ai.orchestrator import AIOrchestrator
from offtec.modules.tooling import inventory
from offtec.modules.reporting import generate
from offtec.interface.keyboard import keypress
from offtec.interface.navigation import NavigationState, move_index

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    RICH=True
except ImportError:
    Console=Panel=Table=Text=None; RICH=False

MENU=["menu.web","menu.sql","menu.recon","menu.vuln","menu.api","menu.network","menu.xss","menu.tls","menu.assets","menu.chat","menu.report","menu.lab","menu.projects","menu.history","menu.settings","menu.language","menu.exit"]
MODULES={"menu.web":"web","menu.sql":"sql","menu.recon":"recon","menu.vuln":"vulnerability","menu.api":"api","menu.network":"network","menu.xss":"xss","menu.tls":"tls","menu.assets":"assets"}
RED="\033[91m"; GRAY="\033[90m"; RESET="\033[0m"

def clear():
    if sys.stdout.isatty(): print("\033[2J\033[H",end="",flush=True)

class App:
    def __init__(self,repo=None,task_manager=None,codex=None,provider=None):
        self.repo=repo or Repository(); self.tr=Translator(self.repo.get_setting("language","pt_BR")); self.codex=codex or CodexAdapter(); self.provider=provider or ProviderManager(self.repo); self.scope=ScopeManager(); self.orchestrator=AIOrchestrator(self.repo)
        self.active=self.repo.get_setting("active_project","default"); self.tab=0; self.panel_focus=False; self.panel_tab=0; self.panel_actions=["menu.projects","task.title","menu.settings"]; self.tasks=task_manager or TaskManager(self.repo); self.repo.recover_orphan_tasks(); self.console=Console(highlight=False) if RICH else None
        self.navigation=NavigationState(len(MENU),len(self.panel_actions))
    def say(self,text="",end="\n",style=None):
        if self.console: self.console.print(Text(str(text),style=style),end=end,soft_wrap=True)
        else: print(text,end=end,flush=True)
    def pause(self):
        self.say("\n"+self.tr.t("prompt.enter"))
        if sys.stdin.isatty():
            while keypress() not in ("enter","esc","ctrlc"): pass
        else:
            try: input()
            except EOFError: pass
    def input(self,label):
        try: return input(label+": ").strip()
        except (EOFError,KeyboardInterrupt): self.say(self.tr.t("prompt.cancelled")); return ""
    def chat_input(self,label):
        """Editable chat line that can be left immediately with Esc or Q."""
        if not sys.stdin.isatty(): return self.input(label)
        import termios, tty
        fd=sys.stdin.fileno(); previous=termios.tcgetattr(fd); chars=[]
        self.say(label+" [ ESC: "+self.tr.t("chat.back_key")+" · Q: "+self.tr.t("chat.exit_key")+" ]: ",end="")
        try:
            tty.setraw(fd)
            while True:
                key=keypress()
                if key in ("esc",):
                    self.say(); return "__chat_exit__"
                if key=="ctrlc": raise KeyboardInterrupt
                if key=="enter":
                    self.say(); return "".join(chars).strip()
                if key.lower()=="q" and not chars:
                    self.say("q"); return "__chat_exit__"
                if key in ("backspace",):
                    if chars:
                        chars.pop(); self.say("\b \b",end="")
                elif len(key)==1 and key.isprintable():
                    chars.append(key); self.say(key,end="")
        finally:
            termios.tcsetattr(fd,termios.TCSADRAIN,previous)
    def choose(self,title,options):
        if not options: return None
        index=0
        while True:
            clear()
            if self.console:
                body=Table.grid(padding=(0,1)); body.add_column(width=4,justify="right"); body.add_column()
                for n,(label,_) in enumerate(options): body.add_row("❯" if n==index else "",Text(label,style="bold red" if n==index else "white"))
                self.console.print(Panel(body,title=title,border_style="red",title_align="left")); self.say(self.tr.t("prompt.select"),style="dim")
            else:
                self.say(RED+"◆ "+title+RESET+"\n")
                for n,(label,_) in enumerate(options): self.say((RED+"❯ " if n==index else "  ")+label+(RESET if n==index else ""))
                self.say("\n"+GRAY+self.tr.t("prompt.select")+RESET)
            key=keypress()
            if key in ("up","down","left","right","j","k"): index=move_index(index,len(options),key)
            elif key=="enter": return options[index][1]
            elif key in ("esc","ctrlc"): return None
    def render(self):
        clear(); codex=self.codex.status(); project=self.project_name(); items=[]
        for n,key in enumerate(MENU,1): items.append((f"{n:02}",self.tr.t(key)))
        if self.console:
            menu=Table.grid(padding=(0,1)); menu.add_column(style="bold red",width=4); menu.add_column()
            for n,(number,label) in enumerate(items): menu.add_row(("❯" if n==self.tab else "")+number,Text(label,style="bold white" if n==self.tab else "white"))
            status=Table.grid(padding=(0,1)); status.add_column(style="bold red"); status.add_column()
            status.add_row(self.tr.t("status.engine"),self.tr.t("status.connected") if codex["connected"] else self.tr.t("status.disconnected"))
            status.add_row(self.tr.t("status.provider"),self.ai_provider_name(codex["connected"]))
            status.add_row(self.tr.t("status.project"),project)
            status.add_row(self.tr.t("status.execution"),self.task_summary())
            if self.panel_focus:
                for i,key in enumerate(self.panel_actions):
                    label=self.tr.t(key)
                    if key=="task.title": label=self.tr.t("task.title")
                    status.add_row(("❯ " if i==self.panel_tab else "  ")+label, self.tr.t("prompt.enter") if i==self.panel_tab else "")
            self.console.print(Panel(Text("OFFTEC AI HUNTER",style="bold white"),subtitle=self.tr.t("app.subtitle"),border_style="red",expand=True))
            self.console.print(Panel(menu,title=self.tr.t("menu.title"),border_style="bright_red"))
            self.console.print(Panel(status,border_style="bright_red" if self.panel_focus else "red",title=self.tr.t("task.title") if self.panel_focus else None)); self.say(self.tr.t("prompt.select"),style="dim")
        else:
            self.say(RED+"╔══════════════════════════════════════════════════════╗\n║                 OFFTEC AI HUNTER                    ║\n╚══════════════════════════════════════════════════════╝"+RESET)
            self.say(self.tr.t("app.subtitle")+"\n")
            for i,key in enumerate(MENU,1): self.say((RED+"❯ " if i-1==self.tab else "  ")+f"[{i:02}] {self.tr.t(key)}"+(RESET if i-1==self.tab else ""))
            self.say("\n"+GRAY+f"{self.tr.t('status.engine')}: {self.tr.t('status.connected') if codex['connected'] else self.tr.t('status.disconnected')} · {self.tr.t('status.provider')}: {self.ai_provider_name(codex['connected'])}\n{self.tr.t('status.project')}: {project} · {self.tr.t('status.execution')}: {self.task_summary()}"+RESET)
            self.say(self.tr.t("prompt.panel_focus") if self.panel_focus else self.tr.t("prompt.menu_focus"))
            self.say("\n"+self.tr.t("prompt.select"))
    def task_summary(self):
        rows=self.repo.all_tasks(self.active); active=sum(1 for r in rows if r["status"] in ("queued","running"))
        return self.tr.t("status.running")+f" ({active})" if active else self.tr.t("status.idle")
    def ai_provider_name(self,codex_connected=None):
        if self.repo.get_setting("active_provider","codex")=="codex":
            state=self.codex.status()
            connected=state["connected"] if codex_connected is None else codex_connected
            label="status.connected" if connected else "status.disconnected"
            if connected and state.get("authenticated") is False: label="status.unauthenticated"
            return "Codex ("+self.tr.t(label)+")"
        return self.provider.display_name(self.tr)
    def project_name(self):
        return next((r["name"] for r in self.repo.projects() if r["id"]==self.active),self.tr.t("status.none"))
    def main(self):
        if not sys.stdin.isatty(): self.say("OFFTEC AI HUNTER requer um terminal interativo."); return
        try:
            while True:
                self.render(); key=keypress(); action=self.navigation.handle(key)
                self.tab=self.navigation.menu_index; self.panel_tab=self.navigation.panel_index; self.panel_focus=self.navigation.panel_focus
                if action=="activate":
                    if self.panel_focus:
                        target=self.panel_actions[self.panel_tab]
                        if target=="menu.projects": self.projects()
                        elif target=="task.title": self.task_monitor()
                        else: self.settings()
                    else: self.dispatch(MENU[self.tab])
                elif key.isdigit() and key!="0":
                    index=int(key)-1
                    if select.select([sys.stdin],[],[],.25)[0]:
                        digit=keypress()
                        if digit.isdigit(): index=int(key+digit)-1
                    if 0<=index<len(MENU): self.dispatch(MENU[index])
                elif key=="ctrlc": return
        finally: self.tasks.shutdown(); self.codex.close()
    def dispatch(self,key):
        if key=="menu.language": self.language()
        elif key=="menu.settings": self.settings()
        elif key=="menu.projects": self.projects()
        elif key=="menu.chat": self.chat()
        elif key=="menu.report": self.report()
        elif key=="menu.history": self.history()
        elif key=="menu.lab": self.lab()
        elif key=="menu.exit": raise SystemExit
        elif key in MODULES: self.analysis(key)
    def language(self):
        code=self.choose(self.tr.t("language.title"),[(self.tr.t(LANGUAGES[c]),c) for c in LANGUAGES])
        if code: self.repo.set_setting("language",code); self.tr.set_language(code); self.say(self.tr.t("language.changed")); self.pause()
    def projects(self):
        actions=[(self.tr.t("project.new"),"new"),(self.tr.t("scope.title"),"scopes"),(self.tr.t("common.back"),None)]
        selected=self.choose(self.tr.t("project.title"),[(r["name"]+(" ✓" if r["id"]==self.active else ""),"project:"+r["id"]) for r in self.repo.projects()]+actions)
        if selected is None: return
        if selected=="new":
            name=self.input(self.tr.t("project.name"))
            if name: self.active=self.repo.create_project(name); self.repo.set_setting("active_project",self.active); self.say(self.tr.t("project.created")); self.pause()
        elif selected=="scopes": self.manage_scopes()
        elif selected.startswith("project:"):
            pid=selected.split(":",1)[1]; self.active=pid; self.repo.set_setting("active_project",pid)
            actions=[(self.tr.t("project.rename"),"rename"),(self.tr.t("project.delete"),"delete"),(self.tr.t("common.back"),None)]
            action=self.choose(self.tr.t("project.current")+": "+self.project_name(),actions)
            if action=="rename":
                name=self.input(self.tr.t("project.name"))
                if name: self.repo.rename_project(pid,name)
            elif action=="delete":
                if len(self.repo.projects())<2: self.say(self.tr.t("project.cannot_delete_last")); self.pause(); return
                if any(r["status"] in ("queued","running") for r in self.repo.tasks(pid)):
                    self.say(self.tr.t("project.delete_active")); self.pause(); return
                if self.confirm(self.tr.t("project.confirm_delete")):
                    self.repo.delete_project(pid); self.active=self.repo.projects()[0]["id"]; self.repo.set_setting("active_project",self.active)
    def manage_scopes(self):
        while True:
            hosts=self.repo.scopes(self.active)
            choices=[(self.tr.t("scope.add"),"add")]+[(self.tr.t("scope.remove")+": "+h,"remove:"+h) for h in hosts]+[(self.tr.t("common.back"),None)]
            action=self.choose(self.tr.t("scope.title"),choices)
            if not action: return
            if action=="add":
                raw=self.input(self.tr.t("scope.host"))
                try: _,host=normalize_target(raw if "://" in raw else "https://"+raw)
                except ValueError: self.say(self.tr.t("analysis.invalid_target")); self.pause(); continue
                self.repo.add_scope(self.active,host); self.say(self.tr.t("scope.added")); self.pause()
            elif action.startswith("remove:"):
                self.repo.remove_scope(self.active,action.split(":",1)[1]); self.say(self.tr.t("scope.removed")); self.pause()
    def confirm(self,prompt):
        return self.input(prompt+" [y/N]").lower() in ("y","yes","s","sim")
    def analysis(self,key):
        module=MODULES[key]
        if module in ("sql","xss"):
            if module=="sql":
                choices=[(self.tr.t("analysis.local_input"),"review")]
                if inventory().get("sqlmap"): choices.insert(0,("SQLMap ("+self.tr.t("analysis.active_warning")+")","sqlmap"))
                mode=self.choose(self.tr.t("menu.sql"),choices)
                if not mode: return
                if mode=="sqlmap": module="sqlmap"
                else:
                    sample=self.input(self.tr.t("analysis.local_input"));
                    if sample: self.queue_task("sql_review",sample,())
                    return
            else:
                sample=self.input(self.tr.t("analysis.local_input"))
                if sample: self.queue_task("xss_review",sample,())
                return
        if module=="sqlmap" and not inventory().get("sqlmap"):
            self.say(self.tr.t("analysis.tool_missing",tool="SQLMap")); self.pause(); return
        target=self.input(self.tr.t("prompt.target"))
        if not target: return
        try: parsed,host=normalize_target(target)
        except ValueError: self.say(self.tr.t("analysis.invalid_target")); self.pause(); return
        hosts=self.repo.scopes(self.active)
        if host not in hosts:
            if self.confirm(self.tr.t("scope.register_prompt")):
                self.repo.add_scope(self.active,host); hosts=self.repo.scopes(self.active)
            else: self.say(self.tr.t("error.scope")); self.pause(); return
        active=(module in ("network","sqlmap","api","assets")) or (module=="vulnerability" and bool(inventory().get("nuclei")))
        warning=self.tr.t("analysis.active_warning") if active else self.tr.t("analysis.scope")
        if not self.confirm(warning+" "+self.tr.t("analysis.active_confirm")): return
        self.queue_task(module,parsed.geturl(),hosts)
    def queue_task(self,module,target,hosts):
        tid=self.tasks.submit(self.active,module,target,hosts,language=self.tr.lang,authorized=module not in ("sql_review","xss_review"))
        self.say(self.tr.t("task.submitted")+" · "+tid[:8]); self.task_monitor(tid)
    def task_monitor(self,focus=None):
        if not sys.stdin.isatty():
            rows=self.repo.all_tasks(self.active)[:20]
            for row in rows: self.say(f"{row['id'][:8]} · {row['module']} · {row['status']} {row['progress']}%")
            return
        index=next((i for i,row in enumerate(self.repo.all_tasks(self.active)[:20]) if row["id"]==focus),0) if focus else 0
        while True:
            rows=self.repo.all_tasks(self.active)[:20]; index=min(index,max(0,len(rows)-1)); clear()
            if self.console:
                table=Table(title=self.tr.t("task.title"),border_style="red"); table.add_column("ID"); table.add_column(self.tr.t("common.module")); table.add_column(self.tr.t("status.execution")); table.add_column(self.tr.t("task.progress")); table.add_column(self.tr.t("common.target"))
                for i,row in enumerate(rows):
                    status_key="task."+row["status"]; status=self.tr.t(status_key) if status_key in self.tr.catalogs[self.tr.lang] else row["status"]
                    table.add_row(("❯ " if i==index else "")+row["id"][:8],row["module"],status,f"{row['progress']}%",row["target"][:38])
                self.console.print(table)
            else:
                self.say(RED+self.tr.t("task.title")+RESET)
                for i,row in enumerate(rows):
                    status_key="task."+row["status"]; status=self.tr.t(status_key) if status_key in self.tr.catalogs[self.tr.lang] else row["status"]
                    self.say((RED+"❯ " if i==index else "  ")+f"{row['id'][:8]} · {row['module']} · {status} {row['progress']}% · {row['target'][:35]}")
            self.say(self.tr.t("prompt.select")+" · Enter: detalhes")
            ready=select.select([sys.stdin],[],[],.7)[0]
            if not ready: continue
            key=keypress()
            if key in ("up","down","left","right","j","k") and rows:index=move_index(index,len(rows),key)
            elif key=="ctrlc":
                if rows and rows[index]["status"] in ("queued","running"):
                    self.tasks.cancel(rows[index]["id"])
                return
            elif key in ("esc","q"):
                if rows and rows[index]["status"] in ("running","queued"):
                    choice=self.choose(self.tr.t("chat.leave_task"),[(self.tr.t("chat.leave_background"),"background"),(self.tr.t("task.cancel"),"cancel"),(self.tr.t("common.back"),"stay")])
                    if choice=="cancel": self.tasks.cancel(rows[index]["id"])
                    elif choice=="stay": continue
                return
            elif key=="enter" and rows:
                row=rows[index]; clear(); self.say(f"{row['module']} · {row['target']} · {row['status']} · {row['progress']}%")
                if row["error"]: self.say(self.tr.t("task.error")+": "+row["error"])
                if row["result"]: self.say((row["result"] or "")[:5000])
                for ev in self.repo.task_events(row["id"])[-12:]: self.say(ev["created_at"]+" · "+ev["event"])
                actions=[]
                if row["status"] in ("running","queued"): actions.append((self.tr.t("task.cancel"),"cancel"))
                actions.append((self.tr.t("common.back"),"back"))
                if self.choose(self.tr.t("task.title"),actions)=="cancel": self.tasks.cancel(row["id"])
    def clear_screen(self):
        clear()
    def settings(self):
        while True:
            choices=[(self.tr.t("language.title"),"language"),(self.tr.t("provider.title"),"providers"),(self.tr.t("scope.title"),"scopes"),(self.tr.t("settings.tools"),"tools"),(self.tr.t("settings.codex"),"codex"),(self.tr.t("task.title"),"tasks"),(self.tr.t("common.back"),None)]
            action=self.choose(self.tr.t("settings.title"),choices)
            if action is None:return
            if action=="language": self.language()
            elif action=="providers": self.providers()
            elif action=="scopes": self.manage_scopes()
            elif action=="tools": self.show_tools()
            elif action=="codex": self.check_codex()
            elif action=="tasks": self.task_monitor()
    def check_codex(self):
        state=self.codex.status(); self.say((self.tr.t("status.connected") if state["connected"] else self.tr.t("status.disconnected"))+" · "+str(state.get("version") or "")); self.say(state["reason"]); self.pause()
    def show_tools(self):
        self.clear_screen(); self.say(self.tr.t("settings.tools"))
        for tool,path in inventory().items(): self.say(f"{tool}: {path or self.tr.t('status.unknown')}")
        self.pause()
    def providers(self):
        while True:
            choices=[(self.tr.t("provider.add"),"add")]
            profiles=self.provider.configured_profiles()
            choices.extend(((self.tr.t("provider.environment") if p["id"]=="environment" else p["name"])+" · "+p["model"],"select:"+p["id"]) for p in profiles)
            choices.extend([(self.tr.t("provider.test"),"test"),(self.tr.t("common.back"),None)])
            action=self.choose(self.tr.t("provider.title"),choices)
            if action is None: return
            if action=="add": self.add_provider()
            elif action=="test":
                pid=self.repo.get_setting("active_provider","codex")
                result=self.provider.test(pid); self.say(self.tr.t("provider.ready") if result["connected"] else self.tr.t("provider.failed")); self.pause()
            elif action.startswith("select:"):
                self.repo.set_setting("active_provider",action.split(":",1)[1]); self.say(self.tr.t("provider.selected")); self.pause()
    def add_provider(self):
        kinds=[("Gemini","gemini"),("Groq","groq"),("OpenAI-compatible","compatible")]
        kind=self.choose(self.tr.t("provider.kind"),[(self.tr.t("provider."+k) if k!="compatible" else self.tr.t("provider.openai"),k) for _,k in kinds])
        if not kind:return
        pid="provider-"+str(int(time.time()))
        name=self.input(self.tr.t("provider.name")) or kind
        default={"gemini":"https://generativelanguage.googleapis.com/v1beta","groq":"https://api.groq.com/openai/v1","compatible":""}[kind]
        url=self.input(self.tr.t("provider.url")+f" [{default}]") or default
        model=self.input(self.tr.t("provider.model"))
        key=getpass.getpass(self.tr.t("provider.key")+": ").strip()
        try:
            self.provider.configure(pid,kind,name,url,model,key); self.say(self.tr.t("provider.saved")); self.pause()
        except (ValueError,OSError,RuntimeError) as exc: self.say(self.tr.t("common.error")+": "+str(exc)); self.pause()
    def chat(self):
        conv=self.choose_conversation()
        if not conv:return
        while True:
            self.clear_screen(); self.say(RED+self.tr.t("chat.title")+RESET+" · "+conv["title"]+"\n")
            rows=self.repo.messages(conv["id"])
            if not rows:self.say(self.tr.t("chat.empty"))
            for row in rows[-24:]: self.say(f"{self.tr.t('chat.user') if row['role']=='user' else self.tr.t('chat.assistant')}: {row['content']}\n")
            self.say(self.tr.t("chat.command_help"))
            msg=self.chat_input(self.tr.t("prompt.input"))
            if msg in ("__chat_exit__","/q","/quit"): return
            if not msg: continue
            if msg=="/help": self.say(self.tr.t("chat.command_help")); self.pause(); continue
            if msg=="/report": self.report(); continue
            if msg.startswith("/scan "):
                self.chat_scan_command(msg); continue
            if msg=="/new": conv=self.repo.create_conversation(self.active); continue
            if msg=="/rename":
                title=self.input(self.tr.t("chat.rename"));
                if title:self.repo.rename_conversation(conv["id"],title); conv["title"]=title
                continue
            if msg=="/delete":
                if self.confirm(self.tr.t("chat.delete")+"?"):
                    self.repo.delete_conversation(conv["id"]); return
                continue
            if msg=="/export": self.export_conversation(conv); continue
            self.repo.add_message(conv["id"],"user",msg)
            provider_id=self.repo.get_setting("active_provider","codex")
            context=self.orchestrator.system_context(self.active,self.tr.lang)
            augmented=msg+"\n\n"+self.tr.t("chat.context")+"\n"+context
            if self.stream_answer(conv,provider_id,augmented): return
    def choose_conversation(self):
        rows=self.repo.conversations(self.active)
        choices=[(r["title"]+" · "+r["created_at"],"id:"+r["id"]) for r in rows]
        choices += [(self.tr.t("chat.new"),"new"),(self.tr.t("common.back"),None)]
        pick=self.choose(self.tr.t("chat.conversations"),choices)
        if not pick:return None
        if pick=="new":return self.repo.create_conversation(self.active)
        cid=pick.split(":",1)[1]
        return next((dict(x) for x in rows if x["id"]==cid),None)
    def stream_answer(self,conv,provider_id,message):
        chunks=queue.Queue(); cancel=threading.Event(); result={"ok":False}
        def work():
            try:
                if provider_id=="codex":
                    if not self.codex.connect(): raise RuntimeError(self.codex.status()["reason"])
                    if conv.get("provider")!="codex" or not conv.get("thread_id"):
                        context=self.orchestrator.system_context(self.active,self.tr.lang)
                        thread=self.codex.start_thread(str(Path.cwd()),self.tr.lang,context,resume_id=conv.get("thread_id") if conv.get("provider")=="codex" else None)
                        self.repo.set_conversation_session(conv["id"],"codex",thread); conv["provider"]="codex"; conv["thread_id"]=thread
                    for delta in self.codex.stream_turn(message,cancel=cancel):
                        if cancel.is_set(): break
                        chunks.put(("delta",delta))
                else:
                    history=[{"role":r["role"],"content":r["content"]} for r in self.repo.messages(conv["id"]) if r["role"] in ("user","assistant")][-30:]
                    for delta in self.provider.stream_chat(history,self.tr.lang,provider_id,system_context=self.orchestrator.system_context(self.active,self.tr.lang),cancel_event=cancel):
                        if cancel.is_set(): break
                        chunks.put(("delta",delta))
                result["ok"]=not cancel.is_set()
            except Exception as exc: result["error"]=str(exc)
            finally: chunks.put(("done",None))
        threading.Thread(target=work,name="offtec-ai-stream",daemon=True).start()
        self.say(self.tr.t("chat.assistant")+": ",end="")
        full=[]; done=False; leave_chat=False; quit_app=False
        while not done:
            try: kind,value=chunks.get(timeout=.1)
            except queue.Empty: kind=value=None
            if kind=="delta": self.say(value,end=""); full.append(value)
            elif kind=="done": done=True
            if sys.stdin.isatty() and select.select([sys.stdin],[],[],0)[0]:
                key=keypress()
                if key in ("ctrlc","esc","q"):
                    cancel.set(); leave_chat=key in ("esc","q"); quit_app=key=="ctrlc"
                    self.say("\n"+self.tr.t("prompt.cancelled"))
        self.say()
        if full: self.repo.add_message(conv["id"],"assistant","".join(full))
        if quit_app: raise KeyboardInterrupt
        elif result.get("error"):
            self.say(self.tr.t("chat.no_engine")); self.say(result["error"][:500]); self.pause()
        return leave_chat
    def chat_scan_command(self,message):
        try: _,module,target=shlex.split(message)
        except ValueError: self.say(self.tr.t("prompt.invalid")); return
        aliases={"web":"web","tls":"tls","recon":"recon","api":"api","assets":"assets","network":"network","vuln":"vulnerability"}
        if module not in aliases: self.say(self.tr.t("prompt.invalid")); return
        key=next((k for k,v in MODULES.items() if v==aliases[module]),None)
        if key:self.analysis(key)
    def export_conversation(self,conv):
        EXPORT_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
        path=EXPORT_DIR/(conv["id"]+".json")
        data={"title":conv["title"],"project":self.project_name(),"language":self.tr.lang,"messages":[dict(r) for r in self.repo.messages(conv["id"])]}
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); os.chmod(path,0o600); self.say(str(path)); self.pause()
    def report(self):
        if not self.repo.all_tasks(self.active): self.say(self.tr.t("report.empty")); self.pause(); return
        base=generate(self.repo,self.active,self.project_name(),self.tr)
        self.say(self.tr.t("report.created")+f" {base}.[html|json|txt]")
        self.say(self.tr.t("report.pdf_fallback")); self.pause()
    def history(self):
        action=self.choose(self.tr.t("history.title"),[(self.tr.t("task.title"),"tasks"),(self.tr.t("report.title"),"reports"),(self.tr.t("common.back"),None)])
        if action=="tasks": self.task_monitor()
        elif action=="reports":
            clear(); rows=self.repo.report_history(self.active)
            for r in rows: self.say(f"{r['created_at']} · {r['format']} · {r['language']} · {r['path']}")
            if not rows:self.say(self.tr.t("report.empty"))
            self.pause()
    def lab(self):
        options=[(self.tr.t("lab.sql"),"sql"),(self.tr.t("lab.xss"),"xss"),(self.tr.t("lab.http"),"http"),(self.tr.t("common.back"),None)]
        exercise=self.choose(self.tr.t("lab.title"),options)
        if not exercise:return
        if exercise=="sql": sample="You have an error in your SQL syntax near '"; self.tasks.submit(self.active,"sql_review",sample,(),self.tr.lang)
        elif exercise=="xss": sample="<script>alert(1)</script>"; self.tasks.submit(self.active,"xss_review",sample,(),self.tr.lang)
        else: sample="Strict-Transport-Security: max-age=31536000; includeSubDomains\nContent-Security-Policy: default-src 'self'"
        self.say(self.tr.t("lab.exercise")+": "+sample); self.say(self.tr.t("lab.info")); self.pause()

def run():
    try: App().main()
    except KeyboardInterrupt: print("\nOFFTEC AI HUNTER")
