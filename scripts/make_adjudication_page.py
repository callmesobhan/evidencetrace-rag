"""Build a self-contained HTML page for a human to adjudicate the system-vs-annotator disagreements.

    python scripts/make_adjudication_page.py --out docs/adjudication.html          # needs the papers (make fetch-pinned)

Every item shows the sentence in context (from the paper's own text) and asks one question: is this a genuine effect
estimate of the kind the annotation guidelines define? The page runs offline, keeps progress in the browser, and exports
the decisions as JSONL; ``scripts/apply_adjudication.py`` turns that file into corrected accuracy figures.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evidencetrace.evaluation.adjudication import item_id
from evidencetrace.ingest.parsers import parse_file
from evidencetrace.ingest.sentences import split_sentences

ROOT = Path(__file__).resolve().parent.parent
M1 = ROOT / "data" / "m1"
DEFAULT_SOURCES = [M1 / "independent" / "scores_prefix_strict" / "disagreements.jsonl"]


def _context(doc, needle: str) -> tuple[str, str, str]:
    """(section, text before, text after) around the sentence containing ``needle`` (whitespace-insensitive)."""
    sents = split_sentences(doc)
    flat = " ".join(needle.split())
    for i, s in enumerate(sents):
        if flat[:60] in " ".join(s.text.split()):
            before = " ".join(x.text for x in sents[max(0, i - 2) : i])
            after = " ".join(x.text for x in sents[i + 1 : i + 3])
            return s.section or "", before, after
    return "", "", ""


def build_items(sources: list[Path], raw_dirs: list[Path]) -> list[dict]:
    docs: dict[str, object] = {}
    items = []
    for src in sources:
        for ln in src.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            if r["pmcid"] not in docs:
                path = next((d / f"{r['pmcid']}.xml" for d in raw_dirs if (d / f"{r['pmcid']}.xml").exists()), None)
                docs[r["pmcid"]] = parse_file(path) if path else None
            doc = docs[r["pmcid"]]
            sec, before, after = _context(doc, r.get("sentence") or "") if doc and r.get("sentence") else ("", "", "")
            items.append({"id": item_id(r), "kind": "estimate", "type": r["type"], "pmcid": r["pmcid"], "metric": r["metric"],
                          "value": r["value"], "ci": r.get("ci"), "attribution": r.get("attribution"), "sentence": r.get("sentence") or "",
                          "section": sec, "before": before, "after": after, "source": src.parent.name})
    return items


def design_items() -> list[dict]:
    man = {json.loads(ln)["pmcid"]: json.loads(ln) for f in ("corpus_manifest.jsonl", "fresh_manifest.jsonl")
           for ln in (M1 / f).read_text(encoding="utf-8").splitlines() if ln.strip()}
    out = []
    for ln in (M1 / "design.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(ln)
        if r["disagree"]:
            out.append({"id": "design-" + r["pmcid"], "kind": "design", "pmcid": r["pmcid"], "title": man[r["pmcid"]]["title"],
                        "pubmed_types": r["pubmed_types"], "classified_as": r["design"], "basis": r["basis"]})
    return out


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Adjudication - EvidenceTrace-RAG</title>
<style>
:root{--bg:#fafaf7;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#e2e1da;--acc:#2f5d50;--yes:#2e7d4f;--no:#b3422f;--unk:#8a6d1d;--mark:#fff1a8}
@media (prefers-color-scheme:dark){:root{--bg:#161715;--fg:#ecebe5;--mut:#a09f97;--card:#1f201d;--line:#34352f;--acc:#7fc4ae;--yes:#6fcf97;--no:#ef8a76;--unk:#e0c06b;--mark:#5a4d12}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;z-index:2}
h1{font-size:1.05rem;margin:0 0 4px}.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden}.bar i{display:block;height:100%;background:var(--acc);width:0}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:8px;font-size:.9rem;color:var(--mut)}
main{max-width:860px;margin:0 auto;padding:16px}.intro{color:var(--mut);font-size:.92rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0}
.card.done{border-left:5px solid var(--acc)}.meta{display:flex;gap:8px;flex-wrap:wrap;font-size:.82rem;color:var(--mut);margin-bottom:6px}
.tag{border:1px solid var(--line);border-radius:999px;padding:1px 9px}.tag.sys{color:var(--no)}.tag.ann{color:var(--unk)}
.est{font-weight:600;margin:2px 0 8px}.ctx{font-size:.95rem}.ctx .b,.ctx .a{color:var(--mut)}.ctx mark{background:var(--mark);color:inherit;padding:0 2px;border-radius:3px}
.q{margin:10px 0 6px;font-size:.92rem}.btns{display:flex;gap:8px;flex-wrap:wrap}
button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:8px;padding:8px 14px;cursor:pointer;min-height:40px}
button:hover{border-color:var(--acc)}button.sel.yes{background:var(--yes);color:#fff;border-color:var(--yes)}button.sel.no{background:var(--no);color:#fff;border-color:var(--no)}button.sel.unk{background:var(--unk);color:#fff;border-color:var(--unk)}
select,input[type=text]{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:8px;padding:7px 10px;max-width:100%}
.note{margin-top:8px;width:100%}a{color:var(--acc)}.kbd{font-family:ui-monospace,monospace;border:1px solid var(--line);border-radius:4px;padding:0 5px}
@media(max-width:560px){button{flex:1 1 30%}}
</style></head><body>
<header><h1>Adjudication: who is right, the system or the annotator?</h1>
<div class="bar"><i id="prog"></i></div>
<div class="row"><span id="count"></span>
<label>show <select id="filter"><option value="todo">undecided</option><option value="all">all</option><option value="yes">in scope</option><option value="no">not in scope</option><option value="unk">unsure</option></select></label>
<button id="dl">Download decisions (.jsonl)</button><button id="clear" title="forget all saved decisions">Reset</button></div></header>
<main>
<p class="intro">For each item, decide whether it is <b>a genuine effect estimate of the kind the
<a href="https://github.com/callmesobhan/evidencetrace-rag/blob/main/docs/annotation-guidelines.md">annotation guidelines</a> define</b>:
a between-group point estimate (HR, OR, RR, IRR, MD, SMD, RD; optionally with CI and p), <i>not</i> a planned/hypothetical value,
a baseline-balance statistic, a within-arm change, a rate or proportion, a regression coefficient, or an unnamed difference.
You are judging the <i>estimate</i>, not who found it. Keys: <span class="kbd">y</span> in scope, <span class="kbd">n</span> not in scope,
<span class="kbd">u</span> unsure, <span class="kbd">j</span>/<span class="kbd">k</span> next/previous. Progress is saved in this browser; download the file when you
are done (or any time) and give it back. The text is quoted from the open-access (CC BY) papers named in each item.</p>
<div id="list"></div></main>
<script type="application/json" id="data">__DATA__</script>
<script>
const items=JSON.parse(document.getElementById('data').textContent);const KEY='adjudication-v1';
let saved={};try{saved=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(saved))}catch(e){}};
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function hl(text,nums){if(!text)return'';let h=esc(text);return h.replace(/-?\\d+(?:\\.\\d+)?/g,m=>{const v=Math.abs(parseFloat(m));return nums.some(n=>Math.abs(n-v)<1e-9)?'<mark>'+m+'</mark>':m})}
const REASONS={'':'(reason, if not in scope)','balance':'baseline balance / SMD diagnostic','within_arm':'within-arm change','planned':'planned / threshold value','unnamed':'unnamed difference / effect size','rate':'rate, proportion or mean','coef':'regression coefficient / correlation','duplicate':'duplicate of another item','other':'other'};
function card(it){const s=saved[it.id]||{};const d=document.createElement('div');d.className='card';d.id='c'+it.id;
 let head,body;
 if(it.kind==='design'){head=`<span class="tag">study design</span><a href="https://pmc.ncbi.nlm.nih.gov/articles/${it.pmcid}/" target="_blank" rel="noopener">${it.pmcid}</a>`;
  body=`<div class="est">${esc(it.title)}</div><div class="ctx">PubMed publication types: <b>${esc(it.pubmed_types.join(', '))}</b><br>Classifier said: <b>${esc(it.classified_as)}</b> (from the ${esc(it.basis)}).</div><div class="q">Is this paper a report of a clinical trial (randomized or not)?</div>`;}
 else{const ci=it.ci?` (${it.ci[0]} to ${it.ci[1]})`:'';const sys=it.type==='system_only';
  head=`<span class="tag ${sys?'sys':'ann'}">${sys?'the SYSTEM extracted this; the annotator did not':'the ANNOTATOR recorded this; the system did not'}</span><a href="https://pmc.ncbi.nlm.nih.gov/articles/${it.pmcid}/" target="_blank" rel="noopener">${it.pmcid}</a>${it.section?`<span>${esc(it.section)}</span>`:''}`;
  const nums=[Math.abs(it.value)].concat((it.ci||[]).map(Math.abs));
  body=`<div class="est">${esc(it.metric)} ${esc(it.value)}${esc(ci)}</div><div class="ctx"><span class="b">${esc(it.before)}</span> ${hl(it.sentence,nums)} <span class="a">${esc(it.after)}</span></div><div class="q">Is the bold estimate a genuine in-scope effect estimate?</div>`;}
 d.innerHTML=`<div class="meta">${head}</div>${body}<div class="btns"><button class="yes" data-v="yes">${it.kind==='design'?'Yes, a trial':'Yes, in scope'}</button><button class="no" data-v="no">${it.kind==='design'?'No, not a trial':'No, not in scope'}</button><button class="unk" data-v="unk">Unsure</button>${it.kind==='design'?'':`<select class="reason">${Object.entries(REASONS).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select>`}</div><input class="note" type="text" placeholder="optional note" value="${esc(s.note||'')}">`;
 const paint=()=>{const cur=(saved[it.id]||{}).v;d.classList.toggle('done',!!cur);d.querySelectorAll('button[data-v]').forEach(b=>b.classList.toggle('sel',b.dataset.v===cur));d.querySelectorAll('button[data-v]').forEach(b=>b.classList.remove('yes','no','unk'));d.querySelectorAll('button[data-v]').forEach(b=>{if(b.dataset.v===cur)b.classList.add('sel',b.dataset.v)});};
 d.querySelectorAll('button[data-v]').forEach(b=>b.onclick=()=>{set(it.id,b.dataset.v)});
 const rs=d.querySelector('.reason');if(rs){rs.value=s.reason||'';rs.onchange=()=>{saved[it.id]={...(saved[it.id]||{}),reason:rs.value};save()}}
 d.querySelector('.note').oninput=e=>{saved[it.id]={...(saved[it.id]||{}),note:e.target.value};save()};
 d._paint=paint;paint();return d}
const cards={};const list=document.getElementById('list');
items.forEach(it=>{cards[it.id]=card(it);list.appendChild(cards[it.id])});
function set(id,v){saved[id]={...(saved[id]||{}),v};save();cards[id]._paint();refresh();const nx=nextTodo(id);if(nx&&document.getElementById('filter').value==='todo')nx.scrollIntoView({block:'center',behavior:'smooth'})}
function nextTodo(from){const i=items.findIndex(x=>x.id===from);for(let k=i+1;k<items.length;k++){if(!(saved[items[k].id]||{}).v)return cards[items[k].id]}return null}
function refresh(){const f=document.getElementById('filter').value;let done=0;items.forEach(it=>{const v=(saved[it.id]||{}).v;if(v)done++;cards[it.id].style.display=(f==='all'||(f==='todo'&&!v)||f===v)?'':'none'});
 document.getElementById('count').textContent=done+' of '+items.length+' decided';document.getElementById('prog').style.width=(100*done/items.length)+'%'}
document.getElementById('filter').onchange=refresh;
document.getElementById('clear').onclick=()=>{if(confirm('Forget every saved decision in this browser?')){saved={};save();items.forEach(it=>cards[it.id]._paint());refresh()}};
document.getElementById('dl').onclick=()=>{const lines=items.filter(it=>(saved[it.id]||{}).v).map(it=>JSON.stringify({id:it.id,kind:it.kind,pmcid:it.pmcid,decision:saved[it.id].v,reason:saved[it.id].reason||null,note:saved[it.id].note||null}));
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([lines.join('\\n')+'\\n'],{type:'application/jsonl'}));a.download='adjudication_decisions.jsonl';a.click()};
let cur=null;document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'||e.target.tagName==='SELECT')return;
 const vis=items.filter(it=>cards[it.id].style.display!=='none');if(!vis.length)return;if(!cur||!vis.includes(cur))cur=vis[0];
 const k=e.key.toLowerCase();if(k==='y'||k==='n'||k==='u'){set(cur.id,{y:'yes',n:'no',u:'unk'}[k])}
 if(k==='j'||k==='k'){const i=vis.indexOf(cur);cur=vis[Math.min(vis.length-1,Math.max(0,i+(k==='j'?1:-1)))];cards[cur.id].scrollIntoView({block:'center',behavior:'smooth'})}
 if(k==='y'||k==='n'||k==='u'){const i=vis.indexOf(cur);}});
refresh();
</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, action="append", help="disagreements.jsonl (repeatable); default: the 30-paper held-out round")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "adjudication.html")
    args = ap.parse_args()
    items = build_items(args.source or DEFAULT_SOURCES, [ROOT / "data/raw/fresh", ROOT / "data/raw/pmc"]) + design_items()
    data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(PAGE.replace("__DATA__", data), encoding="utf-8")
    n_est = sum(i["kind"] == "estimate" for i in items)
    print(f"{n_est} estimate items + {len(items) - n_est} design items -> {args.out} ({args.out.stat().st_size // 1000} kB)")


if __name__ == "__main__":
    main()
