import pandas as pd, numpy as np, datetime as dt, math, os
ET=dt.timezone(dt.timedelta(hours=-4))
A=pd.read_pickle(os.path.expanduser('~/fx/alerts.pkl'))
bars={}
for root,f in (('ES','bars/ES_1m_2026-08-03_2026-09-12.csv'),('NQ','bars/NQ_1m_2026-08-03_2026-09-12.csv')):
    b=pd.read_csv(f); b['ts']=pd.to_datetime(b['ts_event'],utc=True); b=b.set_index('ts').sort_index(); bars[root]=b
MAP={'SPY':('ES',5.0),'QQQ':('NQ',2.0)}   # micro $/pt: MES 5, MNQ 2
STOP,TGT=25.0,50.0
ARM=STOP*(5/7.5); STEP=STOP*(2/7.5)        # arm at 2/3 stop -> BE; rung every 6.67
CLOSE=dt.time(15,59)
def run(a, mode):
    root,ppt=MAP[a['sym']]; b=bars[root]; s=1 if a['dirn']=='L' else -1
    t0=(a['ts']+dt.timedelta(minutes=1)).replace(second=0,microsecond=0)
    day_end=a['ts'].replace(hour=CLOSE.hour,minute=CLOSE.minute,second=0,microsecond=0)
    w=b[(b.index>=t0)&(b.index<=day_end)]
    if w.empty: return dict(status='no bars')
    if mode=='market':
        e=float(w.iloc[0]['open']); ei=0
    else:  # 25-pt snap limit in his favour, 10-min window
        ref=float(w.iloc[0]['open'])
        lvl=math.floor(ref/25)*25 if s>0 else math.ceil(ref/25)*25
        ei=None
        for i in range(min(10,len(w))):
            r=w.iloc[i]
            if (s>0 and r['low']<=lvl) or (s<0 and r['high']>=lvl): ei=i; break
        if ei is None: return dict(status='snap never touched', lvl=lvl, ref=ref)
        e=float(lvl)
    stop=e-s*STOP; tgt=e+s*TGT; mfe=0.0; mae=0.0
    for i in range(ei,len(w)):
        r=w.iloc[i]; hi,lo=float(r['high']),float(r['low'])
        fav=(hi-e)*s if s>0 else (e-lo); adv=(e-lo) if s>0 else (hi-e)
        # stop first (conservative), then target, then ratchet on this bar's excursion
        hit_stop=(lo<=stop) if s>0 else (hi>=stop)
        hit_tgt=(hi>=tgt) if s>0 else (lo<=tgt)
        if hit_stop: ex=stop; why='STOP' if stop==e-s*STOP else ('BE' if abs(stop-e)<1e-9 else 'RATCHET'); break
        if hit_tgt: ex=tgt; why='TARGET'; break
        mfe=max(mfe,fav); mae=max(mae,adv)
        if mfe>=ARM:
            k=math.floor((mfe-ARM)/STEP); new=e+s*(k*STEP)
            if (s>0 and new>stop) or (s<0 and new<stop): stop=new
    else:
        ex=float(w.iloc[-1]['close']); why='CLOSE'
    pts=(ex-e)*s
    return dict(status='ok',entry=e,exit=ex,why=why,pts=pts,usd=pts*ppt,mfe=mfe,mae=mae,bars=i-ei+1)
out=[]
for mode in ('market','snap'):
    for _,a in A.iterrows():
        r=run(a,mode); r.update(mode=mode,ts=a['ts'],sym=a['sym'],dirn=a['dirn'],room=a['room'],caller=a['caller'],src=a['src']); out.append(r)
R=pd.DataFrame(out); R.to_csv(os.path.expanduser('~/fx/replay.csv'),index=False)
for mode in ('market','snap'):
    x=R[(R['mode']==mode)]; ok=x[x['status']=='ok']
    print(f"\n===== {mode.upper()} entry =====  alerts {len(x)}  traded {len(ok)}  skipped {len(x)-len(ok)} ({x[x['status']!='ok']['status'].value_counts().to_dict()})")
    print(f"  GROSS ${ok['usd'].sum():+.0f}   win {(ok['usd']>0).mean()*100:.0f}%   avg ${ok['usd'].mean():+.1f}/trade   exits {ok['why'].value_counts().to_dict()}")
    print(f"  after $1.50 RT/contract: ${ok['usd'].sum()-1.5*len(ok):+.0f}")
    g=ok.groupby('sym').agg(n=('usd','size'),usd=('usd','sum'),win=('usd',lambda s:(s>0).mean()*100),avg_pts=('pts','mean'),mfe=('mfe','median'),mae=('mae','median')).round(1)
    print(g.to_string())
    print("  by direction:"); print(ok.groupby(['sym','dirn'])['usd'].agg(['size','sum']).round(0).to_string())
