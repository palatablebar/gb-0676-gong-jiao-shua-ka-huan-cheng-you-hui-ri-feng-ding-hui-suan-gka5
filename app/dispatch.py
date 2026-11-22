"""Dispatch-task evidence: the authoritative source for the fare line.

A vehicle may print a line code that follows the vehicle's *task*, so a borrowed
or re-routed vehicle can print one line for part of the day while the fare
system keeps billing another.  Each dispatch assignment is a versioned claim
(task_id, vehicle, route, [start, end)).  The dispatch task decides the fare
line while a tap is covered by a valid assignment; the onboard printed code is
kept beside it as evidence and is only used when dispatch evidence cannot
decide (no schedule at all, no task on the tap, uncovered time, vehicle
mismatch).

Lineage rules:
* an identical assignment retried for the same task is a retry, not a new
  attribution version;
* an overlapping but different assignment for the same task (or the same
  vehicle) fails the switch: the earlier readable version is retained and the
  failed line is quarantined;
* every dispatch input line ends in exactly one disposition (accepted, retry,
  quarantine or blank) so settlement can prove nothing was silently dropped.
"""
import csv
import io

from app.errors import DomainError
from app.lines import normalize_route
from app.reasons import reject
from app.values import instant

COLUMNS = ["task_id", "vehicle", "route", "start", "end"]


def decode(raw):
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DomainError("ENCODING", "无法识别调度依据编码")


def _rows_from_csv(text):
    stream = csv.reader(io.StringIO(text, newline=""))
    header = next(stream, None)
    if header != COLUMNS:
        raise DomainError("BAD_DISPATCH_HEADER", "调度依据表头不匹配")
    rows = []
    malformed = []
    for cells in stream:
        line = stream.line_num
        row = {"_line": line, "_sources": [f"dispatch:{line}"], "_raw": cells}
        if not cells or not any(c.strip() for c in cells):
            rows.append({**row, "_blank": True})
            continue
        if len(cells) != len(header):
            malformed.append(reject(row, "BAD_COLUMNS", "调度行列数不匹配"))
            continue
        row.update({key: value.strip() for key, value in zip(header, cells)})
        rows.append(row)
    return rows, malformed


def _normalize(source):
    if source is None:
        return None, []
    if isinstance(source, str) and not source.strip():
        return None, []
    if isinstance(source, bytes):
        if not source.strip():
            return None, []
        source = decode(source)
    if isinstance(source, str):
        return _rows_from_csv(source)
    if isinstance(source, (list, tuple)):
        if not source:
            return None, []
        rows = []
        for index, item in enumerate(source, 2):
            if not isinstance(item, dict):
                raise DomainError("BAD_DISPATCH", "调度依据记录需要对象")
            line = item.get("_line", index)
            rows.append({**item, "_line": line, "_sources": [f"dispatch:{line}"], "_raw": item.get("_raw", item)})
        return rows, []
    raise DomainError("BAD_DISPATCH", "调度依据需要CSV文本或记录列表")


def _prepare(row):
    if row.get("_blank"):
        return None, "blank"
    try:
        task = str(row.get("task_id") or "").strip()
        if not task:
            return reject(row, "EMPTY_VALUE", "任务号为空"), "quarantine"
        route = normalize_route(row.get("route"))
        if not route:
            return reject(row, "UNKNOWN_ROUTE", "调度线路未登记"), "quarantine"
        start = instant(row.get("start"))
        end_text = str(row.get("end") or "").strip()
        end = instant(end_text) if end_text else None
        if end is not None and end <= start:
            return reject(row, "INVALID_WINDOW", "调度结束须晚于开始"), "quarantine"
    except DomainError as error:
        return reject(row, error.code, str(error)), "quarantine"
    version = {
        **row,
        "task_id": task,
        "vehicle": str(row.get("vehicle") or "").strip(),
        "printed_route": row.get("route"),
        "route": route,
        "start": start.isoformat(),
        "end": end.isoformat() if end else None,
    }
    return version, "ok"


def _overlap(left, right):
    left_end, right_end = left["_end"], right["_end"]
    if right_end is not None and left["_start"] >= right_end:
        return False
    if left_end is not None and right["_start"] >= left_end:
        return False
    return True


