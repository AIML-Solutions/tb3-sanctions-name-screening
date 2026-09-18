import json,sys,re,uuid
src,dst_dir,variant=sys.argv[1:4]
new_id=str(uuid.uuid4())
lines=[json.loads(l) for l in open(src,errors="replace") if l.strip()]
SCRIPT=re.compile(r'[؀-ۿЀ-ӿ一-鿿]')
DOMAIN=[("sanctions","records"),("Sanctions","Records"),("watchlist","register"),("Watchlist","Register"),("screening","matching"),("Screening","Matching"),("SDN-","REG-"),("passport","docnum"),("Passport","Docnum"),("Abu Layth","Abu Nour"),("The Engineer","The Tailor"),("Al-Hakim","Abu Karim"),("The Sheikh","Hajji Omar"),("The Colonel","The Teacher"),("The Broker","The Grocer"),("El Jefe","Don Pepe"),("designated","recorded"),("decoy","look-alike"),("customer","client"),("Customer","Client")]
def mut_text(t):
    if variant=="strip-scripts": return SCRIPT.sub("?",t)
    if variant=="redact-domain":
        for a,b in DOMAIN: t=t.replace(a,b)
        return t
    if variant=="omit-tool-results": return t
    return t
def walk(c, in_tool_result=False):
    if isinstance(c,str): 
        if variant=="omit-tool-results" and in_tool_result: return "[tool output omitted]"
        return mut_text(c)
    if isinstance(c,list): return [walk(x,in_tool_result) for x in c]
    if isinstance(c,dict):
        if c.get("type")=="thinking": return c  # signed; never touch
        if c.get("type")=="tool_result":
            return {**c, "content": walk(c.get("content"), True)}
        if c.get("type")=="text": return {**c, "text": walk(c.get("text"), in_tool_result)}
        return {k:(walk(v,in_tool_result) if k in ("content","message","text") else v) for k,v in c.items()}
    return c
out=[]
n_asst=sum(1 for l in lines if l.get("type")=="assistant")
seen_asst=0
for l in lines:
    if variant=="truncate-half":
        if l.get("type")=="assistant": seen_asst+=1
        if seen_asst> n_asst//2: 
            # stop before the second half; keep only entries up to here (must end after a tool result: drop trailing assistant)
            break
    if l.get("type") in ("user","assistant") and variant!="truncate-half":
        l={**l, "message": walk(l.get("message"), False)}
    if "sessionId" in l: l["sessionId"]=new_id
    out.append(l)
if variant=="truncate-half":
    # ensure the tail ends on a user/tool_result line so the next turn is an assistant turn
    while out and out[-1].get("type")!="user": out.pop()
open(f"{dst_dir}/{new_id}.jsonl","w").write("\n".join(json.dumps(l,ensure_ascii=False) for l in out)+"\n")
print(new_id, "lines", len(out), "of", len(lines))
