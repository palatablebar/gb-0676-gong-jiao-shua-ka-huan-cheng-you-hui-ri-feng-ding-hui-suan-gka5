import time
from app.config import ROOT,MODULES
from app.errors import DomainError
from app.values import scalar
from app.manifest import digest,manifest
from app import dispatch as dispatch_evidence
from app import store
from app.modules.m1_taps.rules import evaluate as stage1
from app.modules.m2_routes.rules import evaluate as stage2
from app.modules.m3_fares.rules import evaluate as stage3
from app.modules.m4_journeys.rules import evaluate as stage4
from app.modules.m5_discounts.rules import evaluate as stage5
from app.modules.m6_clearing.rules import evaluate as stage6
from app.modules.m7_settlement.rules import evaluate as stage7
STAGES=[stage1,stage2,stage3,stage4,stage5,stage6,stage7]
#: Sample -> its bundled dispatch evidence, if any.
SAMPLES={"dirty.csv":None,"clean.csv":None,"legacy.csv":None,"borrowed.csv":"dispatch.csv"}
def load_sample(name):
    if name not in SAMPLES: raise DomainError("BAD_SAMPLE","样例不存在",404)
    return (ROOT/"sample_data"/name).read_bytes()
def sample_dispatch(name):
    companion=SAMPLES.get(name)
    return (ROOT/"sample_data"/companion).read_bytes() if companion else None
def calculate(raw,params=None,stop=6,dispatch=None):
    params=params or {};started=time.monotonic();context={"parameters":params,"raw":raw,"quarantine":[]}
    supplied=dispatch if dispatch is not None else params.get("dispatch")
    report=dispatch_evidence.load(supplied)
    context["dispatch"]=report
    stages=[];rows=[];dispatch_stage=None
    for index,stage in enumerate(STAGES[:stop+1]):
        result=stage(raw if index==0 else rows,context)
        result=scalar(result);rows=result["rows"]
        context["quarantine"].extend(result.get("quarantine",[]))
        if index==0: context["intake"]=result["metrics"]
        if index==1: dispatch_stage=report
        result["cumulative_quarantine"]=list(context["quarantine"])
        context[MODULES[index][0]]=result
        stages.append(result)
    return {"run_id":digest(raw,params,supplied)[:20],"stages":stages,"manifest":manifest(raw,params,started,supplied),"parameters":params,"dispatch":dispatch_stage}
def execute(raw,params=None,dispatch=None):
    result=calculate(raw,params,dispatch=dispatch);return store.save(result["run_id"],result)
def execute_sample(name,params=None):
    return execute(load_sample(name),params,dispatch=sample_dispatch(name))
def stage_preview(index,payload):
    if "rows" in payload and index>0:
        if not isinstance(payload["rows"],list) or any(not isinstance(row,dict) for row in payload["rows"]): raise DomainError("BAD_ROWS","记录需要对象列表")
        if not isinstance(payload.get("context",{}),dict): raise DomainError("BAD_CONTEXT","上下文需要对象")
        return scalar(STAGES[index](payload["rows"],payload.get("context",{"parameters":{},"quarantine":[]})))
    dispatch=payload.get("dispatch")
    if "csv" in payload and payload["csv"] is not None:
        raw=payload["csv"]
        raw=raw.encode() if isinstance(raw,str) else (_ for _ in ()).throw(DomainError("BAD_CSV","CSV需要文本"))
    else:
        name=payload.get("sample","dirty.csv")
        raw=load_sample(name)
        if dispatch is None and "dispatch" not in payload: dispatch=sample_dispatch(name)
    return calculate(raw,payload.get("parameters",{}),index,dispatch)["stages"][-1]
