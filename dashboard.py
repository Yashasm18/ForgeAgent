"""A zero-dependency visual trust ledger for ForgeAgent demos."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PAGE = r'''<!doctype html><html><head><meta charset="utf-8"><title>ForgeAgent — Trust Ledger</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{box-sizing:border-box}body{margin:0;background:#08111b;color:#e8f0f7;font:15px Inter,ui-sans-serif,system-ui,sans-serif}main{max-width:1120px;margin:auto;padding:38px 24px 70px}.eyebrow{color:#7ee4c3;font-weight:800;letter-spacing:.16em;font-size:11px}.hero{display:flex;justify-content:space-between;gap:20px;align-items:end;border-bottom:1px solid #243546;padding-bottom:28px}.hero h1{font-family:Georgia,serif;font-size:55px;margin:7px 0;letter-spacing:-.06em}.hero p{color:#9db1c3;max-width:560px;line-height:1.55}.seal{width:134px;height:134px;border:1px solid #7ee4c3;border-radius:50%;display:grid;place-items:center;text-align:center;color:#7ee4c3;font-weight:800;letter-spacing:.08em;font-size:12px;box-shadow:0 0 55px #1f856844}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:27px 0}.metric,.panel{background:#0d1926;border:1px solid #243546;border-radius:14px}.metric{padding:18px}.metric b{font-size:32px;display:block;color:#fff}.metric span{color:#8da3b6;font-size:12px}.panel{padding:21px}.panel h2{font-size:15px;margin:0 0 15px}.panel h2 span{color:#7ee4c3}.flow{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.step{background:#122234;border-radius:9px;padding:13px 10px;min-height:92px;color:#9db1c3;font-size:12px}.step b{display:block;color:#fff;margin-bottom:8px}.step.ok{border:1px solid #338b70}.tools{display:grid;gap:10px}.tool{padding:15px;border:1px solid #263b4d;border-radius:10px;background:#0b1724;display:flex;justify-content:space-between;gap:16px}.tool code{color:#e8f0f7;font-weight:700}.tool p{color:#8da3b6;margin:6px 0 0}.badge{height:max-content;padding:5px 9px;border-radius:100px;background:#12372f;color:#7ee4c3;font-size:11px;font-weight:800}.empty{color:#8da3b6;padding:16px 0}@media(max-width:700px){.hero{align-items:start;flex-direction:column}.hero h1{font-size:42px}.grid{grid-template-columns:1fr}.flow{grid-template-columns:1fr 1fr}.seal{display:none}}</style></head>
<body><main><section class="hero"><div><div class="eyebrow">FORGEAGENT / VERIFIED SKILL MEMORY</div><h1>Trust is forged,<br>not assumed.</h1><p>GPT‑5.6 may propose a capability. Only isolated execution and reproducible evidence allow it to become an agent's permanent memory.</p></div><div class="seal">VERIFIED<br>BEFORE<br>REUSE</div></section>
<section class="grid"><div class="metric"><b id="count">—</b><span>trusted skills in memory</span></div><div class="metric"><b id="reuses">—</b><span>verified reuses</span></div><div class="metric"><b id="tests">—</b><span>recorded proof cases</span></div></section>
<section class="panel"><h2><span>01 /</span> The forge protocol</h2><div class="flow"><div class="step"><b>Capability gap</b>Agent names what it cannot yet do.</div><div class="step"><b>GPT‑5.6 proposal</b>Code and edge-case tests are proposed.</div><div class="step"><b>Policy gate</b>Dangerous imports and operations are blocked.</div><div class="step ok"><b>Isolated proof</b>Every test must pass in a fresh process.</div><div class="step ok"><b>Reusable memory</b>Evidence-backed skills compound over time.</div></div></section>
<section class="panel" style="margin-top:14px"><h2><span>02 /</span> Trust ledger</h2><div class="tools" id="tools"><div class="empty">Loading verified memory…</div></div></section><section class="panel" style="margin-top:14px"><h2><span>03 /</span> Evidence trail</h2><div class="tools" id="events"><div class="empty">Loading decisions…</div></div></section></main>
<script>async function load(){let [r,e]=await Promise.all([fetch('/api/tools'),fetch('/api/events')]),d=await r.json(),a=await e.json(),t=d.tools||[];count.textContent=t.length;reuses.textContent=t.reduce((a,x)=>a+(x.reuse_count||0),0);tests.textContent=t.reduce((a,x)=>a+(x.tests||[]).length,0);tools.innerHTML=t.length?t.map(x=>`<article class="tool"><div><code>${x.name}</code><p>${x.description}</p><p>Provenance: ${x.provenance||'legacy demo'} · ${x.tests?.length||1} proof case(s)</p></div><span class="badge">TRUSTED</span></article>`).join(''):'<div class="empty">No tools have earned trust yet. Forge your first capability.</div>';events.innerHTML=(a.events||[]).map(x=>`<article class="tool"><div><code>${x.event}</code><p>${x.capability} — ${x.detail}</p><p>${x.created_at}</p></div><span class="badge">${x.outcome.toUpperCase()}</span></article>`).join('')||'<div class="empty">No decisions recorded yet.</div>'}load();setInterval(load,3500);</script></body></html>'''


def serve(registry_path: str | Path = "data/tool_registry.json", port: int = 8787) -> None:
    path = Path(registry_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/api/tools":
                try:
                    tools = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
                except json.JSONDecodeError:
                    tools = []
                body, content_type = json.dumps({"tools": tools}).encode(), "application/json"
            elif self.path == "/api/events":
                audit_path = path.parent / "audit_log.jsonl"
                try:
                    rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                except (FileNotFoundError, json.JSONDecodeError):
                    rows = []
                body, content_type = json.dumps({"events": list(reversed(rows[-12:]))}).encode(), "application/json"
            elif self.path == "/":
                body, content_type = PAGE.encode(), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            return

    print(f"Forge Ledger running at http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
