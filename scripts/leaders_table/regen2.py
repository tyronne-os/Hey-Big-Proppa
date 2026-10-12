import json,csv,urllib.request,sys
sys.path.insert(0,'.')
import bpl,data,leaders
CATS={'Rushing Yds':('RUSHING','rushyds','player_rushing_week','rushing_yards',50),
      'Receiving Yds':('RECEIVING','recyds','player_receiving_week','receiving_yards',100),
      'Receptions':('RECEPTIONS','recs','player_receiving_week','receptions',100),
      'Passing Yds':('PASSING','passyds','player_passing_week','passing_yards',100)}
# multi-season game history straight from nflverse + lake (current season)
HIST={}  # col -> pid -> [(season,week,opp,value)]
FILES=['/tmp/nflv/w2023.csv','/tmp/nflv/w2024.csv','/tmp/nflv/w2025.csv']+['/home/user/Hey-Big-Proppa/lake/gold/nfl/%s.csv'%n for n in('player_rushing_week','player_receiving_week','player_passing_week')]
COLS=['rushing_yards','receiving_yards','receptions','passing_yards','targets']
seen=set()
for f in FILES:
    for r in csv.DictReader(open(f)):
        if r.get('season_type','REG')!='REG': continue
        for c in COLS:
            if r.get(c) in (None,''): continue
            k=(c,r['player_id'],r['season'],r['week'])
            if k in seen: continue
            seen.add(k)
            HIST.setdefault(c,{}).setdefault(r['player_id'],[]).append((int(r['season']),int(r['week']),r['opponent_team'],float(r[c])))
for c in HIST:
    for p in HIST[c]: HIST[c][p].sort()
def get(u): return json.load(urllib.request.urlopen('http://localhost:8086'+u,timeout=300))
tmap={r['playerId']:r for r in get('/api/targets')['rows']}
DIM=data.player_dimension()
NAMES={}
for f in FILES[:3]:
    for r in csv.DictReader(open(f)):
        if r.get('player_display_name'): NAMES[r['player_id']]=r['player_display_name']
for r in csv.DictReader(open('/home/user/Hey-Big-Proppa/lake/gold/nfl/depth_chart_pregame.csv')):
    if r.get('player_name') and r['player_id'] not in NAMES: NAMES[r['player_id']]=r['player_name']
def nm(pid,name):
    n=(tmap.get(pid) or {}).get('name')
    if not n or n.startswith('00-'): n=DIM.get(pid,{}).get('name')
    if not n or n.startswith('00-'): n=NAMES.get(pid) or name
    return n
def pct(a): return round(100*sum(a)/len(a)) if a else None
SEASON=2026
def hitrates(pid,col,line,opp):
    """Hit rates against the line shown in the table: Season = every 2026 game, L5 = last five 2026 games,
    vs Opp = every meeting since 2023. A hit is strictly over the line."""
    allg=HIST.get(col,{}).get(pid,[])
    cur=[v for (s,w,o,v) in allg if s==SEASON]
    ov=[v>line for v in cur]
    vs=[v for (s,w,o,v) in allg if o==opp]
    st=0
    for o_ in reversed(ov):
        if st==0: st=1 if o_ else -1
        elif (st>0)==o_: st+=1 if st>0 else -1
        else: break
    return dict(season=pct(ov),l5=pct(ov[-5:]),vs=pct([v>line for v in vs]) if vs else None,vsn=len(vs),streak=st)
