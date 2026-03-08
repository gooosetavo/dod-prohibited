import pandas as pd
import logging

# Configure logging for GitHub Actions (stdout, INFO level by default)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)


def get_nested(data, path, default=None):
    keys = path.split(".")
    value = data
    try:
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError) as e:
        logging.warning(f"Failed to get nested key '{path}': {e}")
        return default


def parse_prohibited_list(settings):
    logging.info("Parsing prohibited list from settings.")
    prohibited_list = get_nested(settings, "dodProhibited")
    if prohibited_list is None:
        logging.error("No 'dodProhibited' key found in settings.")
        return pd.DataFrame()
    df = pd.DataFrame(prohibited_list)
    logging.info(f"Parsed {len(df)} prohibited substances.")
    return df
