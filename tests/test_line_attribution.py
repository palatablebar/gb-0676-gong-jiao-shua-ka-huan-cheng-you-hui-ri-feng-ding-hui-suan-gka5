"""临时改道/跨线借车：调度任务 vs 车载打印编码的票务线路裁决。"""
import csv
import io

import pytest

from app.errors import DomainError
from app.modules.m2_routes.rules import evaluate as attribute
from app.modules.m5_discounts.rules import evaluate as discount
from app.modules.m7_settlement.rules import evaluate as settle
from app.pipeline import calculate, load_sample, sample_dispatch

TAPS = """event_id,card,route,event_time,result,reported,note,vehicle,task_id
1001,0001,01,2026-11-16T08:00:00+08:00,success,2.50,首程,V1,T1
1002,0001,01,2026-11-16T08:10:00+08:00,success,2.50,接续,V1,T2
"""
DISPATCH = """task_id,vehicle,route,start,end
T1,V1,01,2026-11-16T07:00:00+08:00,2026-11-16T08:05:00+08:00
T2,V1,02,2026-11-16T08:05:00+08:00,2026-11-16T12:00:00+08:00
"""


def run(taps=TAPS, dispatch=DISPATCH):
    return calculate(taps.encode(), {}, dispatch=dispatch)


def test_task_line_wins_over_stale_printed_code():
    rows = run()["stages"][1]["rows"]
    assert [row["printed_route"] for row in rows] == ["01", "01"]
    assert [row["fare_route"] for row in rows] == ["01", "02"]
    assert rows[1]["line_source"] == "dispatch" and rows[1]["line_switch"] is True
    assert rows[1]["line_note"] == "任务改道，采用调度线路"


def test_real_cross_line_after_borrow_keeps_discount():
    "车载机换了线路编码但任务仍是原线：不能再多减一元。"
    taps = """event_id,card,route,event_time,result,reported,note,vehicle,task_id
1001,0001,01,2026-11-16T08:00:00+08:00,success,2.50,首程,V1,T1
1002,0001,02,2026-11-16T08:20:00+08:00,success,2.50,借车打印02,V1,T1
"""
    dispatch = "task_id,vehicle,route,start,end\nT1,V1,01,2026-11-16T07:00:00+08:00,2026-11-16T12:00:00+08:00\n"
    rows = run(taps, dispatch)["stages"][4]["rows"]
    assert rows[1]["fare_route"] == "01"
    assert rows[1]["transfer_discount"] == "0.00" and rows[1]["expected"] == "2.50"
    assert rows[1]["printed_expected"] == "1.50" and rows[1]["line_difference"] == "-1.00"


def test_genuine_cross_line_after_reassignment_is_not_lost():
    "任务真的换线后，接续应算跨线优惠，而不是按旧编码归并。"
    taps = """event_id,card,route,event_time,result,reported,note,vehicle,task_id
1001,0001,01,2026-11-16T08:00:00+08:00,success,2.50,首程,V1,T1
1002,0001,01,2026-11-16T08:20:00+08:00,success,2.50,任务已换线,V1,T2
"""
    dispatch = """task_id,vehicle,route,start,end
T1,V1,01,2026-11-16T07:00:00+08:00,2026-11-16T08:10:00+08:00
T2,V1,02,2026-11-16T08:10:00+08:00,2026-11-16T12:00:00+08:00
"""
    rows = run(taps, dispatch)["stages"][4]["rows"]
    assert rows[1]["fare_route"] == "02" and rows[1]["line_switch"] is True
    assert rows[1]["transfer_anchor"] == "1001" and rows[1]["expected"] == "1.50"


def test_each_card_day_keeps_exactly_one_result_set():
    "票务结果只按采用的线路生成一套，不能同时保留打印编码与调度线路两套链。"
    rows = run()["stages"][4]["rows"]
    assert len(rows) == len({(row["card"], row["business_day"], row["event_id"]) for row in rows})
    assert len({(row["card"], row["business_day"]) for row in rows}) == 1
    anchors = [row["transfer_anchor"] for row in rows if row["transfer_anchor"] != "—"]
    assert all(anchor in {row["event_id"] for row in rows} for anchor in anchors)
    assert "printed_transfer_discount" not in rows[0]


def test_fallback_without_dispatch_uses_printed_code_with_reason():
    report = calculate(TAPS.encode(), {})
    rows = report["stages"][1]["rows"]
    assert {row["line_source"] for row in rows} == {"NO_DISPATCH"}
    assert {row["fare_route"] for row in rows} == {"01"}
    assert report["stages"][4]["metrics"]["printed_total"] == report["stages"][4]["metrics"]["expected_total"]


