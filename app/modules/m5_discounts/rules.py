from decimal import Decimal
from app.values import number,instant,money
from app.errors import DomainError
def _line(row): return row.get("fare_route") or row.get("route")
def _quote(rows,cap,off,window,route_of):
    """Replay the card-day under one line assignment; used only to price the choice."""
    spent={};anchor={};out={}
    for index,row in enumerate(sorted(rows,key=lambda r:(r["card"],instant(r["at"]),r["event_id"]))):
        key=(row["card"],row["business_day"]);base=number(row["base_fare"]);previous=anchor.get(key);eligible=False
        route=route_of(row)
        if previous:
            delta=Decimal(str((instant(row["at"])-instant(previous["at"])).total_seconds()))/60
            eligible=previous["route"]!=route and Decimal(0)<=delta<window
        transfer=min(base,off) if eligible else Decimal(0)
        after_transfer=base-transfer;remaining=max(Decimal(0),cap-spent.get(key,Decimal(0)));charge=min(after_transfer,remaining)
        cap_discount=after_transfer-charge;spent[key]=spent.get(key,Decimal(0))+charge
        out[id(row)]={"transfer_discount":money(transfer),"cap_discount":money(cap_discount),"expected":money(charge)}
        if charge>0:anchor[key]={**row,"route":route}
    return out
def _printed(row): return row.get("printed_route") or row.get("printed_raw") or row.get("route")
def evaluate(rows,context):
    params=context.get("parameters",{});cap=number(params.get("daily_cap","6.00"));off=number(params.get("transfer_discount","1.00"));window=number(params.get("transfer_minutes","60"))
    if cap<0 or off<0 or window<0:raise DomainError("BAD_DISCOUNT","优惠参数不能为负")
    spent={};anchor={};good=[]
    for row in sorted(rows,key=lambda r:(r["card"],instant(r["at"]),r["event_id"])):
        key=(row["card"],row["business_day"]);base=number(row["base_fare"]);previous=anchor.get(key);eligible=False
        if previous:
            delta=Decimal(str((instant(row["at"])-instant(previous["at"])).total_seconds()))/60
            eligible=previous["route"]!=_line(row) and Decimal(0)<=delta<window
        transfer=min(base,off) if eligible else Decimal(0)
        after_transfer=base-transfer;remaining=max(Decimal(0),cap-spent.get(key,Decimal(0)));charge=min(after_transfer,remaining)
        cap_discount=after_transfer-charge;spent[key]=spent.get(key,Decimal(0))+charge
        good.append({**row,"fare_route":_line(row),"transfer_anchor":previous["event_id"] if eligible else "—","transfer_discount":money(transfer),"cap_discount":money(cap_discount),"expected":money(charge),"day_paid":money(spent[key])})
        if charge>0:anchor[key]={**row,"route":_line(row)}
    adopted=_quote(good,cap,off,window,lambda row:_line(row))
    printed=_quote(good,cap,off,window,_printed)
    for row in good:
        mine,other=adopted[id(row)],printed[id(row)]
        row["printed_expected"]=other["expected"]
        row["line_difference"]=money(Decimal(other["expected"])-Decimal(mine["expected"]))
        if _line(row) != _printed(row) and not row.get("line_switch"):
            row["line_note"]="调度线路与打印编码不同（回退或沿用旧版）"
    return {"rows":good,"quarantine":[],"metrics":{"expected_total":money(sum((number(r["expected"]) for r in good),Decimal(0))),"printed_total":money(sum((number(r["printed_expected"]) for r in good),Decimal(0))),"daily_caps":len(spent),"transfer_hits":sum(r["transfer_anchor"]!="—" for r in good),"line_switches":sum(bool(r.get("line_switch")) for r in good),"line_difference":money(sum((number(r["line_difference"]) for r in good),Decimal(0)))}}
