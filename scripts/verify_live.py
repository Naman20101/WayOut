"""Exercise actual HTTP/MySQL routing; writes a reproducible validation report."""
import json,time
from pathlib import Path
import requests
root=Path(__file__).resolve().parents[1];base='http://127.0.0.1:5000';s=requests.Session()
status=s.get(base+'/api/status').json();headers={'X-CSRF-Token':status['csrf']};report=[]
for region in ['kochi','kathmandu','tokyo']:
    demo=s.get(base+'/api/demo',params={'region':region}).json()
    for mode in ['walking','bicycle','car']:
        payload={**demo,'region':region,'mode':mode,'hazard':'flood' if region=='kochi' else 'earthquake','simulation_destination':True}
        start=time.time();r=s.post(base+'/api/route',json=payload,headers=headers,timeout=300);d=r.json()
        report.append({'region':region,'mode':mode,'status':r.status_code,'seconds':round(time.time()-start,2),'shortest_m':d.get('shortest',{}).get('distance_m'),'recommended_m':d.get('recommended',{}).get('distance_m'),'error':d.get('error')})
        if r.status_code==200:
            assert d['recommended']['cost']<=d['shortest']['risk_adjusted_cost']+.1
            assert d['shortest']['distance_m']<=d['recommended']['distance_m']+.1
            assert s.get(base+'/route/'+str(d['id'])).status_code==200
            assert requests.get(base+'/route/'+str(d['id'])).status_code==404
        print(report[-1],flush=True)
(root/'docs/live_validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
