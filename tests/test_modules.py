import threading
import unittest
from unittest.mock import patch, MagicMock

from offtec.modules import native_analysis as native
from offtec.modules import web_analysis


class Response:
    status = 200
    headers = {"Content-Type": "application/json", "Server": "local-test"}
    def __enter__(self): return self
    def __exit__(self, *_): return False


class FakeOpener:
    def __init__(self, handler=None): self.handler = handler
    def open(self, request, timeout=0):
        if self.handler: return self.handler(request, timeout)
        return Response()


class ModuleTests(unittest.TestCase):
    def test_web_analysis_http_headers_and_bounded_timeout(self):
        with patch.object(web_analysis.urllib.request, "build_opener", return_value=FakeOpener()):
            evidence, findings = web_analysis.analyze("http://127.0.0.1/")
        self.assertEqual(evidence["http_status"], 200)
        self.assertEqual(evidence["tls"], "not_applicable_http")
        self.assertGreaterEqual(len(findings), 1)
        self.assertTrue(all(f["title_key"].startswith("finding.") for f in findings))

    def test_api_and_asset_checks_are_fixed_and_rate_limited(self):
        calls=[]
        def response(req, timeout):
            calls.append(req.full_url)
            if req.headers.get("Origin"):
                r=Response(); r.headers={"Access-Control-Allow-Origin":"https://offtec.invalid","Access-Control-Allow-Credentials":"true"}; return r
            if req.full_url.endswith("openapi.json"): return Response()
            raise __import__("urllib.error",fromlist=["HTTPError"]).HTTPError(req.full_url,404,"Not found",{},None)
        with patch.object(native, "OPENER", FakeOpener(response)), patch.object(native.time, "sleep"):
            evidence, findings=native.api_check("http://127.0.0.1")
            self.assertEqual(len(calls),4)
            self.assertTrue(any(f.get("title_key")=="finding.cors_reflect" for f in findings))
            calls.clear()
            assets,_=native.asset_discovery("http://127.0.0.1")
            self.assertEqual(len(calls),4)
            self.assertEqual(len(assets["resources"]),4)

    def test_network_fallback_is_bounded_and_cancellable(self):
        calls=[]
        class FakeSocket:
            def __enter__(self): return self
            def __exit__(self,*_): return False
        def connect(address,timeout):
            calls.append((address,timeout)); raise ConnectionRefusedError()
        with patch.object(native,"inventory",return_value={"nmap":None}), patch.object(native.socket,"create_connection",side_effect=connect), patch.object(native.time,"sleep"):
            evidence,_=native.network("http://127.0.0.1")
        self.assertEqual(len(calls),10)
        self.assertIn("top 10",evidence["method"])
        token=threading.Event(); token.set()
        with patch.object(native,"inventory",return_value={"nmap":None}), patch.object(native.socket,"create_connection",side_effect=connect):
            with self.assertRaises(InterruptedError): native.network("http://127.0.0.1",cancel=token)

    def test_optional_tool_profiles_and_vulnerability_fallback(self):
        with patch.object(native,"web_analyze",return_value=({"headers":{}},[])), patch.object(native,"inventory",return_value={"nuclei":None}):
            evidence, findings=native.vulnerability("https://authorized.test")
        self.assertFalse(findings)
        self.assertIn("CVE",evidence["optional_tool"])
        with patch.object(native,"inventory",return_value={"sqlmap":None}):
            with self.assertRaises(FileNotFoundError): native.sqlmap_scan("https://authorized.test/item?id=1")
        with patch.object(native,"inventory",return_value={"nmap":"/usr/bin/nmap"}), patch.object(native,"run_tool",return_value={"returncode":0,"output":"<nmaprun><host><ports><port protocol=\"tcp\" portid=\"443\"><state state=\"open\"/></port></ports></host></nmaprun>","elapsed":.1}) as run:
            evidence,_=native.network("https://authorized.test")
        self.assertEqual(evidence["ports"][0]["port"],443)
        args=run.call_args.args[0]
        self.assertIn("-sT",args); self.assertIn("--top-ports",args)


if __name__ == "__main__": unittest.main()
