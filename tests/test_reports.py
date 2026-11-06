import json, tempfile, unittest
from pathlib import Path
from offtec.database.repository import Repository
from offtec.core.i18n import Translator, LANGUAGES
from offtec.modules.reporting import generate

class ReportTests(unittest.TestCase):
    def test_localized_html_json_txt(self):
        import offtec.modules.reporting as reporting
        with tempfile.TemporaryDirectory() as d:
            old=reporting.REPORT_DIR; reporting.REPORT_DIR=Path(d)
            try:
                repo=Repository(Path(d)/"db.sqlite3"); pid=repo.get_setting("active_project")
                tid=repo.create_task(pid,"web","https://example.test"); repo.finish_task(tid,"completed","{}")
                repo.add_finding(pid,tid,"low","Cabeçalho ausente","Detalhe","{}",title_key="finding.csp",details_key="finding.header_detail")
                for lang in LANGUAGES:
                    tr=Translator(lang); base=generate(repo,pid,"Proyecto",tr)
                    self.assertTrue(base.with_suffix(".html").exists()); self.assertTrue(base.with_suffix(".json").exists()); self.assertTrue(base.with_suffix(".txt").exists())
                    page=base.with_suffix(".html").read_text(encoding="utf-8")
                    self.assertIn(tr.t("report.summary"),page)
                    self.assertIn(tr.t("finding.csp"),page)
                    if lang=="ar": self.assertIn("dir='rtl'",page)
                    data=json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
                    self.assertEqual(data["findings"][0]["severity"],tr.t("severity.low"))
                    self.assertIn(tr.t("report.executive_summary",count=1),data["executive_summary"])
                    self.assertEqual(base.with_suffix(".json").stat().st_mode & 0o777,0o600)
            finally: reporting.REPORT_DIR=old

if __name__=="__main__": unittest.main()
