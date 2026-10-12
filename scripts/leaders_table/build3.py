h=open('leaders-final.html').read()

css = """
.bpnav{display:flex;justify-content:center;gap:6px;flex-wrap:wrap;padding:12px 0 10px;border-bottom:1px solid var(--border);}
.bpnav a{display:inline-flex;align-items:center;height:30px;padding:0 13px;border-radius:999px;border:1px solid var(--border2);background:var(--surface);color:var(--fg);font-size:11px;font-weight:700;letter-spacing:.1em;text-decoration:none;white-space:nowrap;}
.bpnav a:hover{border-color:#c9a54e;}
.bpnav a.on,.bpnav a.home{border-color:#c9a54e;background:rgba(201,165,78,.14);color:#f1dc92;}
.bpnav a.boo{border-color:#3a2060;background:rgba(139,92,246,.06);color:#9d72ff;}

tbody tr{cursor:pointer;}
tbody tr:hover td{filter:brightness(1.12);}
.pd{--p-bg:#050505;--p-panel:#111113;--p-line:#26262a;--p-fg:#f2f2f3;--p-fg2:#a1a1a8;--p-green:#14532d;--p-red:#7f1d1d;--p-tan:#d2b48c;
  background:var(--p-bg);color:var(--p-fg);border-radius:10px;padding:16px;margin-block:12px;}
.pd .back{background:#111113;color:#f5a623;border:1px solid #f5a623;border-radius:6px;padding:6px 12px;font-size:12px;cursor:pointer;margin-bottom:12px;}
.pd .hdr{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;}
.pd .ph{width:96px;height:96px;border-radius:50%;object-fit:cover;background:#2a2a2e;border:2px solid #f5a623;flex:none;}
.pd .nm{font-size:22px;font-weight:700;color:#f5a623;} .pd .sub{font-size:14px;color:var(--p-fg2);margin-top:2px;}
.pd .grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;margin-top:14px;}
@media(max-width:800px){.pd .grid{grid-template-columns:minmax(0,1fr);}}
.pd .panel{background:var(--p-panel);border-radius:8px;padding:14px;min-width:0;}
.pd .ptitle{font-size:14px;font-weight:700;color:#f5a623;margin-bottom:10px;}
.pd .propline{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;}
.pd .propline b{font-size:17px;} .pd .odds{font-size:16px;font-weight:700;}
.pd svg{width:100%;height:auto;display:block;}
.pd .tiles{display:flex;gap:8px;flex-wrap:wrap;}
.pd .tile{flex:1 1 74px;min-width:74px;background:#2a2a2e;border-radius:6px;overflow:hidden;text-align:center;}
.pd .tile .t1{font-size:10px;font-weight:700;letter-spacing:.05em;padding:6px 4px 2px;color:var(--p-fg2);}
.pd .tile .t2{font-size:15px;font-weight:700;padding:2px 4px 6px;}
.pd .tile .t3{font-size:11px;font-weight:700;padding:5px 4px;color:#fff;}
.pd .rowlbl{display:grid;grid-template-columns:54px 1fr;align-items:center;gap:8px;margin-top:8px;}
.pd .rowlbl span{font-size:10px;color:var(--p-fg2);font-weight:700;letter-spacing:.05em;}
.pd .depth{margin-top:12px;}
.pd .depth .tbl-wrap{background:var(--p-panel);border-radius:8px;}
.pd table{color:var(--p-fg);} .pd th{background:#232327;color:var(--p-fg2);} .pd td{border-color:var(--p-line);}
.pd tr.me td.td-player{box-shadow:inset 3px 0 0 var(--p-tan);} 
.pd td,.pd .td-num,.pd .td-proj,.pd .td-player{color:var(--p-fg);} .pd .td-team{color:var(--p-fg2);} .pd .gp{color:var(--p-fg2);} .pd td.streak-over{color:#22c55e;} .pd td.streak-under{color:#ef4444;} .pd .rk{color:var(--p-fg2);font-size:11px;margin-right:6px;}
"""
h=h.replace('</style>',css+'</style>',1)
h=h.replace('<script>','<div id="pd" class="pd" hidden></div>\n<script>',1)

