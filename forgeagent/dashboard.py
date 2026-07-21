"""A zero-dependency visual trust ledger for ForgeAgent demos."""

from __future__ import annotations

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from forgeagent.benchmark import run_safety_benchmark
from forgeagent.judge_mode import JudgeMode
from forgeagent.platform_store import PlatformStore
from forgeagent.registry import ToolRegistry


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


def pending_payload(registry_path: str | Path) -> dict[str, object]:
    """Read pending SQLite evidence for dashboard review; this never mutates state."""
    database = Path(registry_path).parent / "foundry.sqlite3"
    if not database.exists():
        return {"pending": []}
    store = PlatformStore(database)
    try:
        return {"pending": store.pending_evidence()}
    finally:
        store.close()

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

PENDING_CSS = """
.pending-review{display:grid;gap:12px}.pending-card{border:1px solid #604b29;border-radius:10px;background:#16150f;padding:15px}.pending-card h3{margin:0;color:#f6d18b;font-size:15px}.pending-meta{color:#b7a881;font-size:12px;margin:7px 0 12px}.pending-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.pending-block{border-left:2px solid #f0b86c;background:#101f2d;padding:10px;color:#aabccc;font-size:12px}.pending-block b{display:block;color:#f5f7fa;margin-bottom:6px}.pending-source{margin:10px 0 0;overflow:auto;max-height:260px;padding:12px;border-radius:8px;background:#071019;border:1px solid #263b4d;color:#d8e7f1;font:12px ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre}.proof-entry{border-left:2px solid #7ee4c3;padding:6px 8px;margin:5px 0;background:#0b1724}.proof-entry.failed{border-color:#e06f6f}@media(max-width:700px){.pending-grid{grid-template-columns:1fr}}
"""

LIVE_COUNCIL_SECTION = """
<section class="panel" style="margin-top:14px"><div class="live-head"><h2><span>05 /</span> Live Foundry Council</h2><div class="live-state" id="live-state">CONNECTING…</div></div><p class="empty">New council decisions are read directly from the append-only audit log while a Foundry run is in progress.</p><div class="council" id="council"><div class="empty">Waiting for Council evidence…</div></div></section>
"""

PENDING_SECTION = """
<section class="panel" style="margin-top:14px"><div class="live-head"><h2><span>06 /</span> Pending review</h2><div class="live-state offline">VIEW ONLY</div></div><p class="empty">Candidates held by governance are shown with their complete evidence package. Approval and rejection remain outside this dashboard.</p><div class="pending-review" id="pending-review"><div class="empty">Loading pending evidence…</div></div></section>
"""

LIVE_COUNCIL_SCRIPT = r'''<script>
(()=>{const roles=['planner','builder','security','evaluator','governor'];let cursor=0;let feed=[];const escape=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));const state=status=>/rejected|blocked|failed|denied/.test(status)?'blocked':/pending|repair/.test(status)?'pending':/skipped/.test(status)?'muted':'';function render(){const grouped=Object.fromEntries(roles.map(role=>[role,[]]));feed.filter(event=>String(event.event||'').startsWith('council_')).forEach(event=>{const role=String(event.event).slice('council_'.length);if(grouped[role])grouped[role].push(event)});const seen=roles.some(role=>grouped[role].length);council.innerHTML=seen?roles.map(role=>`<section class="council-role"><h3>${role.toUpperCase()}</h3>${grouped[role].slice(-8).map(event=>`<div class="council-event ${state(String(event.outcome||''))}"><b>${escape(event.outcome||'pending').toUpperCase()}</b>${escape(event.detail)}<br><small>${escape(event.created_at)}</small></div>`).join('')||'<div class="empty">No decision yet.</div>'}</section>`).join(''):'<div class="empty">Waiting for a Foundry run. Open a second terminal and run a new --foundry-task.</div>'}async function poll(){try{const response=await fetch(`/api/audit-log?since=${cursor}`,{cache:'no-store'});if(!response.ok)throw new Error('audit endpoint unavailable');const data=await response.json();cursor=Number(data.cursor||cursor);if(Array.isArray(data.events)&&data.events.length){feed.push(...data.events);render()}liveState.textContent='LIVE / POLLING 1.2s';liveState.className='live-state'}catch(error){liveState.textContent='RETRYING…';liveState.className='live-state offline'}}const liveState=document.getElementById('live-state');poll();setInterval(poll,1200)})();
</script>'''

