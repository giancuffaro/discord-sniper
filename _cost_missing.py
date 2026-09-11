import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import databento as db
import occ
cfg=json.load(open('settings.json',encoding='utf-8'))
key=((cfg.get('execution') or {}).get('databento') or {}).get('api_key','')
items=[
('HPE','2026-09-11','CALLS',62),('MU','2026-09-11','CALLS',990),
('HIMS','2026-09-18','CALLS',29),('TSLA','2026-09-16','PUTS',360),
('AAPL','2026-09-11','CALLS',335),('AMZN','2026-09-14','CALLS',255),
('MU','2026-09-11','CALLS',980),('SPY','2026-09-11','PUTS',766),
('HOOD','2026-09-18','CALLS',118),('ORCL','2026-09-18','CALLS',165),
('SHOP','2026-11-20','CALLS',150),('HAL','2026-10-16','CALLS',38),
('QQQ','2026-09-11','CALLS',716),('SPY','2026-09-18','CALLS',772),
('NVDA','2026-09-16','CALLS',220),('RKLB','2026-09-25','CALLS',70)]
syms=[occ.to_tasty(*x) for x in items]
z=ZoneInfo('America/New_York')
start=datetime(2026,9,11,9,39,tzinfo=z).astimezone(timezone.utc)
end=datetime(2026,9,11,16,1,tzinfo=z).astimezone(timezone.utc)
print('exact_contracts',len(syms))
try:
 c=db.Historical(key).metadata.get_cost(dataset='OPRA.PILLAR',symbols=syms,schema='cbbo-1s',stype_in='raw_symbol',start=start,end=end)
 print('quoted_cost',c)
except Exception as e:
 print('cost_error',type(e).__name__,str(e)[:500])
