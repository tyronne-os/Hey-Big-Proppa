import json,io,base64,ssl,urllib.request,os
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
d=json.load(open('/tmp/table_data3.json'))
urls={}
for v in d.values():
    for r in v:
        for x in [r]+r['depth']:
            if x.get('playerId') and x.get('photoUrl'): urls[x['playerId']]=x['photoUrl']
ctx=ssl.create_default_context(cafile='/root/.ccr/ca-bundle.crt')
def fetch(item):
    pid,u=item
    try:
        raw=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=20,context=ctx).read()
        im=Image.open(io.BytesIO(raw)).convert('RGBA')
        bg=Image.new('RGBA',im.size,(42,42,46,255)); bg.alpha_composite(im)
        w,h=bg.size; s=min(w,h); bg=bg.crop(((w-s)//2,0,(w-s)//2+s,s)).convert('RGB').resize((96,96))
        b=io.BytesIO(); bg.save(b,'JPEG',quality=72)
        return pid,'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()
    except Exception as e:
        return pid,None
with ThreadPoolExecutor(16) as ex: res=dict(ex.map(fetch,urls.items()))
ok={k:v for k,v in res.items() if v}
json.dump(ok,open('/tmp/photos.json','w'))
print(len(ok),'of',len(urls),sum(len(v) for v in ok.values())//1024,'KB')
