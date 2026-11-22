REASONS={"BAD_COLUMNS":"列数不匹配","EMPTY_VALUE":"必填值为空","INVALID_NUMBER":"数字格式错误","INVALID_TIME":"时间缺少偏移或格式错误","DUPLICATE_CONFLICT":"同键取值冲突","UNKNOWN_REFERENCE":"引用不存在","STALE_VERSION":"版本已更新","EMPTY_FILE":"文件为空","HEADER_ONLY":"仅有表头","BLANK_ONLY":"全部为空行","DISPATCH_CONFLICT":"任务时段重叠，保留旧版","VEHICLE_CONFLICT":"车辆时段重叠，保留旧版","INVALID_WINDOW":"调度时段无效","UNKNOWN_ROUTE":"线路未登记","EMPTY_CARD":"卡号为空","UNBALANCED_DISPATCH":"调度来源行未着落","DUPLICATE_CARD_DAY":"同卡同日多套结果","BROKEN_CHAIN":"换乘锚点不属同套结果","BAD_DISPATCH_HEADER":"调度表头不匹配","BAD_DISPATCH":"调度依据格式无效"}
def reject(row, code, detail):
    return {**row,"reason":code,"detail":detail}
def sources(row):
    return row.get("_sources", [row.get("_line",0)])