PENDING_SCRIPT = r'''<script>
(()=>{const target=document.getElementById('pending-review');const escape=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));const proof=entry=>{const results=Array.isArray(entry.proof?.results)?entry.proof.results:[];return results.length?results.map(result=>`<div class="proof-entry ${result.passed?'':'failed'}"><b>${escape(result.category).toUpperCase()} / ${result.passed?'PASSED':'FAILED'}</b>${escape(result.detail||result.rationale||'')}</div>`).join(''):'<div class="empty">Proof evidence unavailable.</div>'};function render(items){target.innerHTML=items.length?items.map(entry=>{const surfaces=entry.threat_model?.detected_risk_surfaces||[];return `<article class="pending-card"><h3>${escape(entry.name)}@v${escape(entry.version)}</h3><div class="pending-meta">${escape(entry.project_id)} · trust score ${escape(entry.trust_score)} · ${escape(entry.provenance)}</div><div class="pending-grid"><div class="pending-block"><b>REQUESTED TASK</b>${escape(entry.requested_task||'Task evidence unavailable.')}</div><div class="pending-block"><b>THREAT MODEL</b>${surfaces.length?surfaces.map(escape).join(', '):'No detected risk surfaces.'}<br><small>${escape(entry.threat_model?.allowed_boundary||'Boundary evidence unavailable.')}</small></div><div class="pending-block"><b>PROOF RESULTS</b>${proof(entry)}</div><div class="pending-block"><b>GOVERNANCE STATE</b>PENDING — evidence retained; no action is available in this view.</div></div><pre class="pending-source"><code>${escape(entry.source)}</code></pre></article>`}).join(''):'<div class="empty">No capabilities are pending review. Run a Foundry task with <code>--approval-policy production</code> to create a reviewable evidence package.</div>'}async function load(){try{const response=await fetch('/api/pending',{cache:'no-store'});if(!response.ok)throw new Error('pending endpoint unavailable');const data=await response.json();render(Array.isArray(data.pending)?data.pending:[])}catch(error){target.innerHTML='<div class="empty">Pending evidence is temporarily unavailable.</div>'}}load();setInterval(load,1800)})();
</script>'''

# Keep the existing ledger intact and layer the live view into the local page.
PAGE = PAGE.replace("</style></head>", LIVE_COUNCIL_CSS + "</style></head>")
PAGE = PAGE.replace("</style></head>", PENDING_CSS + "</style></head>")
PAGE = PAGE.replace("</section></main>\n<script>", LIVE_COUNCIL_SECTION + "</main>\n<script>")
PAGE = PAGE.replace("</script></body></html>", "</script>" + LIVE_COUNCIL_SCRIPT + "</body></html>")
PAGE = PAGE.replace(LIVE_COUNCIL_SECTION, LIVE_COUNCIL_SECTION + PENDING_SECTION)
PAGE = PAGE.replace("</body></html>", PENDING_SCRIPT + "</body></html>")

