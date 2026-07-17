"""A zero-dependency visual trust ledger for ForgeAgent demos."""

from __future__ import annotations

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from benchmark import run_safety_benchmark
from registry import ToolRegistry


def audit_updates(audit_path: str | Path, since: int = 0) -> dict[str, object]:
    """Return valid audit entries after a stable, count-based cursor.

    The writer appends one JSON line at a time. A reader can briefly observe an
    incomplete final line, so it is ignored until it becomes valid rather than
    advancing the cursor and losing that event.
    """
    try:
        requested_cursor = max(0, int(since))
    except (TypeError, ValueError):
        requested_cursor = 0
    try:
        lines = Path(audit_path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    entries: list[dict[str, object]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    cursor = min(requested_cursor, len(entries))
    return {"events": entries[cursor:], "cursor": len(entries)}


def tools_payload(registry_path: str | Path) -> dict[str, object]:
    """Expose persisted proof evidence without fabricating legacy counts."""
    try:
        tools = [asdict(tool) for tool in ToolRegistry(registry_path).list()]
    except RuntimeError:
        tools = []
    counts = [tool.get("proof_case_count") for tool in tools]
    evidence_available = all(isinstance(count, int) and not isinstance(count, bool) and count >= 0 for count in counts)
    return {
        "tools": tools,
        "proof_summary": {
            "evidence_available": evidence_available,
            "total_case_count": sum(counts) if evidence_available else None,
        },
    }

PAGE = r'''<!doctype html><html><head><meta charset="utf-8"><title>ForgeAgent — Trust Ledger</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{box-sizing:border-box}body{margin:0;background:#08111b;color:#e8f0f7;font:15px Inter,ui-sans-serif,system-ui,sans-serif}main{max-width:1120px;margin:auto;padding:38px 24px 70px}.eyebrow{color:#7ee4c3;font-weight:800;letter-spacing:.16em;font-size:11px}.hero{display:flex;justify-content:space-between;gap:20px;align-items:end;border-bottom:1px solid #243546;padding-bottom:28px}.hero h1{font-family:Georgia,serif;font-size:55px;margin:7px 0;letter-spacing:-.06em}.hero p{color:#9db1c3;max-width:560px;line-height:1.55}.seal{width:134px;height:134px;border:1px solid #7ee4c3;border-radius:50%;display:grid;place-items:center;text-align:center;color:#7ee4c3;font-weight:800;letter-spacing:.08em;font-size:12px;box-shadow:0 0 55px #1f856844}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:27px 0}.metric,.panel{background:#0d1926;border:1px solid #243546;border-radius:14px}.metric{padding:18px}.metric b{font-size:32px;display:block;color:#fff}.metric span{color:#8da3b6;font-size:12px}.panel{padding:21px}.panel h2{font-size:15px;margin:0 0 15px}.panel h2 span{color:#7ee4c3}.flow{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.step{background:#122234;border-radius:9px;padding:13px 10px;min-height:92px;color:#9db1c3;font-size:12px}.step b{display:block;color:#fff;margin-bottom:8px}.step.ok{border:1px solid #338b70}.tools{display:grid;gap:10px}.tool{padding:15px;border:1px solid #263b4d;border-radius:10px;background:#0b1724;display:flex;justify-content:space-between;gap:16px}.tool code{color:#e8f0f7;font-weight:700}.tool p{color:#8da3b6;margin:6px 0 0}.badge{height:max-content;padding:5px 9px;border-radius:100px;background:#12372f;color:#7ee4c3;font-size:11px;font-weight:800}.graph{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.edge{border-left:2px solid #7ee4c3;background:#0b1724;padding:10px;color:#9db1c3;font-size:12px}.edge b{display:block;color:#fff}.empty{color:#8da3b6;padding:16px 0}@media(max-width:700px){.hero{align-items:start;flex-direction:column}.hero h1{font-size:42px}.grid,.graph{grid-template-columns:1fr}.flow{grid-template-columns:1fr 1fr}.seal{display:none}}</style></head>
<body><main><section class="hero"><div><div class="eyebrow">FORGEAGENT / VERIFIED SKILL MEMORY</div><h1>Trust is forged,<br>not assumed.</h1><p>GPT‑5.6 may propose a capability. Only isolated execution and reproducible evidence allow it to become an agent's permanent memory.</p></div><div class="seal">VERIFIED<br>BEFORE<br>REUSE</div></section>
<section class="grid"><div class="metric"><b id="count">—</b><span>trusted skills in memory</span></div><div class="metric"><b id="reuses">—</b><span>verified reuses</span></div><div class="metric"><b id="tests">—</b><span>recorded proof cases</span></div><div class="metric"><b id="safety">—</b><span>trust-gate benchmark</span></div></section>
<section class="panel"><h2><span>01 /</span> The forge protocol</h2><div class="flow"><div class="step"><b>Capability gap</b>Agent names what it cannot yet do.</div><div class="step"><b>GPT‑5.6 proposal</b>Code and edge-case tests are proposed.</div><div class="step"><b>Policy gate</b>Dangerous imports and operations are blocked.</div><div class="step ok"><b>Isolated proof</b>Every test must pass in a fresh process.</div><div class="step ok"><b>Reusable memory</b>Evidence-backed skills compound over time.</div></div></section>
<section class="panel" style="margin-top:14px"><h2><span>02 /</span> Capability graph</h2><div class="graph" id="graph"><div class="empty">Loading task-to-skill lineage…</div></div></section><section class="panel" style="margin-top:14px"><h2><span>03 /</span> Trust ledger</h2><div class="tools" id="tools"><div class="empty">Loading verified memory…</div></div></section><section class="panel" style="margin-top:14px"><h2><span>04 /</span> Evidence trail</h2><div class="tools" id="events"><div class="empty">Loading decisions…</div></div></section></main>
<script>async function load(){let [r,e,b,g]=await Promise.all([fetch('/api/tools'),fetch('/api/events'),fetch('/api/benchmark'),fetch('/api/graph')]),d=await r.json(),a=await e.json(),q=await b.json(),k=await g.json(),t=d.tools||[];count.textContent=t.length;reuses.textContent=t.reduce((a,x)=>a+(x.reuse_count||0),0);tests.textContent=t.reduce((a,x)=>a+(x.tests||[]).length,0);safety.textContent=`${q.passed}/${q.total}`;tools.innerHTML=t.length?t.map(x=>`<article class="tool"><div><code>${x.name}@v${x.version||1}</code><p>${x.description}</p><p>${x.state||'active'} · ${x.tests?.length||1} proof case(s)</p></div><span class="badge">TRUSTED</span></article>`).join(''):'<div class="empty">No tools have earned trust yet. Forge your first capability.</div>';graph.innerHTML=(k.edges||[]).map(x=>`<div class="edge"><b>${x.relation}</b>${x.source.replace('skill:','').replace('task:','task ') } → ${x.target.replace('skill:','')}</div>`).join('')||'<div class="empty">Run the autonomy demo to forge a graph.</div>';events.innerHTML=(a.events||[]).map(x=>`<article class="tool"><div><code>${x.event}</code><p>${x.capability} — ${x.detail}</p><p>${x.created_at}</p></div><span class="badge">${x.outcome.toUpperCase()}</span></article>`).join('')||'<div class="empty">No decisions recorded yet.</div>'}load();setInterval(load,3500);</script></body></html>'''


# The aggregate comes from the same persisted metadata exposed in /api/tools;
# legacy records remain visibly unavailable rather than receiving a fake "1".
PAGE = PAGE.replace(
    "t=d.tools||[];count.textContent=t.length;reuses.textContent=t.reduce((a,x)=>a+(x.reuse_count||0),0);tests.textContent=t.reduce((a,x)=>a+(x.tests||[]).length,0);safety.textContent=`${q.passed}/${q.total}`;",
    "t=d.tools||[],p=d.proof_summary||{evidence_available:false,total_case_count:null};count.textContent=t.length;reuses.textContent=t.reduce((a,x)=>a+(x.reuse_count||0),0);tests.textContent=p.evidence_available?p.total_case_count:'—';tests.nextElementSibling.textContent=p.evidence_available?'recorded proof cases':'proof evidence unavailable';safety.textContent=`${q.passed}/${q.total}`;",
)
PAGE = PAGE.replace(
    "${x.state||'active'} · ${x.tests?.length||1} proof case(s)",
    "${x.state||'active'} · ${Number.isInteger(x.proof_case_count)?`${x.proof_case_count} proof case(s)`:'proof evidence unavailable'}",
)

LIVE_COUNCIL_CSS = """
.live-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.live-state{color:#7ee4c3;font-size:11px;font-weight:800;letter-spacing:.08em}.live-state.offline{color:#f0b86c}.council{display:grid;grid-template-columns:repeat(5,1fr);gap:9px}.council-role{background:#0b1724;border:1px solid #263b4d;border-radius:10px;min-height:126px;padding:11px}.council-role h3{margin:0 0 9px;color:#fff;font-size:12px}.council-event{border-left:2px solid #7ee4c3;padding:7px 8px;margin:6px 0;background:#101f2d;font-size:11px;color:#aabccc}.council-event b{display:block;color:#e8f0f7}.council-event.blocked{border-color:#e06f6f}.council-event.pending{border-color:#f0b86c}.council-event.muted{border-color:#587083}@media(max-width:700px){.council{grid-template-columns:1fr}}
"""

LIVE_COUNCIL_SECTION = """
<section class="panel" style="margin-top:14px"><div class="live-head"><h2><span>05 /</span> Live Foundry Council</h2><div class="live-state" id="live-state">CONNECTING…</div></div><p class="empty">New council decisions are read directly from the append-only audit log while a Foundry run is in progress.</p><div class="council" id="council"><div class="empty">Waiting for Council evidence…</div></div></section>
"""

LIVE_COUNCIL_SCRIPT = r'''<script>
(()=>{const roles=['planner','builder','security','evaluator','governor'];let cursor=0;let feed=[];const escape=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));const state=status=>/rejected|blocked|failed|denied/.test(status)?'blocked':/pending|repair/.test(status)?'pending':/skipped/.test(status)?'muted':'';function render(){const grouped=Object.fromEntries(roles.map(role=>[role,[]]));feed.filter(event=>String(event.event||'').startsWith('council_')).forEach(event=>{const role=String(event.event).slice('council_'.length);if(grouped[role])grouped[role].push(event)});const seen=roles.some(role=>grouped[role].length);council.innerHTML=seen?roles.map(role=>`<section class="council-role"><h3>${role.toUpperCase()}</h3>${grouped[role].slice(-8).map(event=>`<div class="council-event ${state(String(event.outcome||''))}"><b>${escape(event.outcome||'pending').toUpperCase()}</b>${escape(event.detail)}<br><small>${escape(event.created_at)}</small></div>`).join('')||'<div class="empty">No decision yet.</div>'}</section>`).join(''):'<div class="empty">Waiting for a Foundry run. Open a second terminal and run a new --foundry-task.</div>'}async function poll(){try{const response=await fetch(`/api/audit-log?since=${cursor}`,{cache:'no-store'});if(!response.ok)throw new Error('audit endpoint unavailable');const data=await response.json();cursor=Number(data.cursor||cursor);if(Array.isArray(data.events)&&data.events.length){feed.push(...data.events);render()}liveState.textContent='LIVE / POLLING 1.2s';liveState.className='live-state'}catch(error){liveState.textContent='RETRYING…';liveState.className='live-state offline'}}const liveState=document.getElementById('live-state');poll();setInterval(poll,1200)})();
</script>'''

# Keep the existing ledger intact and layer the live view into the local page.
PAGE = PAGE.replace("</style></head>", LIVE_COUNCIL_CSS + "</style></head>")
PAGE = PAGE.replace("</section></main>\n<script>", LIVE_COUNCIL_SECTION + "</main>\n<script>")
PAGE = PAGE.replace("</script></body></html>", "</script>" + LIVE_COUNCIL_SCRIPT + "</body></html>")


def create_server(
    registry_path: str | Path = "data/tool_registry.json",
    host: str = "127.0.0.1",
    port: int = 8787,
) -> ThreadingHTTPServer:
    """Build the local dashboard server for use by the CLI and endpoint tests."""
    path = Path(registry_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            request = urlparse(self.path)
            if request.path == "/api/tools":
                body, content_type = json.dumps(tools_payload(path)).encode(), "application/json"
            elif request.path == "/api/events":
                audit_path = path.parent / "audit_log.jsonl"
                try:
                    rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                except (FileNotFoundError, json.JSONDecodeError):
                    rows = []
                body, content_type = json.dumps({"events": list(reversed(rows[-12:]))}).encode(), "application/json"
            elif request.path == "/api/audit-log":
                raw_since = parse_qs(request.query).get("since", ["0"])[0]
                body, content_type = json.dumps(audit_updates(path.parent / "audit_log.jsonl", raw_since)).encode(), "application/json"
            elif request.path == "/api/benchmark":
                body, content_type = json.dumps(run_safety_benchmark()).encode(), "application/json"
            elif request.path == "/api/graph":
                graph_path = path.parent / "capability_graph.json"
                try:
                    graph = json.loads(graph_path.read_text(encoding="utf-8"))
                except (FileNotFoundError, json.JSONDecodeError):
                    graph = {"nodes": [], "edges": []}
                body, content_type = json.dumps(graph).encode(), "application/json"
            elif request.path == "/":
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

    return ThreadingHTTPServer((host, port), Handler)


def serve(registry_path: str | Path = "data/tool_registry.json", port: int = 8787) -> None:
    print(f"Forge Ledger running at http://127.0.0.1:{port}")
    create_server(registry_path, port=port).serve_forever()
