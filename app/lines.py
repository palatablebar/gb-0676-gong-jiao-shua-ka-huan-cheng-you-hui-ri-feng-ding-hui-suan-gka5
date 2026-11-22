"""Line-code aliases. Business codes stay textual so leading zeros survive."""
ROUTES={"01":"01","1路":"01","02":"02","2路":"02","03":"03","3路":"03"}
def normalize_route(value):
    if value is None: return None
    return ROUTES.get(str(value).strip())
