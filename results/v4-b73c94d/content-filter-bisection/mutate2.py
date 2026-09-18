import json,sys,uuid
src,dst_dir,pairs_json=sys.argv[1:4]
PAIRS=json.loads(pairs_json); new_id=str(uuid.uuid4())
def mt(t):
    for a,b in PAIRS: t=t.replace(a,b)
    return t
def walk(c):
    if isinstance(c,str): return mt(c)
    if isinstance(c,list): return [walk(x) for x in c]
    if isinstance(c,dict):
        if c.get("type")=="thinking": return c
        return {k:(walk(v) if k in ("content","message","text") else v) for k,v in c.items()}
    return c
out=[]
for l in (json.loads(x) for x in open(src,errors="replace") if x.strip()):
    if l.get("type") in ("user","assistant"): l={**l,"message":walk(l.get("message"))}
    if "sessionId" in l: l["sessionId"]=new_id
    out.append(l)
open(f"{dst_dir}/{new_id}.jsonl","w").write("\n".join(json.dumps(l,ensure_ascii=False) for l in out)+"\n"); print(new_id)
