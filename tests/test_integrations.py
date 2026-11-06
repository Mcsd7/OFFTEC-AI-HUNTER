import json
import tempfile
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from offtec.ai.provider_manager import ProviderManager
from offtec.ai.secrets import SecretStore
from offtec.ai.codex_adapter import CodexAdapter
from offtec.core.i18n import LANGUAGES, Translator
from offtec.core.task_manager import TaskManager
from offtec.database.repository import Repository
from offtec.interface.app import MENU, MODULES
from offtec.modules.native_analysis import RUNNERS, sql_error_review, xss_review


class FakeSSE:
    def __init__(self, lines): self.lines = iter(lines)
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def readline(self): return next(self.lines, b"")


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = Repository(self.root / "db.sqlite3")
        self.pid = self.repo.get_setting("active_project")

    def tearDown(self): self.tmp.cleanup()

    def test_every_menu_module_has_runner_and_catalogs(self):
        for menu_key, module in MODULES.items():
            self.assertIn(menu_key, MENU)
            runners = {"sql": ("sql_review", "sqlmap"), "xss": ("xss_review",)}.get(module, (module,))
            self.assertTrue(any(runner in RUNNERS for runner in runners), module)
        base = set(Translator("pt_BR").catalogs["pt_BR"])
        for lang in LANGUAGES:
            self.assertEqual(base, set(Translator(lang).catalogs[lang]))

    def test_local_sql_and_xss_review_are_offline(self):
        evidence, findings = sql_error_review("SQLite error near syntax")
        self.assertTrue(findings)
        self.assertIn("offline", evidence["method"])
        _, xss = xss_review("<script>alert(1)</script>")
        self.assertTrue(xss)
        _, escaped = xss_review("&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertFalse(escaped)

    def test_task_manager_requires_authorization_and_persists_completion(self):
        manager = TaskManager(self.repo, max_workers=1)
        try:
            with self.assertRaises(PermissionError):
                manager.submit(self.pid, "web", "https://example.test", ["example.test"])
            with self.assertRaises(PermissionError):
                manager.submit(self.pid, "web", "https://evil.test", ["evil.test"], authorized=True)
            tid = manager.submit(self.pid, "sql_review", "SQLite error near syntax", [], language="pt_BR")
            for _ in range(100):
                row = next(r for r in self.repo.tasks(self.pid) if r["id"] == tid)
                if row["status"] in ("completed", "failed", "cancelled"): break
                time.sleep(.02)
            self.assertEqual(row["status"], "completed")
            self.assertTrue(self.repo.findings(self.pid))
        finally: manager.shutdown()

    def test_cancellation_and_persisted_scope_guard(self):
        self.repo.add_scope(self.pid, "example.test")
        gate = threading.Event()
        original = RUNNERS["web"]
        def slow_runner(target, cancel=None, progress=None):
            while not cancel.is_set():
                gate.wait(.01)
            raise InterruptedError("cancelled")
        RUNNERS["web"] = slow_runner
        manager = TaskManager(self.repo, max_workers=1)
        try:
            with self.assertRaises(PermissionError):
                manager.submit(self.pid, "web", "https://evil.test", ["example.test"], authorized=True)
            tid = manager.submit(self.pid, "web", "https://example.test", ["example.test"], authorized=True)
            self.assertTrue(manager.cancel(tid))
            for _ in range(100):
                row = next(r for r in self.repo.tasks(self.pid) if r["id"] == tid)
                if row["status"] in ("cancelled", "failed", "completed"): break
                time.sleep(.02)
            self.assertEqual(row["status"], "cancelled")
        finally:
            manager.shutdown()
            RUNNERS["web"] = original

    def test_provider_streaming_and_secret_storage(self):
        secret_store = SecretStore(self.root / "private" / "credentials.json")
        provider = ProviderManager(self.repo, secret_store)
        provider.configure("local-test", "compatible", "Servidor local", "http://127.0.0.1:8081/v1", "model-x", "not-logged")
        lines = [b'data: {"choices":[{"delta":{"content":"Resposta"}}]}\n', b'data: [DONE]\n']
        captured=[]
        def fake_open(request,**kwargs):
            captured.append(json.loads(request.data.decode("utf-8")))
            return FakeSSE(lines)
        with patch("offtec.ai.provider_manager.urllib.request.urlopen", side_effect=fake_open):
            for lang in LANGUAGES:
                self.assertEqual("".join(provider.stream_chat([{"role":"user","content":"oi"}], lang)), "Resposta")
        system_prompts=[payload["messages"][0]["content"] for payload in captured]
        for expected,actual in zip(("português brasileiro","English","العربية","हिंदी","español"),system_prompts): self.assertIn(expected,actual)
        self.assertEqual(secret_store.get("provider:local-test"), "not-logged")
        if hasattr(secret_store.path.stat(), "st_mode"):
            self.assertEqual(secret_store.path.stat().st_mode & 0o777, 0o600)
        with self.repo.connect() as db:
            serialized = json.dumps([dict(r) for r in db.execute("SELECT * FROM provider_profiles")])
        self.assertNotIn("not-logged", serialized)

    def test_environment_provider_is_selectable_without_database_secret(self):
        manager=ProviderManager(self.repo,SecretStore(self.root/"env-secrets.json"))
        with patch.dict("os.environ",{"OFFTEC_AI_API_KEY":"env-secret","OFFTEC_AI_MODEL":"model-y","OFFTEC_AI_BASE_URL":"https://provider.example/v1"}):
            self.assertIn("environment",[p["id"] for p in manager.configured_profiles()])
            self.repo.set_setting("active_provider","environment")
            self.assertEqual(manager.profile()["model"],"model-y")
            self.assertEqual(manager._key(manager.profile()),"env-secret")
        with self.repo.connect() as db:
            self.assertNotIn("env-secret",str(db.execute("SELECT value FROM settings WHERE key='active_provider'").fetchone()[0]))

    def test_codex_system_instructions_follow_all_five_languages(self):
        adapter=CodexAdapter(executable="codex")
        prompts=[]
        def request(method,params,timeout=15):
            if method=="thread/start": prompts.append(params["baseInstructions"]); return {"thread":{"id":"thread-test"}}
            return {"thread":{"id":"thread-test"}}
        with patch.object(adapter,"request",side_effect=request):
            for language in LANGUAGES:
                self.assertEqual(adapter.start_thread(".",language),"thread-test")
        for prompt in prompts:
            self.assertIn("assistente de análise defensiva",prompt)
        self.assertIn("português brasileiro",prompts[0])
        self.assertIn("English",prompts[1])
        self.assertIn("español",prompts[4])
        self.assertIn("العربية",prompts[2])
        self.assertIn("हिंदी",prompts[3])


if __name__ == "__main__": unittest.main()
