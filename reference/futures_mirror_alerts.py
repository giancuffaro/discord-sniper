import pandas as pd, re, datetime as dt
ET=dt.timezone(dt.timedelta(hours=-4))
def parse_time(d,t):
    t=str(t).strip()
    m=re.match(r'^(\d{1,2}):(\d{2})(?::(\d{2}))?',t)
    if not m: return None
    return dt.datetime.strptime(str(d)[:10],'%Y-%m-%d').replace(hour=int(m[1]),minute=int(m[2]),second=int(m[3] or 0),tzinfo=ET)
rows=[]
a=pd.read_csv('master_alerts.csv',low_memory=False)
for _,r in a[a['symbol'].isin(['SPY','QQQ'])].iterrows():
    side=str(r.get('side','')).upper()
    if not side.startswith(('C','P')): continue
    ts=parse_time(r['date'],r['time']); 
    if ts is None: continue
    rows.append(dict(ts=ts,sym=r['symbol'],dirn='L' if side.startswith('C') else 'S',room=r.get('room'),caller=r.get('caller'),src='bot',their=r.get('their_price'),outcome=r.get('outcome')))
c=pd.read_csv('recovered_alerts_chat.csv',low_memory=False)
cm=c[(c['symbol'].isin(['SPY','QQQ']))&(c['msg_type']=='entry')&(c['confidence'].isin(['high','medium']))]
for _,r in cm.iterrows():
    side=str(r.get('side','')).upper()
    if not side.startswith(('C','P')): continue
    ts=parse_time(r['date'],r['time'])
    if ts is None: continue
    room=str(r.get('room','')).split(' #')[0]
    rows.append(dict(ts=ts,sym=r['symbol'],dirn='L' if side.startswith('C') else 'S',room=room,caller=r.get('caller'),src='chat',their=r.get('their_price'),outcome='chat'))
df=pd.DataFrame(rows)
df=df[(df['ts']>=dt.datetime(2026,8,3,tzinfo=ET))&(df['ts']<=dt.datetime(2026,9,11,23,tzinfo=ET))]
# RTH only, before 15:45 so there is time to trade
df=df[(df['ts'].dt.hour*60+df['ts'].dt.minute>=9*60+30)&(df['ts'].dt.hour*60+df['ts'].dt.minute<=15*60+45)]
# dedupe: same symbol+direction within 3 minutes = one alert (relays/echoes)
df=df.sort_values('ts').reset_index(drop=True)
keep=[]; last={}
for i,r in df.iterrows():
    k=(r['sym'],r['dirn']); 
    if k in last and (r['ts']-last[k]).total_seconds()<180: continue
    last[k]=r['ts']; keep.append(i)
df=df.loc[keep].reset_index(drop=True)
df.to_pickle('/root/fx/alerts.pkl') if False else df.to_pickle(__import__('os').path.expanduser('~/fx/alerts.pkl'))
print("alerts after RTH filter + 3-min dedupe:",len(df)); print(df.groupby(['sym','dirn']).size().to_dict()); print("by source:",df['src'].value_counts().to_dict())
print("date range:",df['ts'].min().date(),"->",df['ts'].max().date(),"| trading days:",df['ts'].dt.date.nunique())