def test_unknown_task_falls_back_with_reason():
    taps = TAPS.replace("V1,T1\n", "V9,T9\n").replace("V1,T2\n", "V9,T9\n")
    rows = run(taps)["stages"][1]["rows"]
    assert {row["line_source"] for row in rows} == {"UNKNOWN_TASK"}
    assert all("任务未登记" in row["line_note"] for row in rows)


def test_failed_switch_keeps_readable_old_version():
    dispatch = """task_id,vehicle,route,start,end
T1,V1,01,2026-11-16T07:00:00+08:00,2026-11-16T12:00:00+08:00
T1,V1,02,2026-11-16T09:00:00+08:00,2026-11-16T10:00:00+08:00
"""
    report = run(TAPS, dispatch)
    rows = report["stages"][1]["rows"]
    first = next(row for row in rows if row["event_id"] == "1001")
    assert first["fare_route"] == "01"
    assert first["task_switch"] == "失败，保留旧版" and first["task_switch_reason"] == "DISPATCH_CONFLICT"
    assert {row["fare_route"] for row in rows} == {"01"}
    assert report["dispatch"]["metrics"]["accepted"] == 1
    assert report["dispatch"]["switch_failures"][0]["route"] == "02"


def test_sample_borrowed_has_dispatch_evidence_in_archive(client):
    payload = client.post("/api/runs", json={"sample": "borrowed.csv"}).get_json()
    assert payload["dispatch"]["provided"] is True
    assert payload["dispatch"]["metrics"]["retries"] == 1
    assert payload["stages"][5]["metrics"]["dispatch_balanced"] is True
    archive = client.get("/api/runs/" + payload["run_id"] + "/archive")
    rows = list(csv.reader(io.StringIO(archive.data.decode("utf-8-sig"))))
    kinds = {row[3] for row in rows[1:]}
    assert {"dispatch", "dispatch-retry", "dispatch-quarantine"} & kinds
    assert rows[0][7] == "dispatch_sha256"


def test_settlement_blocks_when_source_lines_unaccounted():
    rows = run()["stages"][6]["rows"]
    with pytest.raises(DomainError) as error:
        settle(rows, {"dispatch": {"metrics": {"input": 3, "accepted": 1, "retries": 0, "quarantine": 1, "blank": 0, "gaps": 1}}})
    assert error.value.code == "UNBALANCED_DISPATCH"


def test_attribution_does_not_invent_task_versions():
    rows = run()["stages"][1]["rows"]
    assert run()["stages"][1]["metrics"]["task_versions"] == 2
    rerun = run(TAPS + TAPS, DISPATCH + DISPATCH)
    assert rerun["stages"][1]["metrics"]["task_versions"] == 2
    assert rerun["dispatch"]["metrics"]["retries"] == 2


def test_original_taps_and_dispatch_evidence_kept():
    report = run()
    stage = report["stages"][5]
    assert all(row["_raw"] for row in stage["rows"])
    assert all(row["_sources"] for row in stage["rows"])
    assert report["dispatch"]["rows"] and all(row["_raw"] for row in report["dispatch"]["rows"])
    assert report["manifest"]["input_sha256"] and report["manifest"]["dispatch_sha256"]


def test_discount_quote_is_bounded_to_own_journey():
    rows = run()["stages"][4]["rows"]
    assert all(row["printed_expected"] for row in rows)
    assert sum(int(row["line_difference"] != "0.00") for row in rows) <= len(rows)


def test_unregistered_printed_code_still_uses_valid_task():
    taps = TAPS.replace("1002,0001,01,", "1002,0001,99,")
    rows = run(taps)["stages"][1]["rows"]
    second = next(row for row in rows if row["event_id"] == "1002")
    assert second["printed_raw"] == "99" and second["fare_route"] == "02"
    assert second["printed_route"] is None
    assert second["line_note"] == "打印编码未登记，采用调度线路"


def test_unregistered_printed_code_quarantined_without_task():
    taps = TAPS.replace("1002,0001,01,2026-11-16T08:10:00+08:00,success,2.50,接续,V1,T2",
                        "1002,0001,99,2026-11-16T08:10:00+08:00,success,2.50,接续,V1,T2")
    report = run(taps, dispatch="task_id,vehicle,route,start,end\n")
    assert any(row["reason"] == "UNKNOWN_ROUTE" for row in report["stages"][1]["quarantine"])


def test_sample_dispatch_is_bundled():
    assert sample_dispatch("borrowed.csv")
    assert sample_dispatch("dirty.csv") is None
    assert load_sample("borrowed.csv").startswith(b"event_id")
