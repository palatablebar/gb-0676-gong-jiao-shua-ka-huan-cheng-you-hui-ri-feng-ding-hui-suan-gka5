import csv,io,json
def _meta(row):
    return json.dumps(row,ensure_ascii=False)
def build_archive(run):
    stream=io.StringIO(newline="");writer=csv.writer(stream)
    writer.writerow(["run_id","input_sha256","rule_version","kind","source_lines","reason","evidence","dispatch_sha256"])
    meta=run["manifest"];sha=meta.get("dispatch_sha256") or ""
    dispatch=run.get("dispatch") or {}
    def emit(kind,sources,reason,row):
        writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],kind,json.dumps(sources),reason,_meta(row),sha])
    for row in run["stages"][-1]["rows"]:
        emit("accepted",row.get("_sources",[]),row.get("status",""),row)
    for row in run["stages"][-1].get("cumulative_quarantine",[]):
        emit("quarantine",row.get("_sources",[]),row.get("reason",""),row)
    for row in dispatch.get("rows",[]):
        emit("dispatch",row.get("_sources",[]),row.get("task_id",""),row)
    for row in dispatch.get("quarantine",[]):
        emit("dispatch-quarantine",row.get("_sources",[]),row.get("reason",""),row)
    for row in dispatch.get("superseded_rows",[]):
        emit("dispatch-superseded",row.get("_sources",[]),"同任务同线新版本覆盖",row)
    for item in dispatch.get("dispositions",[]):
        if item.get("kind") in ("retry","blank"):
            reason="重试不新增线路归属" if item["kind"]=="retry" else "空白调度行"
            emit("dispatch-"+item["kind"],[f"dispatch:{item['line']}"],reason,{"line":item["line"],"kind":item["kind"]})
    return "﻿"+stream.getvalue()
