# 深度登记 公交刷卡换乘优惠与日封顶回算

规模：中型。使用者：公交清分中心复核员。核心规则：换乘按上次有效付费行程的时间窗计算，优惠与日封顶按确定顺序裁决并保留分币守恒。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 刷卡采信 | 查看并运行刷卡采信 | `/api/taps` | `app/modules/m1_taps/rules.py` | `tests/test_m1.py` |
| M2 线路换乘 | 查看并运行线路换乘 | `/api/routes` | `app/modules/m2_routes/rules.py` | `tests/test_m2.py` |
| M3 票价版本 | 查看并运行票价版本 | `/api/fares` | `app/modules/m3_fares/rules.py` | `tests/test_m3.py` |
| M4 行程配对 | 查看并运行行程配对 | `/api/journeys` | `app/modules/m4_journeys/rules.py` | `tests/test_m4.py` |
| M5 优惠回算 | 查看并运行优惠回算 | `/api/discounts` | `app/modules/m5_discounts/rules.py` | `tests/test_m5.py` |
| M6 清分对账 | 查看并运行清分对账 | `/api/clearing` | `app/modules/m6_clearing/rules.py` | `tests/test_m6.py` |
| M7 日结归档 | 查看并运行日结归档 | `/api/settlement` | `app/modules/m7_settlement/rules.py` | `tests/test_m7.py` |

调度依据解析与版本裁决在 `app/dispatch.py`（`tests/test_dispatch.py`），归属链路在 `tests/test_line_attribution.py`。

## 陷阱登记

| TRAP | 现象 | 朴素实现 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-01 | 旧编码 | 默认解码失败 | 回退GB18030 | `app/modules/m1_taps/rules.py` | `tests/test_m1.py::test_legacy_encoding_real_sample` |
| TRAP-02 | BOM | 首列名多字符 | utf-8-sig | `app/modules/m1_taps/rules.py` | `tests/test_m1.py::test_bom_real_sample` |
| TRAP-03 | 带引号换行 | 拆成两条 | csv逻辑行 | `app/modules/m1_taps/rules.py` | `tests/test_m1.py::test_quoted_newline_is_one_record` |
| TRAP-05 | 列数不匹配 | 静默错列 | 隔离原行 | `app/modules/m1_taps/rules.py` | `tests/test_m1.py::test_bad_columns_real_sample` |
| TRAP-08 | 前导零ID | 编码变形 | 全程字符串 | `app/modules/m1_taps/rules.py` | `tests/test_m1.py::test_identifier_preserved_real_sample` |
| TRAP-14 | 重复键冲突 | 后写覆盖 | 保留首条并隔离冲突行 | `app/modules/m1_taps/rules.py` | `tests/test_m1.py::test_duplicate_conflict_real_sample` |
| TRAP-18 | 空态三态 | 一律成功 | 分别错误码 | `app/modules/m1_taps/rules.py` | `tests/test_m1.py::test_three_empty_states` |
| TRAP-26 | 旧版本提交 | 覆盖新结果 | 版本条件更新 | `app/store.py` | `tests/test_e2e.py::test_stale_review_409` |
| TRAP-06 | 全角数字 | 转换失败 | NFKC与Decimal | `app/values.py` | `tests/test_m3.py::test_thousands_and_fullwidth` |
| TRAP-07 | 金额哨兵 | 零参与扣费 | 空值隔离 | `app/values.py` | `tests/test_m3.py::test_real_sentinel_quarantined` |
| TRAP-11 | 混合偏移 | 落错版本 | UTC归整 | `app/values.py` | `tests/test_m3.py::test_timezone_equal` |
| TRAP-23 | 换乘截止点 | 重复优惠 | 截止点排除 | `app/modules/m5_discounts/rules.py` | `tests/test_m5.py::test_exact_window_excluded` |
| TRAP-25 | 票价重叠 | 随意取版 | 冲突隔离 | `app/modules/m3_fares/rules.py` | `tests/test_m3.py::test_overlap_rejected` |
| TRAP-27 | 借车后打印编码随车辆变 | 按打印编码判跨线，多减一元 | 调度任务覆盖时以任务线路裁决 | `app/modules/m2_routes/rules.py`、`app/dispatch.py` | `tests/test_line_attribution.py::test_real_cross_line_after_borrow_keeps_discount` |
| TRAP-28 | 一律按原线路归并 | 真实换线的接续漏掉优惠 | 任务换线后接续按新线路判跨线 | `app/modules/m2_routes/rules.py` | `tests/test_line_attribution.py::test_genuine_cross_line_after_reassignment_is_not_lost` |
| TRAP-29 | 两套换乘/封顶结果 | 打印与调度各算一遍，重复减免 | 每卡日只保留采用线路的一套 | `app/modules/m5_discounts/rules.py`、`app/modules/m7_settlement/rules.py` | `tests/test_line_attribution.py::test_each_card_day_keeps_exactly_one_result_set` |
| TRAP-30 | 同任务重试 | 重复归属，多出版本 | 完全相同归属计重试不新增版本 | `app/dispatch.py` | `tests/test_dispatch.py::test_identical_assignment_is_retry_not_new_version` |
| TRAP-31 | 任务切换失败 | 覆盖旧版，线路不可读 | 冲突行隔离并保留可读旧版 | `app/dispatch.py` | `tests/test_dispatch.py::test_overlapping_switch_fails_and_keeps_readable_old_version` |
| TRAP-32 | 来源行未有着落 | 静默丢弃后封存 | 逐行处置且 gaps 非零拒绝日结 | `app/dispatch.py`、`app/modules/m7_settlement/rules.py` | `tests/test_line_attribution.py::test_settlement_blocks_when_source_lines_unaccounted` |
| TRAP-33 | 原始依据被删 | 只留派生结果 | 刷卡与调度 `_raw`、来源行、双摘要全保留 | `app/modules/m7_settlement/rules.py`、`app/archive.py` | `tests/test_line_attribution.py::test_original_taps_and_dispatch_evidence_kept` |
| TRAP-34 | 同任务修订时段 | 视为冲突丢弃新版 | 同线新版本覆盖并留档旧行 | `app/dispatch.py` | `tests/test_dispatch.py::test_same_line_window_revision_supersedes_without_new_line_version` |

## 对账规则

输入原始逻辑行=最终采纳来源行+隔离来源行+重复行+空白行+分段表头。派生记录用_sources保存完整来源，因此分组不丢行。业务预期合计与上游申报合计之差等于逐行差异之和。结果按输入摘要、调度摘要、规则版本及参数产生唯一批次，事务写入；同源重跑只复用已有批次。

调度依据单独对账：调度输入行=调度采纳行+调度重试行+调度隔离行+调度空白行+同任务同线覆盖行，`dispositions` 逐行留痕，`gaps` 必须为0。刷卡对账增加 `dispatch_balanced`；任一侧未对平即 `balanced` 为假，M7拒绝封存。调度采用不代表删除打印编码：`printed_route` 与 `_raw` 均保留。

## 裁决说明

临时任务期间的票务线路以调度任务认定，车载机编码只作证据与回退。理由：打印编码随车辆任务漂移，按它判跨线会把同线接续误判为跨线并多减一元；而坚持按原线路归并又会让真实换线后的接续漏掉优惠。以任务为准可从调度依据复现，且回退原因逐行可审计。

## 已知不覆盖

4MB以上文件需预先按业务键分批；不模拟生产支付与外部回调。人工复核只变更批次状态，不改写原始记录。
