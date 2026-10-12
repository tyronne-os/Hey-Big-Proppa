import csv,json
L='/home/user/Hey-Big-Proppa/lake/gold/nfl/'
def load(f): return {r['player_id']:r for r in csv.DictReader(open(L+f+'.csv'))}
U=load('player_usage');R=load('redzone_tiers');T=load('player_usage_td_correlation')
def f(x):
    try: return float(x)
    except: return None
SC={}
for r in csv.DictReader(open(L+'player_scoring_week.csv')):
    if r['season']=='2026' and r.get('season_type','REG')=='REG': SC.setdefault(r['player_id'],[]).append(r)
def fan(pid):
    g=sorted(SC.get(pid,[]),key=lambda r:int(r['week']))
    if not g: return {}
    pts=[f(r['total_points']) or 0 for r in g];ppr=[f(r['fantasy_points_ppr']) or 0 for r in g];tds=sum(f(r['total_tds']) or 0 for r in g)
    l3=ppr[-3:]
    return dict(ptsG=round(sum(pts)/len(pts),1),ptsTot=sum(pts),tds=tds,pprG=round(sum(ppr)/len(ppr),1),pprL3=round(sum(l3)/len(l3),1),pprTot=round(sum(ppr),1),pprLast=ppr[-1],fg=len(g))
FP={}
for pid in SC: FP[pid]=fan(pid)
POSR={}
for pid,u in U.items():
    if pid in FP and FP[pid]['fg']>=2: POSR.setdefault(u['position'],[]).append((FP[pid]['pprG'],pid))
RANK={}
for pos,l in POSR.items():
    for i,(v,pid) in enumerate(sorted(l,reverse=True),1): RANK[pid]=i
def cs(pid):
    u=U.get(pid)
    if not u: return None
    r=R.get(pid,{});t=T.get(pid,{})
    p5=f(r.get('pct_i5_intra'));flag=t.get('correlation_flag') or ''
    ui=f(u.get('usage_index_score'))
    q=bool(u['position'] in('RB','WR','TE') and p5 is not None and p5>=0.18 and 'AGREEMENT' in flag and ui is not None and ui>=55)
    return dict(pos=u['position'],games=int(u['games']),metric=u['spine_metric'],usage=ui,role=u['usage_role'],rankTeam=f(u['usage_rank_on_team']),rankPos=f(u['usage_rank_in_pos_group']),
      share=f(u['share_overall']),shareCalm=f(u['share_calm']),shareStress=f(u['share_stress']),conf=f(u['confidence_delta']),
      stress=f(u['stress_score']),redzone=f(u['redzone_score']),depthPos=u['depth_pos'],depthRank=f(u['depth_rank']),
      i20=f(u['opp_i20']),i10=f(u['opp_i10']),i5=f(u['opp_i5']),g2g=f(u['opp_g2g']),pctI5=p5,pctI20=f(u['pct_i20_shrunk']),
      fan=FP.get(pid),fanRank=RANK.get(pid),touches=f(u['touches']),ypt=f(u['yards_per_touch']),flag=flag,qualifies=q)
d=json.load(open('/tmp/table_data3.json'));n=0
for v in d.values():
    for r in v:
        for x in [r]+r['depth']:
            c=cs(x.get('playerId'))
            if c: x['cs']=c;n+=1
json.dump(d,open('/tmp/table_data3.json','w'));print('attached',n,'qualifying',sum(1 for v in d.values() for r in v if (r.get('cs') or {}).get('qualifies')))
