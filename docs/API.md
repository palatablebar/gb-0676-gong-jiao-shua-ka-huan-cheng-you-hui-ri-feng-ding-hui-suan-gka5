# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存。每个阶段返回rows、quarantine、metrics；后续阶段还返回累计隔离。/api/upload接收multipart文件file，可选dispatch字段（调度依据CSV文本）。/api/runs/<id>/archive只导出一份带清单与证据的CSV。

## 调度依据

`POST /api/runs` 可传 `dispatch`：调度依据CSV文本、调度记录对象列表或省略。省略且使用仓内样例时，借车样例自动带出 `sample_data/dispatch.csv`；上传刷卡时以multipart `dispatch` 字段传入。`GET /api/runs/<id>` 的 `dispatch` 含 `rows`、`quarantine`、`dispositions`、`switch_failures` 与 `metrics`。每条调度输入行在 `dispositions` 中恰有一项处置（accepted/retry/quarantine/blank），`metrics.gaps` 必须为0才能日结。

## 线路归属

M2返回 `printed_route`（车载打印）、`task_route`（调度任务线路）、`fare_route`（采用的票务线路）、`line_source`（dispatch/dispatch-vehicle/dispatch-retained 或回退原因）、`line_switch`、`line_note`、`task_switch`。M5按 `fare_route` 计算换乘与封顶，并给出 `printed_expected` 与 `line_difference` 供复核；每卡日只产出一套结果。
