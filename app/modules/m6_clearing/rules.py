from decimal import Decimal
from app.reasons import sources
from app.errors import DomainError
def evaluate(rows,context):
    intake=context.get("intake")
    bad=context.get("quarantine",[])
    dispatch=context.get("dispatch") or {}
    accepted=set(x for row in rows for x in sources(row))
    rejected=set(x for row in bad for x in sources(row))
    dispatch_accepted=set(x for row in dispatch.get("rows",[]) for x in sources(row))
    dispatch_rejected=set(x for row in dispatch.get("quarantine",[]) for x in sources(row))
    if accepted & rejected: raise DomainError("LINEAGE_OVERLAP","同一来源行被重复裁决")
    if dispatch_accepted & dispatch_rejected: raise DomainError("LINEAGE_OVERLAP","调度来源行被重复裁决")
    m={"accepted_inputs":len(accepted),"quarantine_inputs":len(rejected),"output_records":len(rows)}
    dm=dispatch.get("metrics")
    if dm:
        total=dm.get("accepted",0)+dm.get("retries",0)+dm.get("quarantine",0)+dm.get("blank",0)+dm.get("superseded",0)
        m.update(dispatch_input=dm.get("input",0),dispatch_accepted=dm.get("accepted",0),dispatch_retries=dm.get("retries",0),dispatch_quarantine=dm.get("quarantine",0),dispatch_blank=dm.get("blank",0),dispatch_superseded=dm.get("superseded",0),dispatch_gaps=dm.get("gaps",0))
    if intake:
        excluded=intake["duplicate"]+intake["blank"]+intake["repeated_headers"]
        m.update(input=intake["input"],excluded=excluded,balanced=intake["input"]==len(accepted)+len(rejected)+excluded)
    else:m.update(input=len(accepted)+len(rejected),excluded=0,balanced=True)
    if dm:
        dispatch_balanced=dm.get("input",0)==total and dm.get("gaps",0)==0
        m.update(dispatch_balanced=dispatch_balanced,balanced=m["balanced"] and dispatch_balanced)
    output=[]
    for row in rows:
        expected=Decimal(str(row.get("expected","0")));reported=Decimal(str(row.get("reported","0")))
        output.append({**row,"difference":str(expected-reported),"status":"通过" if expected==reported else "差异"})
    m.update(expected_total=str(sum((Decimal(str(r.get("expected","0"))) for r in rows),Decimal(0))),reported_total=str(sum((Decimal(str(r.get("reported","0"))) for r in rows),Decimal(0))),differences=sum(r["status"]=="差异" for r in output))
    return {"rows":output,"quarantine":[],"metrics":m}
