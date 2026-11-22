"""Line attribution: dispatch task first, onboard printed code as fallback.

Every tap keeps the code its onboard machine printed.  The fare line used for
transfer/cap decisions is the dispatch assignment when one validly covers the
tap, otherwise the printed code.  The reason is recorded so reviewers can see
why a line was adopted and how the discount would have differed.
"""
from app import dispatch as dispatch_evidence
from app.lines import normalize_route
from app.reasons import reject
from app.values import instant

FALLBACK_REASONS = {"NO_TASK", "NO_DISPATCH", "UNKNOWN_TASK", "NO_COVERAGE", "VEHICLE_MISMATCH", "AMBIGUOUS_TASK"}
NOTES = {
    "NO_DISPATCH": "未提供调度依据，采用打印编码",
    "NO_TASK": "刷卡无任务号，采用打印编码",
    "UNKNOWN_TASK": "任务未登记，采用打印编码",
    "NO_COVERAGE": "任务时段未覆盖本次刷卡，采用打印编码",
    "VEHICLE_MISMATCH": "车辆与任务不符，采用打印编码",
    "AMBIGUOUS_TASK": "任务不唯一，采用打印编码",
}


def evaluate(rows, context):
    report = dispatch_evidence.report_of(context.get("dispatch"))
    index = dispatch_evidence.index_of(report)
    swaps = {failure["task_id"]: failure for failure in report.get("switch_failures", [])}
    good = []
    bad = []
    for row in rows:
        printed = normalize_route(row.get("route"))
        if not row.get("card"):
            bad.append(reject(row, "EMPTY_CARD", "卡号为空"))
            continue
        try:
            at = instant(row.get("at") or row.get("event_time")) if report["provided"] else None
        except Exception as error:  # DomainError from values.instant
            bad.append(reject(row, getattr(error, "code", "INVALID_TIME"), str(error)))
            continue
        task = str(row.get("task_id") or "").strip()
        vehicle = str(row.get("vehicle") or "").strip()
        if not report["provided"]:
            assignment, source = None, "NO_DISPATCH"
        else:
            assignment, source = dispatch_evidence.select(index, task, vehicle, at)
        if assignment is not None:
            fare_route = assignment["route"]
        else:
            fare_route = printed
        if not fare_route:
            bad.append(reject(row, "UNKNOWN_ROUTE", "线路未登记"))
            continue
        adopted = {**row, "route": printed, "printed_route": printed, "printed_raw": row.get("route"), "fare_route": fare_route, "line_source": source, "line_group": "city"}
        if assignment is not None:
            adopted.update(task_route=assignment["route"], task_start=assignment["start"], task_end=assignment.get("end"))
            adopted["line_switch"] = assignment["route"] != printed
            if adopted["line_switch"]:
                adopted["line_note"] = "任务改道，采用调度线路"
            elif source == "dispatch-retained":
                adopted["line_note"] = "任务切换失败，沿用可读旧版线路"
            else:
                adopted["line_note"] = "任务与打印一致"
            if not printed:
                adopted["line_note"] = "打印编码未登记，采用调度线路"
        else:
            adopted.update(task_route="", task_start="", task_end="")
            adopted["line_switch"] = False
            adopted["line_note"] = NOTES.get(source, "任务不唯一，采用打印编码")
        failed = swaps.get(task)
        if failed is not None:
            adopted["task_switch"] = "失败，保留旧版"
            adopted["task_switch_reason"] = failed["reason"]
        else:
            adopted["task_switch"] = "现行" if assignment is not None else "—"
            adopted["task_switch_reason"] = ""
        good.append(adopted)
    fallbacks = sum(row["line_source"] in FALLBACK_REASONS for row in good)
    task_versions = sum(len(group) for group in index["tasks"].values())
    return {
        "rows": good,
        "quarantine": bad,
        "metrics": {
            "routes": len(set(row["fare_route"] for row in good)),
            "printed_routes": len(set(row["printed_route"] for row in good)),
            "accepted": len(good),
            "dispatch_used": sum(row["line_source"] in {"dispatch", "dispatch-retained"} for row in good),
            "printed_fallback": fallbacks,
            "line_switches": sum(row["line_switch"] for row in good),
            "task_versions": task_versions,
        },
    }
