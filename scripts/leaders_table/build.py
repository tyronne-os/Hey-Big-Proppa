import json
d=json.load(open('/tmp/table_data3.json'))
t=json.load(open('/tmp/targets_top20.json'))
print(type(d), list(d)[:6] if isinstance(d,dict) else d[0])
h=open('leaders-table.html').read()
tg=[dict(r,line=r['tgtPerGame'],proj=r['projTargets'],nextOppRank=r['dRank'],gp=None) for r in t]
pass
h=h.replace('''<button class="cat-tab" onclick="setCategory('Passing Yds',this)">''','''<button class="cat-tab" onclick="setCategory('Receptions',this)">Receptions</button>\n    <button class="cat-tab" onclick="setCategory('Passing Yds',this)">''')
h=h.replace('INJECT_TABLE_DATA',json.dumps(d))
h=h.replace("""    <button class="cat-tab active" onclick="setCategory('Rushing Yds',this)">""","""    <button class="cat-tab active" onclick="setCategory('Targets',this)">Targets</button>
    <button class="cat-tab" onclick="setCategory('Rushing Yds',this)">""")
h=h.replace("""<button class="cat-tab" onclick="setCategory('Rushing Yds',this)">""","""<button class="cat-tab" onclick="setCategory('Rushing Yds',this)">""")
h=h.replace("let currentCat = 'Rushing Yds';","let currentCat = 'Targets';\nconst TCOLS=[COLS[0],{key:'name',label:'Player',align:'left',fmt:'tplayer'},{key:'tgtPerGame',label:'Tgt/G',align:'right',fmt:'num1'},...COLS.slice(3).filter(c=>c.key!=='over_odds'&&c.key!=='under_odds').map(c=>c.key==='line'?{...c,label:'Avg Line'}:c)];\nfunction cols(){return currentCat==='Targets'?TCOLS:COLS;}")
h=h.replace("let sortKey    = 'diff';","let sortKey    = 'tgtPerGame';")
h=h.replace("""  btn.classList.add('active');
  populateGameFilter();""","""  btn.classList.add('active');
  sortKey = cat==='Targets' ? 'tgtPerGame' : 'diff'; sortDir=-1;
  
  populateGameFilter();""")
h=h.replace("""    case 'odds':""","""    case 'tplayer':
      return `<td class="td-player">${row.name||'—'}<span class="gp">${row.pos||''}</span></td>`;
    case 'tpi': {
      const c = pctColor(v);
      return `<td class="pct-cell" style="background:${c.bg};color:${c.fg}">${v ?? '—'}</td>`;
    }
    case 'share':
      return `<td class="td-num">${v != null ? (v*100).toFixed(1)+'%' : '—'}</td>`;
    case 'flag':
      return `<td style="text-align:left;font-size:10px;font-weight:700;color:var(--accent)">${v||''}</td>`;
    case 'odds':""")
h=h.replace("if (propFilter === 'Over')","if (propFilter === 'Over')").replace("if (propFilter === 'Under')","if (propFilter === 'Under')")
h=h.replace("let rows = augment(ALL[currentCat] || []);","let rows = currentCat==='Targets' ? augment(ALL.Targets||[]) : augment(ALL[currentCat] || []);")
h=h.replace("headEl.innerHTML = COLS.map","headEl.innerHTML = cols().map").replace("colspan=\"' + COLS.length","colspan=\"' + cols().length").replace("rows.map(row => '<tr>' + COLS.map","rows.map(row => '<tr>' + cols().map")
h=h.replace("' players'","(currentCat==='Targets'?' targets':' players')")
open('leaders-final.html','w').write(h)