def build(pid,name,team,gp,total,market,col,withgames=True):
    b=bpl.nfl_player_line(pid,market,name,team)
    line=b.get('sportsbookLine'); g=b.get('l5') or []
    vals=[x['value'] for x in g]; ov=[v>line for v in vals] if line is not None else []
    hr=hitrates(pid,col,line,b.get('nextOpp')) if line is not None else dict(season=None,l5=None,vs=None,vsn=0,streak=0)
    st=hr['streak']
    allg=HIST.get(col,{}).get(pid,[])
    row=dict(playerId=pid,name=nm(pid,name),team=team,pos=(tmap.get(pid) or {}).get('pos') or DIM.get(pid,{}).get('position'),photoUrl=data.photo_url(pid),gp=gp,season_total=total,
      line=line,proj=b.get('bpl'),diff=b.get('diffPct'),diff_abs=round(b['bpl']-line,1) if (b.get('bpl') is not None and line is not None) else None,
      nextOpp=b.get('nextOpp'),nextOppRank=b.get('nextOppRank'),nextOppHome=b.get('nextOppHome'),
      season_pct=hr['season'],l5_pct=hr['l5'],
      vs_opp=hr['vs'],vs_opp_n=hr['vsn'] if line is not None else 0,
      lineOpp=b.get('lineOpp'),lineLive=b.get('lineLive'),overPrice=b.get('overPrice'),underPrice=b.get('underPrice'),streak=st,parts=b.get('parts'),seasonAvg=b.get('seasonAvg'),books=b.get('books'))
    if withgames:
        row['games']=[dict(season=s,week=w,opp=o,value=v) for (s,w,o,v) in allg[-10:]]
    return row
out={}
for label,(cat,market,src,col,limit) in CATS.items():
    ranked=[r for r in leaders._rank(leaders._sum_by_player(src,col)) if r['value']>0]
    byteam={}
    for r in ranked: byteam.setdefault(r['team'],[]).append(r)
    rows=[]
    for r in ranked[:limit]:
        row=build(r['playerId'],r['name'],r['team'],r['gp'],r['value'],market,col)
        if row['line'] is None: continue
        depth=[build(t['playerId'],t['name'],t['team'],t['gp'],t['value'],market,col) for t in byteam[r['team']][:6]]
        row['depth']=depth
        rows.append(row)
    out[label]=rows; print(label,len(rows))
# Targets
def trow(r):
    h=r.get('hit') or {}
    line=r['line'] if r.get('line') is not None else round(r['projTargets']-r['projDiff'],1)
    p=lambda x: None if x is None else round(100*x)
    log=[x for x in (r.get('log') or [])][-10:]
    hr=hitrates(r['playerId'],'targets',line,r['opp'])
    return dict(playerId=r['playerId'],team=r['team'],name=nm(r['playerId'],r['name']),pos=r['pos'],photoUrl=r.get('photoUrl'),gp=r['games'],tgtPerGame=r['tgtPerGame'],line=line,proj=r['projTargets'],
      diff=round(100*r['projDiffPct'],1),diff_abs=r['projDiff'],nextOpp=r['opp'],nextOppRank=r['dRank'],season_pct=hr['season'],l5_pct=hr['l5'],
      vs_opp=hr['vs'],vs_opp_n=hr['vsn'],streak=hr['streak'],tpi=r.get('tpi'),flag=r.get('flag'),
      tparts=dict(projRec=r.get('projRec'),projYds=r.get('projYds'),teamVolume=r.get('teamVolume'),posFactor=r.get('posFactor'),shareSeason=r.get('shareSeason'),shareL3=r.get('shareL3'),role=r.get('role'),look=r.get('look')),
      games=[dict(season=x['season'],week=x['week'],opp=x['opp'],value=x['tgt']) for x in log])
allt=sorted(tmap.values(),key=lambda r:-(r.get('tgtPerGame') or 0))
tb={}
for r in allt: tb.setdefault(r['team'],[]).append(r)
sel=[];rb=0
for r in allt:
    if r['pos']=='RB':
        rb+=1
        if rb>50: continue
    sel.append(r)
    if len(sel)==100: break
trs=[]
for r in sel:
    x=trow(r); x['depth']=[trow(t) for t in tb[r['team']][:6]]; trs.append(x)
out['Targets']=trs; print('Targets',len(trs))
# Scoring / Field Goals: keep earlier rows, depth = same team within list
old=json.load(open('/tmp/table_data.json'))
for label in('Scoring Pts','Field Goals'):
    rows=old[label]
    for r in rows:
        r['games']=[dict(season=2026,week=g['week'],opp=g['opp'],value=g['value']) for g in r.get('l5_games',[])]
        r['vs_opp']=None;r['vs_opp_n']=0
    for r in rows: r['depth']=[dict(x) for x in rows if x['team']==r['team']][:6]
    out[label]=rows
json.dump(out,open('/tmp/table_data3.json','w'))
print(len(json.dumps(out))//1024,'KB')
