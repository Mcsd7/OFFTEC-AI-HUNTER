import json, tempfile, unittest
import os
from pathlib import Path
from offtec.database.repository import Repository
from offtec.core.i18n import Translator, LANGUAGES
from offtec.core.scope_manager import ScopeManager, normalize_target

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.repo=Repository(Path(self.tmp.name)/"test.sqlite3")
    def tearDown(self): self.tmp.cleanup()
    def test_default_language_and_catalog_coverage(self):
        self.assertEqual(self.repo.get_setting("language"),"pt_BR")
        catalogs={c:json.loads((Path(__file__).parents[1]/"locales"/(c+".json")).read_text(encoding="utf-8")) for c in LANGUAGES}
        required=set(catalogs["pt_BR"])
        for code,catalog in catalogs.items():
            self.assertEqual(required-set(catalog),set(),code)
            self.assertTrue(all(isinstance(v,str) and v for v in catalog.values()),code)
    def test_language_setting_does_not_reset_project_or_conversation(self):
        project=self.repo.get_setting("active_project"); conv=self.repo.conversation(project)
        self.repo.add_message(conv["id"],"user","teste unicode العربية हिन्दी")
        self.repo.set_setting("language","hi")
        self.assertEqual(self.repo.get_setting("language"),"hi")
        self.assertEqual(self.repo.get_setting("active_project"),project)
        self.assertIn("हिन्दी",self.repo.messages(conv["id"])[0]["content"])
    def test_scope_is_exact_host(self):
        manager=ScopeManager(); manager.validate("https://scan.example.test/path",["scan.example.test"])
        with self.assertRaises(PermissionError): manager.validate("https://child.example.test",["example.test"])
        with self.assertRaises(ValueError): normalize_target("javascript:alert(1)")
    def test_project_and_task_persistence(self):
        pid=self.repo.create_project("Projeto Unicode π")
        tid=self.repo.create_task(pid,"web","https://example.test")
        self.repo.finish_task(tid,"completed","ok")
        self.assertEqual(self.repo.tasks(pid)[0]["status"],"completed")
        self.assertEqual(os.stat(self.repo.path).st_mode & 0o777,0o600)
        self.assertEqual(os.stat(Path(self.repo.path).parent).st_mode & 0o777,0o700)

if __name__=="__main__": unittest.main()