JUDGE_PAGE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ForgeAgent — Judge Mode</title><style>
*{box-sizing:border-box}body{margin:0;background:#08111b;color:#e8f0f7;font:16px Inter,ui-sans-serif,system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:46px 24px 72px}.eyebrow{color:#7ee4c3;font-size:12px;font-weight:800;letter-spacing:.15em}.hero{display:flex;justify-content:space-between;gap:30px;border-bottom:1px solid #263b4d;padding-bottom:30px}.hero h1{font-family:Georgia,serif;font-size:56px;line-height:1;margin:10px 0 16px;letter-spacing:-.055em}.hero p{max-width:670px;color:#aabccc;line-height:1.6}.seal{align-self:center;border:1px solid #7ee4c3;border-radius:50%;padding:30px 18px;color:#7ee4c3;font-size:12px;font-weight:800;letter-spacing:.1em;text-align:center}.panel{background:#0d1926;border:1px solid #263b4d;border-radius:15px;padding:24px;margin-top:18px}.panel h2{font-size:18px;margin:0 0 8px}.note{color:#8da3b6;line-height:1.5;margin:0}.steps{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:20px}.step{background:#101f2d;border:1px solid #263b4d;border-radius:11px;min-height:134px;padding:15px;color:#9db1c3;font-size:13px}.step b{display:block;color:#e8f0f7;margin-bottom:9px}.step.active{border-color:#7ee4c3;color:#d7f2e8}.step.done{border-color:#3c8d75}.step.blocked{border-color:#e06f6f}.controls{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px}.button{border:1px solid #38566f;border-radius:9px;background:#102235;color:#e8f0f7;padding:11px 15px;font:inherit;font-weight:750;cursor:pointer}.button.primary{background:#7ee4c3;color:#082018;border-color:#7ee4c3}.button.warn{background:#3c201f;border-color:#e06f6f}.button:disabled{opacity:.38;cursor:not-allowed}.state{display:inline-block;margin-top:14px;padding:6px 10px;border-radius:999px;background:#12372f;color:#7ee4c3;font-size:12px;font-weight:800;letter-spacing:.08em}.evidence{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}.metric{background:#071019;border:1px solid #263b4d;border-radius:10px;padding:14px}.metric b{display:block;color:#fff;font-size:24px;margin-top:4px}.metric span{color:#8da3b6;font-size:12px}.output{white-space:pre-wrap;overflow:auto;max-height:420px;background:#071019;border:1px solid #263b4d;border-radius:10px;padding:16px;color:#d8e7f1;font:12px ui-monospace,SFMono-Regular,Menlo,monospace;line-height:1.5;margin:16px 0 0}.footer{color:#8da3b6;font-size:13px;line-height:1.5;margin-top:20px}@media(max-width:760px){.hero{display:block}.seal{display:none}.hero h1{font-size:45px}.steps{grid-template-columns:1fr}.evidence{grid-template-columns:1fr}}
</style></head><body><main><section class="hero"><div><div class="eyebrow">FORGEAGENT / REAL LOCAL JUDGE MODE</div><h1>Break trust.<br>Watch it respond.</h1><p>This is a real, deterministic backend run—not a prerecorded animation. Each click uses the Foundry, isolated sandbox, SQLite capability memory, governance transition, feedback regression, and MCP reuse path.</p></div><div class="seal">NO API KEY<br>NO FAKE<br>STATE</div></section><section class="panel"><h2>90-second judge story</h2><p class="note">Forge a capability, approve it, reuse it, report a reproduced failure, observe quarantine, then repair it against the retained regression evidence.</p><div class="steps" id="steps"></div><div id="state" class="state">LOADING</div><div class="controls"><button class="button" data-action="reset">Reset isolated scenario</button><button class="button primary" data-action="forge">1. Forge & prove</button><button class="button primary" data-action="approve">2. Approve</button><button class="button primary" data-action="reuse">3. Reuse from memory</button><button class="button warn" data-action="report-failure">4. Report failure</button><button class="button primary" data-action="repair">5. Repair & re-prove</button></div></section><section class="panel"><h2>Live evidence</h2><p class="note">Source, proof coverage, feedback regressions, and the most recent drift result are read from the dedicated Judge Mode SQLite database.</p><div class="evidence" id="evidence"></div><pre class="output" id="output">Loading isolated scenario…</pre></section><p class="footer">Reset removes only <code>data/judge_mode/</code>. It never changes normal project memory. For full test evidence, return to the <a href="/" style="color:#7ee4c3">Forge Ledger</a>.</p></main><script>
const steps=[['ready','Capability gap','A known task has no trusted team capability.'],['pending_review','Proof & review','Foundry proves the tool, then production governance holds it.'],['trusted','Trusted reuse','MCP replays evidence and runs the stored capability.'],['quarantined','Failure contained','A reproduced mismatch becomes regression evidence and removes trust.'],['repaired_trusted','Repair verified','A successor passes original and inherited feedback proofs.']];const labels={ready:'READY TO FORGE',pending_review:'PENDING HUMAN REVIEW',trusted:'TRUSTED',quarantined:'QUARANTINED',repaired_trusted:'REPAIRED + TRUSTED'};let current={};const byAction=Object.fromEntries([...document.querySelectorAll('[data-action]')].map(button=>[button.dataset.action,button]));function esc(value){return String(value??'')}function render(state){current=state;document.getElementById('state').textContent=labels[state.phase]||String(state.phase).toUpperCase();document.getElementById('steps').innerHTML=steps.map(([phase,title,body])=>{const index=steps.findIndex(item=>item[0]===phase),active=phase===state.phase,done=steps.findIndex(item=>item[0]===state.phase)>index;return `<article class="step ${active?'active':''} ${done?'done':''} ${phase==='quarantined'&&active?'blocked':''}"><b>${index+1}. ${title}</b>${body}</article>`}).join('');const allowed=new Set(state.available_actions||[]);Object.entries(byAction).forEach(([action,button])=>button.disabled=action!=='reset'&&!allowed.has(action));const evidence=state.evidence;if(!evidence){document.getElementById('evidence').innerHTML='<div class="metric"><span>No capability evidence yet</span><b>—</b></div>';return}const proof=evidence.proof||{},coverage=Array.isArray(proof.coverage)?proof.coverage.join(', '):'unavailable',drift=evidence.latest_drift?.state||'not run';document.getElementById('evidence').innerHTML=`<div class="metric"><span>Capability version</span><b>${esc(evidence.name)}@v${esc(evidence.version)}</b></div><div class="metric"><span>Trust / state</span><b>${esc(evidence.trust_score)} / ${esc(evidence.state)}</b></div><div class="metric"><span>Proof coverage</span><b>${esc(coverage)}</b></div><div class="metric"><span>Feedback regressions / drift</span><b>${esc(evidence.feedback_regression_count)} / ${esc(drift)}</b></div>`}async function refresh(){const response=await fetch('/api/judge/state',{cache:'no-store'});const state=await response.json();render(state);return state}async function action(name){const button=byAction[name];if(button)button.disabled=true;document.getElementById('output').textContent=`Running real Judge Mode action: ${name}…`;try{const response=await fetch(`/api/judge/${name}`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const data=await response.json();if(!response.ok)throw new Error(data.error||'action failed');document.getElementById('output').textContent=JSON.stringify(data,null,2);await refresh()}catch(error){document.getElementById('output').textContent=`ACTION BLOCKED: ${error.message}`;await refresh()}}Object.entries(byAction).forEach(([name,button])=>button.onclick=()=>action(name));refresh();
</script></body></html>'''


SHOWCASE_PAGE = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>ForgeAgent — Live capability story</title>
  <style>
    *{box-sizing:border-box} body{margin:0;background:#08111b;color:#e8f0f7;font:16px Inter,ui-sans-serif,system-ui,sans-serif}
    main{max-width:1100px;margin:auto;padding:54px 24px 74px}.eyebrow{color:#7ee4c3;font-size:12px;font-weight:800;letter-spacing:.15em}.hero{border-bottom:1px solid #263b4d;padding-bottom:34px}.hero h1{font-family:Georgia,serif;font-size:58px;line-height:1;margin:11px 0 17px;letter-spacing:-.055em}.hero p{max-width:720px;color:#aabccc;line-height:1.6}.request{margin-top:24px;display:grid;grid-template-columns:1fr 1fr;gap:14px}.request-card,.timeline{border:1px solid #263b4d;border-radius:14px;background:#0d1926}.request-card{padding:18px}.label{color:#7ee4c3;font-size:11px;font-weight:800;letter-spacing:.1em}.request-card h2{font-size:17px;margin:8px 0}.request-card p{color:#aabccc;line-height:1.5;margin:0}.code{font:13px ui-monospace,SFMono-Regular,Menlo,monospace;color:#d8e7f1;background:#071019;border:1px solid #263b4d;border-radius:8px;padding:12px;margin-top:13px}.action{margin-top:26px;border:0;border-radius:9px;background:#7ee4c3;color:#082018;padding:13px 18px;font:inherit;font-weight:800;cursor:pointer}.action:disabled{opacity:.55;cursor:wait}.notice{display:inline-block;margin-left:12px;color:#8da3b6;font-size:13px}.timeline{margin-top:22px;padding:22px}.timeline h2{font-size:18px;margin:0 0 14px}.event{display:grid;grid-template-columns:39px 1fr;gap:13px;padding:14px 0;border-top:1px solid #263b4d}.event:first-of-type{border-top:0}.event-number{height:28px;width:28px;display:grid;place-items:center;border-radius:50%;background:#163a35;color:#7ee4c3;font-size:12px;font-weight:800}.event h3{font-size:15px;margin:0 0 4px}.event p{color:#aabccc;font:13px ui-monospace,SFMono-Regular,Menlo,monospace;line-height:1.5;margin:0;white-space:pre-wrap}.event.pending .event-number{background:#443720;color:#f6d18b}.event.blocked .event-number{background:#40201f;color:#f1a4a1}.event.ready .event-number{background:#163a35;color:#7ee4c3}.footer{margin-top:20px;color:#8da3b6;font-size:13px}.footer a{color:#7ee4c3}@media(max-width:700px){main{padding:34px 18px}.hero h1{font-size:45px}.request{grid-template-columns:1fr}.notice{display:block;margin:10px 0 0}}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <div class="eyebrow">FORGEAGENT / LIVE CAPABILITY STORY</div>
    <h1>One agent builds it.<br>Every agent can trust it.</h1>
    <p>Run a real end-to-end ForgeAgent lifecycle: a coding agent requests a capability, governance holds it for review, another agent reuses it, a real regression removes trust, and a repaired version earns reuse again.</p>
    <button id="run" class="action">Run the live story</button><span id="notice" class="notice">Uses an isolated local SQLite database. No API key.</span>
  </section>
  <section class="request">
    <article class="request-card"><div class="label">FIRST REQUEST / CODING AGENT</div><h2>“Extract invoice IDs from billing logs.”</h2><div class="code">{ "text": "Invoices INV-2048 and INV-9 are awaiting review." }</div></article>
    <article class="request-card"><div class="label">LATER REQUEST / ANOTHER AGENT</div><h2>“Run the verified invoice extractor.”</h2><p>ForgeAgent must return a trusted capability from persistent memory, not generate fresh code. It replays retained contract evidence before reuse.</p></article>
  </section>
  <section class="timeline"><h2>What the system actually does</h2><div id="events"><div class="event"><div class="event-number">•</div><div><h3>Ready</h3><p>Click “Run the live story” to execute the real local Foundry flow.</p></div></div></div></section>
  <p class="footer">Want to inspect every individual action? Use <a href="/judge">Judge Mode</a>. This walkthrough resets only <code>data/judge_mode/</code>.</p>
</main>
<script>
const events=document.getElementById('events'),run=document.getElementById('run'),notice=document.getElementById('notice');
const story=[
  ['ready','A coding agent requests a new capability','The Foundry creates a constrained candidate and runs isolated normal, edge, contract, and adversarial proof cases.','forge'],
  ['pending','Production governance holds it','The proven candidate is intentionally pending until a named reviewer approves it.','approve'],
  ['ready','Cursor reuses trusted memory','A later coding agent gets the stored capability. ForgeAgent replays its retained contract before returning the real result.','reuse'],
  ['blocked','A reproduced defect revokes trust','The duplicate-ID output differs from the contract, so feedback becomes a regression case and the capability is quarantined.','report-failure'],
  ['ready','The repair must prove the old failure','A v2 candidate is accepted only after original proof plus the inherited feedback regression pass.','repair'],
  ['ready','Another agent reuses the repaired v2','The repaired capability is retrieved from memory and its contract is checked again before it executes.','reuse']
];
function evidenceSummary(action,data,fallback){if(!data)return fallback;if(action==='forge'){const proof=data.proof||{},coverage=Array.isArray(proof.coverage)?proof.coverage.join(', '):'unavailable';return `REAL RESULT: ${data.memory_record?.name||'candidate'}@v${data.memory_record?.version||'?'} is ${data.status}. Proof: ${proof.passed?'passed':'failed'}; coverage: ${coverage}; trust score: ${proof.trust_score??'unavailable'}.`};if(action==='approve')return `REAL RESULT: ${data.name}@v${data.version} is now ${data.state} after named human approval.`;if(action==='reuse'){const drift=data.drift_check?.status||'unavailable';return `REAL RESULT: ${data.memory_record?.name}@v${data.memory_record?.version||'?'} reused from ${data.memory_source||'memory'}; drift replay ${drift}; output ${JSON.stringify(data.result)}.`};if(action==='report-failure'){return `REAL RESULT: ${data.status}; actual output ${JSON.stringify(data.execution?.actual_output)}; trusted reuse quarantined: ${data.quarantined?'yes':'no'}.`};if(action==='repair')return `REAL RESULT: ${data.name}@v${data.version} promoted as ${data.state}. Its proof now includes the retained feedback regression.`;return fallback}
function add(kind,title,detail,data,index,action){const row=document.createElement('article');row.className=`event ${kind}`;row.innerHTML=`<div class="event-number">${index}</div><div><h3>${title}</h3><p></p></div>`;row.querySelector('p').textContent=evidenceSummary(action,data,detail);events.appendChild(row)}
async function post(action){const response=await fetch(`/api/judge/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const data=await response.json();if(!response.ok)throw new Error(data.error||'request failed');return data}
run.addEventListener('click',async()=>{run.disabled=true;events.innerHTML='';notice.textContent='Running the real local flow…';try{await post('reset');for(let i=0;i<story.length;i++){const [kind,title,detail,action]=story[i];const data=await post(action);add(kind,title,detail,data,i+1,action)}notice.textContent='Completed: v2 is trusted and reusable.'}catch(error){add('blocked','Story stopped safely',String(error),null,'!','');notice.textContent='A real policy or proof boundary stopped the scenario.'}finally{run.disabled=false}})
</script>
</body>
</html>'''


def create_server(
    registry_path: str | Path = "data/tool_registry.json",
    host: str = "127.0.0.1",
    port: int = 8787,
) -> ThreadingHTTPServer:
    """Build the local dashboard server for use by the CLI and endpoint tests."""
    path = Path(registry_path)
    judge = JudgeMode(path.parent / "judge_mode", repository_root=Path.cwd())

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            request = urlparse(self.path)
            if request.path == "/api/tools":
                body, content_type = json.dumps(tools_payload(path)).encode(), "application/json"
            elif request.path == "/api/pending":
                body, content_type = json.dumps(pending_payload(path)).encode(), "application/json"
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
            elif request.path == "/api/judge/state":
                body, content_type = json.dumps(judge.state()).encode(), "application/json"
            elif request.path == "/judge":
                body, content_type = JUDGE_PAGE.encode(), "text/html; charset=utf-8"
            elif request.path == "/showcase":
                body, content_type = SHOWCASE_PAGE.encode(), "text/html; charset=utf-8"
            elif request.path == "/favicon.ico":
                body, content_type = b"", "image/x-icon"
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

        def do_POST(self) -> None:  # noqa: N802
            request = urlparse(self.path)
            actions = {
                "/api/judge/reset": judge.reset,
                "/api/judge/forge": judge.forge,
                "/api/judge/approve": judge.approve,
                "/api/judge/reuse": judge.reuse,
                "/api/judge/report-failure": judge.report_failure,
                "/api/judge/repair": judge.repair,
            }
            action = actions.get(request.path)
            if action is None:
                self.send_error(404)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size > 16_384:
                    raise ValueError("Judge Mode accepts no large request body")
                if size:
                    self.rfile.read(size)
                body, status = json.dumps(action()).encode(), 200
            except ValueError as exc:
                body, status = json.dumps({"error": str(exc)}).encode(), 409
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def serve(registry_path: str | Path = "data/tool_registry.json", port: int = 8787) -> None:
    print(f"Forge Ledger running at http://127.0.0.1:{port}")
    print(f"Judge Mode running at http://127.0.0.1:{port}/judge")
    create_server(registry_path, port=port).serve_forever()
