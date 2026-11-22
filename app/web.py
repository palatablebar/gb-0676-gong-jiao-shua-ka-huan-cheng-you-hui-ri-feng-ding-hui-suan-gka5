from flask import render_template
from app.config import MODULES,TITLE,SHORT
from app.pipeline import execute_sample
from app import store
COLUMNS=[
    ['event_id','card','route','event_time','result','reported'],
    ['event_id','card','task_id','vehicle','printed_route','task_route','fare_route','line_source','task_switch','line_note'],
    ['event_id','card','route','printed_route','fare_route','line_source','fare_version','base_fare','reported','at'],
    ['journey','card','task_id','vehicle','printed_route','fare_route','line_source','task_switch','business_day','at'],
    ['event_id','card','task_id','vehicle','printed_route','fare_route','line_source','transfer_anchor','transfer_discount','cap_discount','expected','printed_expected','line_difference','day_paid'],
    ['event_id','card','expected','reported','difference','status'],
    ['event_id','card','expected','reported','status'],
]
LABELS={'event_id':'事件','card':'卡号','route':'打印线路','event_time':'刷卡时间','result':'刷卡状态','reported':'实扣 / 元','line_group':'线路组','fare_version':'票价版','base_fare':'基础票价','at':'事件时间 UTC','journey':'行程编号','business_day':'业务日','transfer_anchor':'换乘锚点','transfer_discount':'换乘优惠','cap_discount':'封顶减免','expected':'应扣 / 元','day_paid':'日累计','difference':'差额 / 元','status':'结论','accepted':'采纳行','versions':'版本','expected_total':'应扣总额','daily_caps':'卡日数量','transfer_hits':'换乘次数','input':'输入行','quarantine':'隔离行','duplicate':'重复行','blank':'空白行','repeated_headers':'重复表头','encoding':'编码','routes':'票务线路数','cards':'卡数','journeys':'行程数','records':'记录数','source_lines':'来源行数','sha256':'摘要','ready':'可归档','differences':'差异项',
    'vehicle':'车辆','task_id':'任务','printed_route':'车载打印编码','task_route':'任务线路','fare_route':'票务线路','line_source':'线路依据','line_note':'归属说明','line_switch':'改道','task_switch':'任务切换','task_switch_reason':'切换失败原因','printed_expected':'按打印编码应扣 / 元','line_difference':'线路差异 / 元','dispatch_used':'采用调度任务','printed_fallback':'回退打印编码','line_switches':'改道行程数','task_versions':'任务版本数','printed_routes':'打印编码数',
    'accepted_inputs':'采纳来源行','quarantine_inputs':'隔离来源行','output_records':'结果记录','excluded':'排除行','balanced':'行数平衡','expected_total':'预期合计','reported_total':'申报合计','dispatch_input':'调度输入行','dispatch_accepted':'调度采纳行','dispatch_retries':'调度重试行','dispatch_quarantine':'调度隔离行','dispatch_blank':'调度空白行','dispatch_gaps':'调度未着落行','dispatch_superseded':'调度覆盖行','dispatch_balanced':'调度行数平衡','dispatch_lines':'调度来源行','card_days':'卡日数','chains':'换乘链数','printed_total':'按打印编码合计','line_difference':'线路差异合计','blank':'空行','repeated_headers':'分段表头','duplicate':'重复行','sha256':'校验摘要'}
def register_pages(app):
    def page(index):
        run=store.latest() or execute_sample("borrowed.csv")
        stage=run["stages"][index]
        return render_template(f"m{index+1}.html",title=TITLE,short=SHORT,modules=MODULES,index=index,run=run,stage=stage,rows=stage["rows"],columns=COLUMNS[index],history=store.history(),labels=LABELS,dispatch=run.get("dispatch"))
    app.add_url_rule("/",view_func=lambda:page(4))
    for index,(slug,name) in enumerate(MODULES):
        app.add_url_rule("/"+slug,endpoint="page_"+slug,view_func=lambda index=index:page(index))
