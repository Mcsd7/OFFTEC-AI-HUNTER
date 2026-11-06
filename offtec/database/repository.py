import json, os, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from offtec.core.config import DB_PATH

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb):
        try: return super().__exit__(exc_type, exc, tb)
        finally: self.close()

class Repository:
    def __init__(self, path=DB_PATH):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try: os.chmod(Path(path).parent,0o700)
        except OSError: pass
        with self.connect() as db:
            db.executescript('''
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,title TEXT NOT NULL,created_at TEXT NOT NULL, FOREIGN KEY(project_id) REFERENCES projects(id));
            CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,created_at TEXT NOT NULL, FOREIGN KEY(conversation_id) REFERENCES conversations(id));
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,module TEXT NOT NULL,target TEXT NOT NULL,status TEXT NOT NULL,result TEXT,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS findings(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,task_id TEXT,severity TEXT NOT NULL,title TEXT NOT NULL,details TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS execution_log(id TEXT PRIMARY KEY,task_id TEXT,event TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS project_scopes(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,host TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(project_id,host),FOREIGN KEY(project_id) REFERENCES projects(id));
            CREATE TABLE IF NOT EXISTS task_events(id TEXT PRIMARY KEY,task_id TEXT NOT NULL,event TEXT NOT NULL,progress INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,FOREIGN KEY(task_id) REFERENCES tasks(id));
            CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,task_id TEXT,path TEXT NOT NULL,format TEXT NOT NULL,language TEXT NOT NULL,created_at TEXT NOT NULL,FOREIGN KEY(project_id) REFERENCES projects(id));
            CREATE TABLE IF NOT EXISTS ai_sessions(project_id TEXT NOT NULL,provider TEXT NOT NULL,session_id TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(project_id,provider),FOREIGN KEY(project_id) REFERENCES projects(id));
            CREATE TABLE IF NOT EXISTS provider_profiles(id TEXT PRIMARY KEY,name TEXT NOT NULL,kind TEXT NOT NULL,base_url TEXT NOT NULL,model TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
            ''')
            # Additive migrations preserve user rows and old databases.
            columns={r[1] for r in db.execute("PRAGMA table_info(tasks)")}
            for column,definition in (("progress","INTEGER NOT NULL DEFAULT 0"),("error","TEXT"),("started_at","TEXT"),("finished_at","TEXT"),("cancel_requested","INTEGER NOT NULL DEFAULT 0")):
                if column not in columns: db.execute(f"ALTER TABLE tasks ADD COLUMN {column} {definition}")
            columns={r[1] for r in db.execute("PRAGMA table_info(conversations)")}
            for column,definition in (("provider","TEXT"),("thread_id","TEXT")):
                if column not in columns: db.execute(f"ALTER TABLE conversations ADD COLUMN {column} {definition}")
            columns={r[1] for r in db.execute("PRAGMA table_info(findings)")}
            for column,definition in (("confidence","REAL NOT NULL DEFAULT 0.5"),("recommendation","TEXT NOT NULL DEFAULT ''"),("title_key","TEXT"),("details_key","TEXT"),("recommendation_key","TEXT")):
                if column not in columns: db.execute(f"ALTER TABLE findings ADD COLUMN {column} {definition}")
            db.execute("INSERT OR IGNORE INTO settings VALUES('schema_version','2')")
            if not db.execute("SELECT 1 FROM projects LIMIT 1").fetchone():
                db.execute("INSERT INTO projects VALUES(?,?,?)", ("default", "Projeto inicial", now()))
            if not db.execute("SELECT 1 FROM settings WHERE key='language'").fetchone():
                db.execute("INSERT INTO settings VALUES('language','pt_BR')")
            if not db.execute("SELECT 1 FROM settings WHERE key='active_project'").fetchone():
                db.execute("INSERT INTO settings VALUES('active_project','default')")
            if not db.execute("SELECT 1 FROM settings WHERE key='active_provider'").fetchone():
                db.execute("INSERT INTO settings VALUES('active_provider','codex')")
    def connect(self):
        previous_umask=os.umask(0o077)
        try: db=sqlite3.connect(self.path, factory=ClosingConnection)
        finally: os.umask(previous_umask)
        try: os.chmod(self.path,0o600)
        except OSError: pass
        db.row_factory=sqlite3.Row; db.execute("PRAGMA foreign_keys=ON"); return db
    def get_setting(self,key,default=None):
        with self.connect() as d:
            r=d.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone(); return r[0] if r else default
    def set_setting(self,key,value):
        with self.connect() as d: d.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(value)))
    def projects(self):
        with self.connect() as d: return d.execute("SELECT * FROM projects ORDER BY created_at").fetchall()
    def create_project(self,name):
        name=name.strip()
        if not name: raise ValueError("project name required")
        pid=uuid.uuid4().hex
        with self.connect() as d: d.execute("INSERT INTO projects VALUES(?,?,?)",(pid,name,now()))
        return pid
    def conversation(self,project_id):
        with self.connect() as d:
            r=d.execute("SELECT * FROM conversations WHERE project_id=? ORDER BY created_at DESC LIMIT 1",(project_id,)).fetchone()
            if r: return dict(r)
            cid=uuid.uuid4().hex; d.execute("INSERT INTO conversations(id,project_id,title,created_at) VALUES(?,?,?,?)",(cid,project_id,"Conversa",now())); return {"id":cid,"project_id":project_id,"title":"Conversa"}
    def create_conversation(self,project_id,title="Conversa"):
        cid=uuid.uuid4().hex
        with self.connect() as d: d.execute("INSERT INTO conversations(id,project_id,title,created_at) VALUES(?,?,?,?)",(cid,project_id,title,now()))
        return {"id":cid,"project_id":project_id,"title":title}
    def rename_conversation(self,cid,title):
        with self.connect() as d: d.execute("UPDATE conversations SET title=? WHERE id=?",(title.strip()[:120],cid))
    def set_conversation_session(self,cid,provider,thread_id):
        with self.connect() as d: d.execute("UPDATE conversations SET provider=?,thread_id=? WHERE id=?",(provider,thread_id,cid))
    def delete_conversation(self,cid):
        with self.connect() as d:
            d.execute("DELETE FROM messages WHERE conversation_id=?",(cid,)); d.execute("DELETE FROM conversations WHERE id=?",(cid,))
    def conversations(self,project_id):
        with self.connect() as d: return d.execute("SELECT * FROM conversations WHERE project_id=? ORDER BY created_at DESC",(project_id,)).fetchall()
    def messages(self,cid):
        with self.connect() as d: return d.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at",(cid,)).fetchall()
    def add_message(self,cid,role,content):
        with self.connect() as d: d.execute("INSERT INTO messages VALUES(?,?,?,?,?)",(uuid.uuid4().hex,cid,role,content,now()))
    def create_task(self,pid,module,target):
        tid=uuid.uuid4().hex
        with self.connect() as d: d.execute("INSERT INTO tasks(id,project_id,module,target,status,result,created_at,progress) VALUES(?,?,?,?,?,?,?,0)",(tid,pid,module,target,"queued",None,now()))
        return tid
    def update_task(self,tid,status=None,progress=None,result=None,error=None,cancel_requested=None):
        with self.connect() as d:
            if status:
                d.execute("UPDATE tasks SET status=?,started_at=CASE WHEN ?='running' AND started_at IS NULL THEN ? ELSE started_at END,finished_at=CASE WHEN ? IN ('completed','failed','cancelled') THEN ? ELSE finished_at END WHERE id=?",(status,status,now(),status,now(),tid))
            if progress is not None: d.execute("UPDATE tasks SET progress=? WHERE id=?",(max(0,min(100,int(progress))),tid))
            if result is not None: d.execute("UPDATE tasks SET result=? WHERE id=?",(result,tid))
            if error is not None: d.execute("UPDATE tasks SET error=? WHERE id=?",(error,tid))
            if cancel_requested is not None: d.execute("UPDATE tasks SET cancel_requested=? WHERE id=?",(int(cancel_requested),tid))
    def finish_task(self,tid,status,result):
        self.update_task(tid,status=status,progress=100 if status=="completed" else None,result=result)
    def log_task(self,tid,event,progress=0):
        with self.connect() as d:
            d.execute("INSERT INTO task_events VALUES(?,?,?,?,?)",(uuid.uuid4().hex,tid,event,int(progress),now()))
            d.execute("INSERT INTO execution_log VALUES(?,?,?,?)",(uuid.uuid4().hex,tid,event,now()))
            d.execute("UPDATE tasks SET progress=? WHERE id=?",(int(progress),tid))
    def task_events(self,tid):
        with self.connect() as d: return d.execute("SELECT * FROM task_events WHERE task_id=? ORDER BY created_at",(tid,)).fetchall()
    def add_scope(self,pid,host):
        with self.connect() as d: d.execute("INSERT OR IGNORE INTO project_scopes VALUES(?,?,?,?)",(uuid.uuid4().hex,pid,host,now()))
    def remove_scope(self,pid,host):
        with self.connect() as d: d.execute("DELETE FROM project_scopes WHERE project_id=? AND host=?",(pid,host))
    def scopes(self,pid):
        with self.connect() as d: return [r[0] for r in d.execute("SELECT host FROM project_scopes WHERE project_id=? ORDER BY host",(pid,))]
    def save_ai_session(self,pid,provider,session_id):
        with self.connect() as d: d.execute("INSERT INTO ai_sessions VALUES(?,?,?,?) ON CONFLICT(project_id,provider) DO UPDATE SET session_id=excluded.session_id,updated_at=excluded.updated_at",(pid,provider,session_id,now()))
    def get_ai_session(self,pid,provider):
        with self.connect() as d:
            r=d.execute("SELECT session_id FROM ai_sessions WHERE project_id=? AND provider=?",(pid,provider)).fetchone(); return r[0] if r else None
    def save_provider(self,pid,name,kind,base_url,model,enabled=True):
        with self.connect() as d: d.execute("INSERT INTO provider_profiles VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,kind=excluded.kind,base_url=excluded.base_url,model=excluded.model,enabled=excluded.enabled",(pid,name,kind,base_url,model,int(enabled),now()))
    def rename_project(self,pid,name):
        with self.connect() as d: d.execute("UPDATE projects SET name=? WHERE id=?",(name.strip()[:120],pid))
    def delete_project(self,pid):
        with self.connect() as d:
            d.execute("DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE project_id=?)",(pid,))
            d.execute("DELETE FROM conversations WHERE project_id=?",(pid,))
            d.execute("DELETE FROM project_scopes WHERE project_id=?",(pid,))
            d.execute("DELETE FROM ai_sessions WHERE project_id=?",(pid,))
            d.execute("DELETE FROM reports WHERE project_id=?",(pid,))
            d.execute("DELETE FROM findings WHERE project_id=?",(pid,))
            d.execute("DELETE FROM task_events WHERE task_id IN (SELECT id FROM tasks WHERE project_id=?)",(pid,))
            d.execute("DELETE FROM execution_log WHERE task_id IN (SELECT id FROM tasks WHERE project_id=?)",(pid,))
            d.execute("DELETE FROM tasks WHERE project_id=?",(pid,))
            d.execute("DELETE FROM projects WHERE id=?",(pid,))
    def providers(self):
        with self.connect() as d: return d.execute("SELECT * FROM provider_profiles ORDER BY created_at").fetchall()
    def record_report(self,pid,task_id,path,fmt,language):
        rid=uuid.uuid4().hex
        with self.connect() as d: d.execute("INSERT INTO reports VALUES(?,?,?,?,?,?,?)",(rid,pid,task_id,str(path),fmt,language,now()))
        return rid
    def report_history(self,pid):
        with self.connect() as d: return d.execute("SELECT * FROM reports WHERE project_id=? ORDER BY created_at DESC",(pid,)).fetchall()
    def add_finding(self,pid,tid,severity,title,details,evidence,confidence=.5,recommendation="",title_key=None,details_key=None,recommendation_key=None):
        with self.connect() as d: d.execute("INSERT INTO findings(id,project_id,task_id,severity,title,details,evidence,created_at,confidence,recommendation,title_key,details_key,recommendation_key) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(uuid.uuid4().hex,pid,tid,severity,title,details,json.dumps(evidence,ensure_ascii=False),now(),float(confidence),recommendation,title_key,details_key,recommendation_key))
    def findings(self,pid):
        with self.connect() as d: return d.execute("SELECT * FROM findings WHERE project_id=? ORDER BY created_at DESC",(pid,)).fetchall()
    def tasks(self,pid):
        with self.connect() as d: return d.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY created_at DESC",(pid,)).fetchall()
    def all_tasks(self,pid=None):
        with self.connect() as d:
            return d.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY created_at DESC",(pid,)).fetchall() if pid else d.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
    def recover_orphan_tasks(self):
        with self.connect() as d:
            return d.execute("UPDATE tasks SET status='failed',error='Processo foi encerrado antes da conclusão.',finished_at=? WHERE status IN ('queued','running')",(now(),)).rowcount