def load(source):
    """Parse and validate dispatch evidence, returning one report."""
    records, malformed = _normalize(source)
    report = {
        "provided": records is not None,
        "rows": [],
        "quarantine": [],
        "dispositions": [],
        "switch_failures": [],
        "superseded_rows": [],
        "metrics": {"input": 0, "accepted": 0, "retries": 0, "quarantine": 0, "blank": 0, "tasks": 0, "gaps": 0},
    }
    if records is None:
        return report
    report["metrics"]["input"] = len(records) + len(malformed)
    for error in malformed:
        report["quarantine"].append(error)
        report["dispositions"].append({"line": error["_line"], "kind": "quarantine", "reason": error["reason"], "raw": error.get("_raw")})
    versions = {}
    vehicles = {}
    signatures = set()
    for row in records:
        line = row["_line"]
        prepared, kind = _prepare(row)
        if kind == "blank":
            report["metrics"]["blank"] += 1
            report["dispositions"].append({"line": line, "kind": "blank", "raw": row.get("_raw")})
            continue
        if kind == "quarantine":
            report["quarantine"].append(prepared)
            report["dispositions"].append({"line": line, "kind": "quarantine", "reason": prepared["reason"], "raw": row.get("_raw")})
            continue
        signature = (prepared["task_id"], prepared["vehicle"], prepared["route"], prepared["start"], prepared["end"])
        if signature in signatures:
            report["metrics"]["retries"] += 1
            report["dispositions"].append({"line": line, "kind": "retry", "raw": row.get("_raw")})
            continue
        signatures.add(signature)
        candidate = {**prepared, "_start": instant(prepared["start"]), "_end": instant(prepared["end"]) if prepared["end"] else None}
        task_conflicts = [other for other in versions.get(prepared["task_id"], []) if _overlap(candidate, other)]
        vehicle_conflicts = [
            other for other in vehicles.get(prepared["vehicle"], [])
            if prepared["vehicle"] and _overlap(candidate, other) and other["task_id"] != prepared["task_id"]
        ]
        if task_conflicts and not vehicle_conflicts and all(other["route"] == candidate["route"] for other in task_conflicts):
            # Same task, same line, revised window: the new version supersedes the
            # old one.  Line attribution does not change, the old version stops
            # being active, and its raw row is kept as evidence.
            for other in task_conflicts:
                versions[prepared["task_id"]].remove(other)
                if other["vehicle"] and other in vehicles.get(other["vehicle"], []):
                    vehicles[other["vehicle"]].remove(other)
                for row_index, old in enumerate(report["rows"]):
                    if old["_line"] == other["_line"]:
                        report["superseded_rows"].append({**old, "_superseded": True})
                        del report["rows"][row_index]
                        break
                for item in report["dispositions"]:
                    if item["line"] == other["_line"]:
                        item["kind"] = "superseded"
                        item["reason"] = "同任务同线新版本覆盖"
            report["metrics"]["superseded"] = len(task_conflicts)
        elif task_conflicts or vehicle_conflicts:
            reason = "DISPATCH_CONFLICT" if task_conflicts else "VEHICLE_CONFLICT"
            conflict = reject(prepared, reason, "同一任务或车辆时段重叠，保留旧版")
            report["quarantine"].append(conflict)
            report["switch_failures"].append({**conflict, "task_id": prepared["task_id"], "vehicle": prepared["vehicle"], "route": prepared["route"], "start": prepared["start"], "end": prepared["end"]})
            report["dispositions"].append({"line": line, "kind": "quarantine", "reason": reason, "raw": row.get("_raw")})
            continue
        versions.setdefault(prepared["task_id"], []).append(candidate)
        if prepared["vehicle"]:
            vehicles.setdefault(prepared["vehicle"], []).append(candidate)
        report["rows"].append(prepared)
        report["dispositions"].append({"line": line, "kind": "accepted", "raw": row.get("_raw")})
    metrics=report["metrics"]
    if "superseded" not in metrics: metrics["superseded"] = 0
    metrics.update(
        accepted=len(report["rows"]),
        quarantine=len(report["quarantine"]),
        tasks=len(versions),
    )
    lines = {row["_line"] for row in records} | {error["_line"] for error in malformed}
    metrics["input"] = len(lines)
    metrics["gaps"] = len(lines - {item["line"] for item in report["dispositions"]})
    report["versions"] = {
        task: [{key: version[key] for key in ("task_id", "vehicle", "printed_route", "route", "start", "end", "_line")} for version in group]
        for task, group in versions.items()
    }
    return report


def report_of(value):
    """Return a dispatch report for whatever the caller supplied."""
    if isinstance(value, dict) and "dispositions" in value and "metrics" in value:
        return value
    return load(value)


def select(index, task_id, vehicle, at):
    """Pick the assignment covering this tap, or say why printed code wins.

    A failed task switch never removes the earlier readable version: the
    conflicting line is quarantined and the retained version stays in ``rows``.
    A tap naming that task (or naming no registered task at all) is resolved
    from the vehicle's retained assignment, so the old line keeps applying
    until a valid switch exists.
    """
    if task_id and task_id in index["tasks"]:
        covering = [version for version in index["tasks"][task_id] if covers(version, at)]
        if not covering:
            return None, "NO_COVERAGE"
        for version in covering:
            if not version.get("vehicle") or not vehicle or version["vehicle"] == vehicle:
                return version, "dispatch"
        return None, "VEHICLE_MISMATCH"
    if vehicle and task_id in index["failures"]:
        retained = [version for version in index["vehicles"].get(vehicle, []) if covers(version, at)]
        if retained:
            if len({version["task_id"] for version in retained}) == 1:
                return retained[0], "dispatch-retained"
            return None, "AMBIGUOUS_TASK"
    if not task_id:
        return None, "NO_TASK"
    return None, "UNKNOWN_TASK"


def covers(version, at):
    """One half-open [start, end) window; an empty end means still open."""
    return instant(version["start"]) <= at and (not version.get("end") or at < instant(version["end"]))


def index_of(report):
    """Build the lookup used by select(), tolerating an already-built report."""
    tasks = {}
    vehicles = {}
    for version in report.get("rows", []):
        tasks.setdefault(version["task_id"], []).append(version)
        if version.get("vehicle"):
            vehicles.setdefault(version["vehicle"], []).append(version)
    failures = {failure["task_id"]: failure for failure in report.get("switch_failures", []) if failure.get("task_id")}
    return {"tasks": tasks, "vehicles": vehicles, "failures": failures}
