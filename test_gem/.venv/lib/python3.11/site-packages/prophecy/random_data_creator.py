import time
import random
import string
from pyspark.sql.functions import *
from pyspark.sql.types import StringType


def get_rand_int(end, start=0):
    return round((rand() * (end - start) + lit(start)))


def string_generator(size):
    chars = string.ascii_uppercase + string.digits

    def f():
        out = "".join(random.choices(chars, k=size))
        return out

    return udf(f)


def create_random_field(data_type, end_epoch=time.time()):
    if data_type.endswith("_normal"):
        random_fn = randn() + lit(0.5)
        data_type = data_type[:data_type.find("_")]
    else:
        random_fn = rand()
    if data_type == 'numeric':
        return random_fn * 10000000
    elif data_type == 'boolean':
        return when(random_fn > 0.5, True).otherwise(False)
    elif data_type == 'null':
        return lit(None)
    elif data_type == 'date':
        return to_date(from_unixtime(get_rand_int(end=end_epoch)))
    elif data_type == 'datetime':
        return from_unixtime(get_rand_int(end=end_epoch)).cast(StringType())
    elif data_type == 'id':
        return string_generator(20)()
    elif data_type.startswith("rand_int"):
        start = int(data_type[data_type.find("(")+1:data_type.find(",")])
        end = int(data_type[data_type.find(",")+1:data_type.find(")")])
        return get_rand_int(start, end)
    elif data_type.startswith("string"):
        str_length = int(data_type[data_type.find("(") + 1:data_type.find(")")])
        return string_generator(random.choice(list(range(str_length))))()


def create_data_batch(data_config):
    full_column_dict = {}
    final_col_list = []
    for data_type, col_list in data_config.items():
        data_type_nm = data_type.replace("(", "_").replace(")", "_").replace("__", "_")
        col_dict = {}
        if type(col_list) == int:
            for i in range(col_list):
                col_dict[f"{data_type_nm}_col_num_{i}"] = {'type': data_type}
        elif type(col_list) == list:
            if type(col_list[0]) == tuple:
                for i in col_list:
                    col_dict[f"{i[0]}_col"] = {'type': data_type, 'args': i[1]}
            elif type(col_list[0]) == dict:
                idx = 0
                for json_schema in col_list:
                    idx += 1
                    col_dict[f"{data_type_nm}_col_num_{idx}"] = {'type': data_type, 'value': json_schema}
            else:
                for col_nm in col_list:
                    col_dict[col_nm] = {'type': data_type}
        else:
            raise Exception("The Config is not defined Properly")
        full_column_dict.update(col_dict)
    for col_nm, val_obj in full_column_dict.items():
        final_col_nm = col_nm.replace(", ", "_").replace(",", "_")
        if val_obj.get("type") == "json":
            list_of_cols = create_data_batch(val_obj.get("value"))
            final_col_list.append(struct(*list_of_cols).alias(final_col_nm))
        else:
            col_obj = create_random_field(val_obj.get("type"))
            col_obj = col_obj.alias(final_col_nm)
            final_col_list.append(col_obj)
    return final_col_list
