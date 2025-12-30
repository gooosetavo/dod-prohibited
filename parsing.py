import pandas as pd

def get_nested(data, path, default=None):
    keys = path.split('.')
    value = data
    try:
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError):
        return default

def parse_prohibited_list(settings):
    prohibited_list = get_nested(settings, "dodProhibited")
    df = pd.DataFrame(prohibited_list)
    return df
