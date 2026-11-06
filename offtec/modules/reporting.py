"""Localized HTML, JSON, and plain-text report exports."""
import html
import json
import os
from datetime import datetime, timezone

from offtec.core.config import REPORT_DIR

METHOD_KEYS = {
    "web": "report.method_web", "tls": "report.method_tls",
    "recon": "report.method_recon", "vulnerability": "report.method_vulnerability",
    "api": "report.method_api", "network": "report.method_network",
    "assets": "report.method_assets", "sqlmap": "report.method_sqlmap",
    "sql_review": "report.method_sql_review", "xss_review": "report.method_xss_review",
}


def generate(repo, project_id, project_name, tr):
    REPORT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    try: os.chmod(REPORT_DIR,0o700)
    except OSError: pass
    findings = repo.findings(project_id)
    tasks = repo.tasks(project_id)
    scopes = repo.scopes(project_id)
    generated_at = datetime.now(timezone.utc)
    stamp = generated_at.strftime("%Y%m%d-%H%M%S-%f")
    base = REPORT_DIR / (stamp + "-" + project_id[:8])
    methods, tools, report_tasks = set(), set(), []
    for task in tasks:
        module = task["module"]
        if module in METHOD_KEYS:
            methods.add(tr.t(METHOD_KEYS[module]))
        try:
            evidence = json.loads(task["result"] or "{}")
        except (json.JSONDecodeError, TypeError):
            evidence = {}
        if evidence.get("tool"):
            tools.add(str(evidence["tool"]))
        report_tasks.append({
            "id": task["id"], "module_id": module,
            "module": tr.t("menu." + {"vulnerability": "vuln", "sqlmap": "sql", "sql_review": "sql", "xss_review": "xss"}.get(module, module)),
            "target": task["target"], "status_code": task["status"],
            "status": tr.t("task." + {"queued": "queued", "running": "running", "completed": "completed", "failed": "failed", "cancelled": "cancelled"}.get(task["status"], "failed")),
            "created_at": task["created_at"], "progress": task["progress"],
        })
    methods, tools = sorted(methods), sorted(tools)
    stamp_iso = generated_at.isoformat()
    active_modules = {"api", "assets", "network", "sqlmap"}
    for task in tasks:
        if task["module"] == "vulnerability":
            try: has_nuclei = bool(json.loads(task["result"] or "{}").get("nuclei"))
            except (json.JSONDecodeError, TypeError): has_nuclei = False
            if has_nuclei: active_modules.add("vulnerability")
    has_active = any(task["module"] in active_modules for task in tasks)
    limitations = tr.t("report.active_note" if has_active else "report.passive_note")
    translated_findings = []
    for row in findings:
        item = dict(row)
        if item.get("title_key"):
            item["title"] = tr.t(item["title_key"])
        if item.get("details_key"):
            item["details"] = tr.t(item["details_key"])
        if item.get("recommendation_key"):
            item["recommendation"] = tr.t(item["recommendation_key"])
        item["severity_code"] = item["severity"]
        severity_key = "severity." + item["severity"]
        item["severity"] = tr.t(severity_key if severity_key in tr.catalogs[tr.lang] else "common.info")
        translated_findings.append(item)
    summary = tr.t("report.executive_summary", count=len(translated_findings))
    data = {
        "report_language": tr.lang, "project": project_name, "executive_summary": summary, "generated_at": stamp_iso,
        "authorized_scope": scopes, "methodology": methods, "tools_used": tools,
        "limitations": limitations, "findings": translated_findings, "tasks": report_tasks,
    }
    jsonpath = base.with_suffix(".json")
    jsonpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    direction = "rtl" if tr.lang == "ar" else "ltr"
    rows = []
    for f in translated_findings:
        rows.append("<tr><td>" + html.escape(f["severity"]) + "</td><td>" + html.escape(f["title"]) + "</td><td>" + html.escape(f["details"]) + "</td><td>" + html.escape(str(round(float(f["confidence"]) * 100)) + "%") + "</td><td>" + html.escape(f["recommendation"] or tr.t("common.none")) + "</td><td><code>" + html.escape(f["evidence"]) + "</code></td></tr>")
    h = lambda key: html.escape(tr.t(key))
    scope_text = ", ".join(scopes) if scopes else tr.t("common.none")
    methods_text = "<ul>" + "".join("<li>" + html.escape(x) + "</li>" for x in methods) + "</ul>" if methods else "<p>" + h("common.none") + "</p>"
    page = ("<!doctype html><html lang='" + html.escape(tr.lang) + "' dir='" + direction + "'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>OFFTEC AI HUNTER</title>"
        "<style>body{background:#101010;color:#eee;font:16px sans-serif;margin:2rem}h1,h2{color:#dc143c}table{border-collapse:collapse;width:100%;font-size:.9rem}td,th{padding:.65rem;border:1px solid #555;text-align:start;vertical-align:top}th{color:#ff526b}code{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>OFFTEC AI HUNTER</h1>"
        "<h2>" + h("report.summary") + "</h2><p>" + html.escape(summary) + "</p><p>" + html.escape(project_name) + " · " + html.escape(stamp_iso) + "</p><p>" + h("report.scope") + ": " + html.escape(scope_text) + "</p>"
        "<h2>" + h("common.findings") + "</h2><table><tr><th>" + h("common.severity") + "</th><th>" + h("common.result") + "</th><th>" + h("common.evidence") + "</th><th>" + h("report.confidence") + "</th><th>" + h("report.recommendations") + "</th><th>" + h("common.info") + "</th></tr>" + ("".join(rows) or "<tr><td colspan='6'>" + h("report.no_findings") + "</td></tr>") + "</table>"
        "<h2>" + h("report.method") + "</h2>" + methods_text + "<h2>" + h("report.tools") + "</h2><p>" + html.escape(", ".join(tools) if tools else tr.t("common.none")) + "</p>"
        "<h2>" + h("report.limitations") + "</h2><p>" + html.escape(limitations) + "</p><p>" + h("report.generated") + "</p></html>")
    htmlpath = base.with_suffix(".html")
    htmlpath.write_text(page, encoding="utf-8")
    txt = ("OFFTEC AI HUNTER\n" + tr.t("report.summary") + ": " + summary + "\n" + project_name + "\n" + tr.t("report.scope") + ": " + scope_text + "\n" + tr.t("common.date") + ": " + stamp_iso + "\n\n" + tr.t("common.findings") + "\n" +
        ("\n".join("[" + f["severity"] + "] " + f["title"] + " — " + f["details"] + "\n" + tr.t("report.confidence") + ": " + str(round(float(f["confidence"]) * 100)) + "%\n" + tr.t("report.recommendations") + ": " + (f["recommendation"] or tr.t("common.none")) + "\n" + tr.t("common.evidence") + ": " + f["evidence"] for f in translated_findings) or tr.t("report.no_findings")) + "\n\n" + tr.t("report.method") + ": " + ("; ".join(methods) or tr.t("common.none")) + "\n" + tr.t("report.tools") + ": " + (", ".join(tools) or tr.t("common.none")) + "\n" + tr.t("report.limitations") + ": " + limitations)
    txtpath = base.with_suffix(".txt")
    txtpath.write_text(txt, encoding="utf-8")
    for fmt, path in (("html", htmlpath), ("json", jsonpath), ("txt", txtpath)):
        try: os.chmod(path,0o600)
        except OSError: pass
        repo.record_report(project_id, None, path, fmt, tr.lang)
    return base
