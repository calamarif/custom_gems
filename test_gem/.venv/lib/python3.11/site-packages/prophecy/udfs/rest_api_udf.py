from pyspark.sql.functions import *
from pyspark.sql.types import *


@udf(
    returnType=StructType(
        [
            StructField("status_code", StringType(), True),
            StructField("reason", StringType(), True),
            StructField("url", StringType(), True),
            StructField("content", StringType(), True),
        ]
    )
)
def get_rest_api(input_cols, await_time_col):
    import json
    import requests
    import time

    inputs = json.loads(input_cols)
    new_dict = {}
    is_multipart = False

    for key, value in inputs.items():
        if value is not None and value.lower() not in ["", "none", "null"]:
            if key == "headers":
                try:
                    headers = json.loads(value)
                    new_dict[key] = headers
                    # Check if Content-Type is multipart/form-data
                    if headers.get("Content-Type", "").lower() == "multipart/form-data":
                        is_multipart = True
                except:
                    continue
            elif key in ["json", "params", "cookies", "proxies"]:
                try:
                    new_dict[key] = json.loads(value)
                except:
                    continue
            elif key in ["data"]:
                try:
                    data = json.loads(value)
                    if is_multipart:
                        # Convert data to multipart files format
                        new_dict["files"] = {k: (None, v) for k, v in data.items()}
                    else:
                        new_dict[key] = data
                except:
                    if is_multipart:
                        new_dict["files"] = {key: (None, value)}
                    else:
                        new_dict[key] = value
            elif key in ["auth"]:
                new_dict[key] = (value.split(":")[0], value.split(":")[1])
            elif key in ["allow_redirects", "stream"]:
                new_dict[key] = True if value.lower() == "true" else False
            elif key in ["verify"]:
                if value.lower() == "true":
                    new_dict[key] = True
                elif value.lower() == "false":
                    new_dict[key] = False
                else:
                    new_dict[key] = value
            elif key in ["timeout"]:
                if ":" in value:
                    new_dict[key] = (
                        float(value.split(":")[0]),
                        float(value.split(":")[1]),
                    )
                else:
                    new_dict[key] = float(value)
            elif key in ["cert"]:
                if ":" in value:
                    new_dict[key] = (value.split(":")[0], value.split(":")[1])
                else:
                    new_dict[key] = value
            else:
                new_dict[key] = value

    # Ensure data is sent as multipart/form-data if the header specifies it
    if is_multipart and "data" in new_dict:
        new_dict["files"] = {k: (None, v) for k, v in new_dict["data"].items()}
        del new_dict["data"]

    response = requests.request(**new_dict)

    if await_time_col.lower() not in ["", "none", "null"]:
        time.sleep(float(await_time_col))

    return response.status_code, response.reason, response.url, response.text

