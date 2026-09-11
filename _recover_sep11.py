import csv,json,os
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import databento as db
import occ
Z=ZoneInfo('America/New_York')
items=[
('09:50','HPE','2026-09-11','CALLS',62),('10:00','MU','2026-09-11','CALLS',990),
('10:05','HIMS','2026-09-18','CALLS',29),('10:12','TSLA','2026-09-16','PUTS',360),
('10:23','AAPL','2026-09-11','CALLS',335),('10:39','AMZN','2026-09-14','CALLS',255),
('11:28','MU','2026-09-11','CALLS',980),('11:21','SPY','2026-09-11','PUTS',766),
('10:50','HOOD','2026-09-18','CALLS',118),('13:10','ORCL','2026-09-18','CALLS',165),
('14:06','SHOP','2026-11-20','CALLS',150),('15:32','HAL','2026-10-16','CALLS',38),
('15:40','QQQ','2026-09-11','CALLS',716),('15:53','SPY','2026-09-18','CALLS',772),
('09:42','NVDA','2026-09-16','CALLS',220),('13:27','RKLB','2026-09-25','CALLS',70)]
cfg=json.load(open('settings.json',encoding='utf-8'))
key=((cfg.get('execution') or {}).get('databento') or {}).get('api_key','')
client=db.Historical(key)
end=datetime(2026,9,11,16,1,tzinfo=Z).astimezone(timezone.utc)
def fetch(item):
 hm,sym,exp,side,strike=item
 o=occ.build(sym,exp,side,strike); raw=occ.to_tasty(sym,exp,side,strike)
 h,m=map(int,hm.split(':')); start=datetime(2026,9,11,h,m,tzinfo=Z).astimezone(timezone.utc)
 try:
  df=client.timeseries.get_range(dataset='OPRA.PILLAR',symbols=[raw],schema='cbbo-1s',stype_in='raw_symbol',start=start,end=end).to_df()
  out=[]
  for ts,row in df.iterrows():
   try: b=float(row.get('bid_px_00')); a=float(row.get('ask_px_00'))
   except: continue
   if b>0 and a>0: out.append((int(ts.timestamp()),o,b,a))
  return o,out,None
 except Exception as e: return o,[],str(e)[:200]
results=[]
with ThreadPoolExecutor(max_workers=4) as pool:
 for fut in as_completed([pool.submit(fetch,x) for x in items]): results.append(fut.result())
path='missed_tape.csv'; existing=set()
if os.path.exists(path):
 with open(path,encoding='utf-8') as f:
  for r in csv.DictReader(f):
   try:
    if datetime.fromtimestamp(float(r['ts']),Z).date().isoformat()=='2026-09-11': existing.add(r['occ'])
   except: pass
new=not os.path.exists(path)
with open(path,'a',newline='',encoding='utf-8') as f:
 w=csv.writer(f)
 if new: w.writerow(['ts','occ','bid','ask'])
 for o,rows,err in sorted(results):
  if o not in existing: w.writerows(rows)
  print(o,len(rows),('ERROR '+err) if err else 'ok')
print('rows_written',sum(len(rows) for o,rows,e in results if o not in existing))