h=h.replace("    case 'odds':","    case 'vsopp': {\n      const vv = row.vs_opp_n >= 2 ? v : null; const c = pctColor(vv);\n      const n = row.vs_opp_n ? `<span style=\"font-size:9px;opacity:.7\"> (${row.vs_opp_n})</span>` : '';\n      return `<td class=\"pct-cell\" style=\"background:${c.bg};color:${c.fg}\">${vv != null ? vv+'%'+n : '—'}</td>`;\n    }\n    case 'odds':",1)
h=h.replace('<div class="page-hdr">','<nav class="bpnav" aria-label="Main">\n  <a class="home" href="https://aibruh-big-proppa-live.hf.space/home/index.html" target="_blank" rel="noopener">HOME</a>\n  <a class="on" href="https://aibruh-big-proppa-live.hf.space/leaders?cat=targets" target="_blank" rel="noopener">LEADERS · TARGETS</a>\n  <a href="https://aibruh-big-proppa-live.hf.space/matchups" target="_blank" rel="noopener">MATCHUPS</a>\n  <a href="https://aibruh-big-proppa-live.hf.space/ramp" target="_blank" rel="noopener">RAMP</a>\n  <a href="https://aibruh-big-proppa-live.hf.space/college" target="_blank" rel="noopener">COLLEGE</a>\n  <a href="https://aibruh-big-proppa-live.hf.space/throwdown" target="_blank" rel="noopener">THROWDOWN THURSDAY</a>\n  <a href="https://aibruh-big-proppa-live.hf.space/monday" target="_blank" rel="noopener">MONDAY NIGHT</a>\n  <a href="https://aibruh-big-proppa-live.hf.space/sunday-night" target="_blank" rel="noopener">SUNDAY NIGHT</a>\n  <a href="https://aibruh-big-proppa-live.hf.space/parlays" target="_blank" rel="noopener">SUNDAY SLIPS</a>\n  <a href="https://aibruh-big-proppa-live.hf.space/engine" target="_blank" rel="noopener">ENGINE</a>\n  <a href="https://aibruh-big-proppa-live.hf.space/news" target="_blank" rel="noopener">NEWS</a>\n  <a href="https://aibruh-big-proppa-live.hf.space/queries" target="_blank" rel="noopener">QUERIES</a>\n  <a class="boo" href="https://aibruh-big-proppa-live.hf.space/myboo" target="_blank" rel="noopener">MY BOO</a>\n  <a href="https://aibruh-big-proppa-live.hf.space/odds" target="_blank" rel="noopener">THE ODDS</a>\n</nav>\n'+'<div class="page-hdr">',1)
h=h.replace('<div class="page-title">🏈 Big Proppa</div>','<div class="page-title" style="text-align:center">🏈 Big Proppa · Leaders</div>',1)
# clickable rows
old="bodyEl.innerHTML = rows.map(row => '<tr>' + cols().map(col => fmtCell(col, row)).join('') + '</tr>').join('');"
assert old in h
h=h.replace(old,"window.VIEW = rows;\n    bodyEl.innerHTML = rows.map((row,i) => '<tr onclick=\"openPlayer(' + i + ')\">' + cols().map(col => fmtCell(col, row)).join('') + '</tr>').join('');")

