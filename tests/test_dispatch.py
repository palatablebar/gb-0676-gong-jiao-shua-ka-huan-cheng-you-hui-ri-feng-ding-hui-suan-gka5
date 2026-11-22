import pytest
from app import dispatch
from app.dispatch import load, index_of, select
from app.errors import DomainError


def ev(*rows):
    return "task_id,vehicle,route,start,end\n" + "".join(",".join(row) + "\n" for row in rows)


def test_identical_assignment_is_retry_not_new_version():
    row = ("T1", "V1", "01", "2026-11-16T08:00:00+08:00", "2026-11-16T10:00:00+08:00")
    report = load(ev(row, row))
    assert report["metrics"]["accepted"] == 1 and report["metrics"]["retries"] == 1
    assert [d["kind"] for d in report["dispositions"]] == ["accepted", "retry"]


def test_overlapping_switch_fails_and_keeps_readable_old_version():
    report = load(ev(
        ("T1", "V1", "01", "2026-11-16T08:00:00+08:00", "2026-11-16T12:00:00+08:00"),
        ("T1", "V1", "02", "2026-11-16T09:00:00+08:00", "2026-11-16T10:00:00+08:00"),
    ))
    assert report["metrics"]["accepted"] == 1
    assert [row["route"] for row in report["rows"]] == ["01"]
    assert report["quarantine"][0]["reason"] == "DISPATCH_CONFLICT"
    assert report["switch_failures"][0]["route"] == "02"


def test_every_dispatch_input_line_has_one_disposition():
    report = load(ev(
        ("T1", "V1", "01", "2026-11-16T08:00:00+08:00", "2026-11-16T09:00:00+08:00"),
        ("T1", "V1", "01", "2026-11-16T08:00:00+08:00", "2026-11-16T09:00:00+08:00"),
        ("T2", "V2", "99", "2026-11-16T08:00:00+08:00", "2026-11-16T09:00:00+08:00"),
        ("T3", "V2", "01", "2026-11-16T10:00:00+08:00", "2026-11-16T09:00:00+08:00"),
    ) + "\n")
    metrics = report["metrics"]
    assert metrics["input"] == 5 and metrics["gaps"] == 0
    assert metrics["accepted"] + metrics["retries"] + metrics["quarantine"] + metrics["blank"] == metrics["input"]
    assert len({item["line"] for item in report["dispositions"]}) == metrics["input"]


def test_blank_dispatch_line_is_counted():
    report = load("task_id,vehicle,route,start,end\nT1,V1,01,2026-11-16T08:00:00+08:00,2026-11-16T09:00:00+08:00\n\n")
    assert report["metrics"]["blank"] == 1 and report["metrics"]["gaps"] == 0


def test_bad_dispatch_header_raises():
    with pytest.raises(DomainError) as error:
        load("a,b,c\n1,2,3\n")
    assert error.value.code == "BAD_DISPATCH_HEADER"


def test_no_dispatch_supplied_is_reported_not_invented():
    report = load(None)
    assert report["provided"] is False and report["metrics"]["input"] == 0


def test_same_line_window_revision_supersedes_without_new_line_version():
    report = load(ev(
        ("T1", "V1", "01", "2026-11-16T08:00:00+08:00", "2026-11-16T09:00:00+08:00"),
        ("T1", "V1", "01", "2026-11-16T08:00:00+08:00", "2026-11-16T10:00:00+08:00"),
    ))
    assert [row["end"] for row in report["rows"]] == ["2026-11-16T02:00:00+00:00"]
    assert report["metrics"]["superseded"] == 1 and report["metrics"]["gaps"] == 0
    assert report["superseded_rows"][0]["end"] == "2026-11-16T01:00:00+00:00"
    assert {row["route"] for row in report["rows"]} == {"01"}


def test_select_requires_covering_task():
    report = load(ev(("T1", "V1", "01", "2026-11-16T08:00:00+08:00", "2026-11-16T09:00:00+08:00")))
    index = index_of(report)
    from app.values import instant
    assert select(index, "T1", "V1", instant("2026-11-16T08:30:00+08:00"))[1] == "dispatch"
    assert select(index, "T1", "V1", instant("2026-11-16T09:00:00+08:00"))[1] == "NO_COVERAGE"
    assert select(index, "T2", "V1", instant("2026-11-16T08:30:00+08:00"))[1] == "UNKNOWN_TASK"
    assert select(index, "T1", "V2", instant("2026-11-16T08:30:00+08:00"))[1] == "VEHICLE_MISMATCH"
    assert select(index, "", "V1", instant("2026-11-16T08:30:00+08:00"))[1] == "NO_TASK"
