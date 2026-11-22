import hashlib,json
from app.errors import DomainError
from app.reasons import sources
def _chains(rows):
    """Each card-day must hold exactly one adopted transfer/cap chain.

    A second chain (e.g. one replaying the printed code beside the dispatch
    line) would show up as an anchor that is not itself an adopted journey of
    the same card-day, or as a repeated event in that card-day.
    """
    chains={}
    for row in rows:
        key=(row.get("card"),row.get("business_day"))
        chains.setdefault(key,[]).append(row)
    for key,group in chains.items():
        ids=[row.get("event_id") for row in group]
        if len(ids)!=len(set(ids)): raise DomainError("DUPLICATE_CARD_DAY","同卡同日存在多套换乘或封顶结果")
        known={str(x) for x in ids}
        for row in group:
            anchor=row.get("transfer_anchor")
            if anchor and anchor!="—" and anchor not in known:
                raise DomainError("BROKEN_CHAIN","换乘锚点不属于同卡同日同一套结果")
    return len(chains)
def evaluate(rows,context):
    stages=[v for v in context.values() if isinstance(v,dict) and "metrics" in v]
    dispatch=context.get("dispatch") or {}
    balances=[s["metrics"]["balanced"] for s in stages if "balanced" in s["metrics"]]
    if balances and not all(balances): raise DomainError("UNBALANCED","来源行未对平，不能归档")
    dm=dispatch.get("metrics")
    if dm and (dm.get("input",0)!=dm.get("accepted",0)+dm.get("retries",0)+dm.get("quarantine",0)+dm.get("blank",0)+dm.get("superseded",0) or dm.get("gaps",0)):
        raise DomainError("UNBALANCED_DISPATCH","调度来源行未逐条有着落，不能归档")
    ids=[str(r.get("event_id",r.get("_line",""))) for r in rows]
    if len(ids)!=len(set(ids)): raise DomainError("ARCHIVE_DUPLICATE","归档业务键重复")
    cards=_chains(rows)
    encoded=json.dumps(rows,ensure_ascii=False,sort_keys=True,default=str).encode()
    m={"records":len(rows),"source_lines":len(set(x for row in rows for x in sources(row))),"sha256":hashlib.sha256(encoded).hexdigest(),"ready":True,"differences":sum(r.get("status")=="差异" for r in rows),"card_days":cards,"chains":cards}
    if dm:
        m.update(dispatch_input=dm["input"],dispatch_accepted=dm["accepted"],dispatch_lines=len(set(x for row in dispatch.get("rows",[]) for x in sources(row))))
    return {"rows":rows,"quarantine":[],"metrics":m}