js = r"""
const PH = __PH__;
const UNIT = {'Rushing Yds':'Rushing Yards','Receiving Yds':'Receiving Yards','Receptions':'Receptions','Passing Yds':'Passing Yards','Scoring Pts':'Scoring Points','Field Goals':'Field Goals Made','Targets':'Targets'};
const LISTSEL = ['.page-hdr','.controls','.tbl-wrap'];
let lastScroll = 0;
let SPLIT = 'L5', CURSEL = null;
function hitTile(label, games, line) {
  const sel = SPLIT === label ? 'outline:2px solid #f5a623;outline-offset:-2px;' : '';
  const n = games.length;
  if (!n || line == null) return `<div class="tile" style="cursor:pointer;${sel}" onclick="setSplit('${label}')"><div class="t1">${label}</div><div class="t2">n/a</div><div class="t3" style="background:#3a3a3f">—</div></div>`;
  const hits = games.filter(g => g.value > line).length;
  const avg = games.reduce((a,g)=>a+g.value,0)/n;
  const p = Math.round(100*hits/n), c = pctColor(p);
  return `<div class="tile" style="cursor:pointer;${sel}" onclick="setSplit('${label}')"><div class="t1">${label}</div><div class="t2">${avg.toFixed(1)}</div><div class="t3" style="background:${c.bg};color:${c.fg}">${p}%<br>${hits}/${n}</div></div>`;
}
function barChart(games, line) {
  if (!games.length) return '<div style="color:var(--p-fg2);padding:30px;text-align:center">No game log yet</div>';
  const W=640,H=270,L=34,R=40,T=14,B=44, n=games.length;
  const mx = Math.max(line||0, ...games.map(g=>g.value), 1) * 1.15;
  const y = v => T + (H-T-B) * (1 - v/mx);
  const bw = (W-L-R)/n, bar = Math.min(44, bw*0.7);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Game log vs line">`;
  const ticks=4;
  for (let i=0;i<=ticks;i++){ const v=mx*i/ticks, yy=y(v); s+=`<line x1="${L}" x2="${W-R}" y1="${yy}" y2="${yy}" stroke="#2e2e33"/><text x="${L-6}" y="${yy+4}" text-anchor="end" font-size="11" fill="#a1a1a8">${v>=10?Math.round(v):v.toFixed(1)}</text>`; }
  games.forEach((g,i)=>{
    const cx=L+bw*i+bw/2, hit = line!=null && g.value>line, yy=y(g.value);
    s+=`<rect x="${cx-bar/2}" y="${yy}" width="${bar}" height="${Math.max(1,H-B-yy)}" fill="${hit?'#14532d':'#7f1d1d'}" stroke="${hit?'#22c55e':'#ef4444'}" stroke-width="1"/>`;
    s+=`<text x="${cx}" y="${yy-4}" text-anchor="middle" font-size="12" font-weight="700" fill="#f2f2f3">${g.value}</text>`;
    const old = g.season < 2026, lc = old ? '#e2631a' : '#f2f2f3';
    s+=`<text x="${cx}" y="${H-B+14}" text-anchor="middle" font-size="11" font-weight="${old?700:400}" fill="${lc}">${g.opp}</text>`;
    s+=`<text x="${cx}" y="${H-B+27}" text-anchor="middle" font-size="9" font-weight="${old?700:400}" fill="${old?'#e2631a':'#a1a1a8'}">'${String(g.season).slice(2)} W${g.week}</text>`;
  });
  if (line!=null) s+=`<line x1="${L}" x2="${W-R}" y1="${y(line)}" y2="${y(line)}" stroke="#f5a623" stroke-width="2" stroke-dasharray="5 4"/><text x="${W-R+4}" y="${y(line)+4}" font-size="12" font-weight="700" fill="#f5a623">${line}</text>`;
  const anyOld = games.some(g => g.season < 2026);
  s += '</svg>';
  if (anyOld) s += '<div style="font-size:11px;color:#a1a1a8;margin-top:4px"><span style="color:#e2631a;font-weight:700">Burnt orange</span> = game from last season</div>';
  return s;
}
function scoreTile(k,v){ if (v==null) return statTile(k,null); const c = v>=70?'#22c55e':v>=40?'#d2b48c':'#ef4444'; return statTile(k, Math.round(v), c); }
function pctTile(k,v,hi,mid){ if (v==null) return statTile(k,null); const c = v>=hi?'#22c55e':v>=mid?'#d2b48c':'#ef4444'; return statTile(k,(v*100).toFixed(0)+'%',c); }
function coachesPanel(row){
  const c = row.cs;
  if (!c) return `<div class="panel"><div class="ptitle">Coaches Son</div><div style="color:var(--p-fg2);font-size:12px">No usage data in the lake for this player yet.</div></div>`;
  const badge = c.qualifies ? '<span style="background:#f5a623;color:#000;font-size:10px;font-weight:800;padding:2px 8px;border-radius:10px;margin-left:8px;letter-spacing:.05em">COACHES SON</span>' : '';
  const fa = c.fan || {};
  const n = v => v;
  return `<div class="panel"><div class="ptitle">Coaches Son${badge}</div>
    <div style="font-size:12px;color:var(--p-fg2);margin:-4px 0 10px">${c.role||''} · ${c.metric.replace(/_/g,' ')}</div>
    <div class="tiles">${scoreTile('USAGE INDEX',c.usage)}${statTile('TEAM RANK', c.rankTeam!=null?'#'+c.rankTeam:null)}${statTile(c.pos+' RANK', c.rankPos!=null?'#'+c.rankPos:null)}${statTile('DEPTH', c.depthRank!=null?c.depthPos+c.depthRank:null)}</div>
    ${c.pos==='QB' ? '' : `<div class="rowlbl" style="grid-template-columns:70px 1fr"><span>SCORING</span><div class="tiles">${statTile('PTS / G', fa.ptsG)}${statTile('SEASON PTS', fa.ptsTot)}${statTile('TOTAL TDs', fa.tds)}</div></div>`}
    <div class="rowlbl" style="grid-template-columns:70px 1fr"><span>FANTASY PPR</span><div class="tiles">${statTile('PPR / G', fa.pprG)}${statTile('L3 PPR / G', fa.pprL3, fa.pprL3>fa.pprG?'#22c55e':fa.pprL3<fa.pprG?'#ef4444':null)}${statTile('SEASON PPR', fa.pprTot)}${statTile(c.pos+' PPR RANK', c.fanRank!=null?'#'+c.fanRank:null)}</div></div>
    <div class="rowlbl" style="grid-template-columns:70px 1fr"><span>WORKLOAD</span><div class="tiles">${scoreTile('REDZONE SCORE',c.redzone)}${scoreTile('STRESS SCORE',c.stress)}${statTile('TOUCHES',c.touches)}</div></div>
    ${c.flag?`<div style="margin-top:10px;font-size:11px;color:var(--p-fg2)">Finishing check: <b style="color:#f5a623">${c.flag}</b></div>`:''}
    </div>`;
}
function statTile(k,v,color){ return `<div class="tile"><div class="t1">${k}</div><div class="t2"${color?` style="color:${color}"`:''}>${v ?? 'n/a'}</div></div>`; }
function setSplit(k) { SPLIT = k; openPlayer(CURSEL.i, CURSEL.fromDepth, true); }
function openPlayer(i, fromDepth, keep) {
  if (!keep) SPLIT = 'L5';
  CURSEL = {i, fromDepth};
  const row = fromDepth ? window.DEPTH[i] : window.VIEW[i];
  if (!row) return;
  const depth = fromDepth ? window.DEPTH : (row.depth || []);
  window.DEPTH = depth;
  if (!fromDepth) lastScroll = window.scrollY;
  const aug = augment([row])[0];
  const games = row.games || [];
  const cur = games.filter(g => g.season >= 2026);
  const vsAll = games.filter(g => g.opp === row.nextOpp);
  const vs = vsAll.length >= 2 ? vsAll : [];
  const line = row.line;
  const chartGames = SPLIT==='L5' ? cur.slice(-5) : SPLIT==='2026' ? cur : SPLIT==='H2H' ? vs : games.slice(-10);
  const unit = UNIT[currentCat] || '';
  const dc = row.nextOppRank ? drankColor(row.nextOppRank) : null;
  const p = row.parts || {};
  const tp = row.tparts || {};
  const sign = v => v > 0 ? '+'+v : v;
  const dtile = row.nextOppRank ? `<span class="drank" style="background:${dc.bg};color:${dc.fg}">${row.nextOppRank}</span>` : 'n/a';
  const defTiles = currentCat==='Targets'
    ? statTile('D RANK', dtile) + statTile('TEAM TGT/G', tp.teamVolume) + statTile('SHARE', tp.shareSeason!=null?(tp.shareSeason*100).toFixed(1)+'%':'n/a')
    : statTile('D RANK', dtile) + statTile('ALLOWED/G', p.oppAllowed) + statTile('SITE', row.nextOppHome==null?'n/a':row.nextOppHome?'HOME':'AWAY');
  const stale = row.lineLive === false;
  const lineLbl = currentCat==='Targets' ? 'AVG LINE' : stale ? 'LINE †' : 'LINE';
  const projTiles = currentCat==='Targets'
    ? statTile(lineLbl, line) + statTile('PROJ TGTS', row.proj) + statTile('SAFE BET', aug.safe, '#22c55e') + statTile('PROJ REC', tp.projRec) + statTile('PROJ YDS', tp.projYds) + statTile('TPI', row.tpi)
    : statTile(lineLbl, line) + statTile('BPL PROJ', row.proj) + statTile('SAFE BET', aug.safe, '#22c55e') + statTile('DIFF', row.diff!=null?sign(row.diff)+'%':'n/a', row.diff>=5?'#4ade80':row.diff<=-5?'#f87171':'#d2b48c') + statTile('BLENDED AVG', p.baseline) + statTile('SEASON AVG', row.seasonAvg);
  const dRows = augment(depth).map(d=>d.line==null?{...d,over_odds:null,under_odds:null}:d).map((d,j) => `<tr class="${d.playerId===row.playerId&&d.name===row.name?'me':''}" onclick="openPlayer(${j},true)">` + cols().map(col => col.fmt==='player'||col.fmt==='tplayer' ? `<td class="td-player"><span class="rk">#${j+1}</span>${d.name||'—'}<span class="gp">${d.pos||''} · ${d.gp||0} GP</span></td>` : fmtCell(col,d)).join('') + '</tr>').join('');
  const head = cols().map(col => `<th class="${col.key==='proj'?'bp-th':''}" ${col.align==='left'?'style="text-align:left"':col.align==='center'?'style="text-align:center"':''}>${col.label}</th>`).join('');
  const photo = PH[row.playerId] ? `<img class="ph" src="${PH[row.playerId]}" alt="${row.name}" onerror="this.style.display='none'">` : '';
  document.getElementById('pd').innerHTML = `
    <button class="back" onclick="closePlayer()">← Back to ${currentCat}</button>
    <div class="hdr"><div><div class="nm">${row.name}</div>
      <div class="sub">${row.pos?row.pos+', ':''}${row.team} · ${row.gp} GP${row.nextOpp?' · next: '+(row.nextOppHome===false?'@':'vs ')+row.nextOpp:''}</div></div>${photo}</div>
    <div class="grid">
      <div class="panel">
        <div class="propline"><b>${line!=null?line:'—'} ${unit}</b>${aug.over_odds!=null?`<span class="odds" style="color:${aug.over_odds>0?'#4ade80':'#f2f2f3'}">O ${aug.over_odds>0?'+':''}${aug.over_odds}${aug.under_odds!=null?` · U ${aug.under_odds>0?'+':''}${aug.under_odds}`:''}</span>`:''}</div>
        ${stale && line!=null ? `<div style="font-size:11px;color:#f5a623;margin:-2px 0 6px">† Last posted line (priced vs ${row.lineOpp||'a prior opponent'}). ${row.nextOpp||'This week'}'s line isn't posted yet, so Diff and hit rates measure against it.</div>` : ''}${currentCat==='Targets' ? '<div style="font-size:11px;color:#a1a1a8;margin:-2px 0 6px">No book posts targets lines. Line = his own average, so Diff shows how much the matchup moves his volume.</div>' : ''}
        ${barChart(chartGames.slice().reverse(), line)}
        <div class="rowlbl"><span>SPLIT</span><div class="tiles">
          ${hitTile('2026', cur, line)}${hitTile('H2H', vs, line)}${hitTile('L10', games.slice(-10), line)}${hitTile('L5', cur.slice(-5), line)}
        </div></div>
      </div>
      <div style="display:flex;flex-direction:column;gap:12px;min-width:0">
        <div class="panel"><div class="ptitle">${row.nextOpp||'Opponent'} Defense (Allowed)</div><div class="tiles">${defTiles}</div></div>
        <div class="panel"><div class="ptitle">${row.name} Projections</div><div class="tiles">${projTiles}</div></div>
        ${coachesPanel(row)}
      </div>
    </div>
    <div class="depth"><div class="ptitle" style="margin:14px 0 8px">${row.team} depth chart · ${unit}</div>
      <div class="tbl-wrap"><table><thead><tr>${head}</tr></thead><tbody>${dRows}</tbody></table></div></div>`;
  LISTSEL.forEach(s => { const e=document.querySelector(s); if (e) e.hidden = true; });
  document.getElementById('pd').hidden = false;
  if (!keep) window.scrollTo(0,0);
}
function closePlayer() {
  document.getElementById('pd').hidden = true;
  LISTSEL.forEach(s => { const e=document.querySelector(s); if (e) e.hidden = false; });
  window.scrollTo(0,lastScroll);
}
"""
h=h.replace("// init\n",js+"\n// init\n",1)
import json
h=h.replace('__PH__',json.dumps(json.load(open('/tmp/photos.json'))))
open('leaders-final.html','w').write(h)
