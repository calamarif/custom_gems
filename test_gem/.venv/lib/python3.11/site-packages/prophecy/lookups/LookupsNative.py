import functools
import logging
from typing import List

from pyspark.sql import SparkSession, Row, DataFrame
from pyspark.sql.functions import udf
from pyspark.sql.types import StructType, ArrayType, IntegerType, BooleanType

lookup_udfs = {}
lookup_last_udfs = {}
lookup_match_udfs = {}
lookup_count_udfs = {}
lookup_nth_udfs = {}
lookup_row_udfs = {}
lookup_row_reverse_udfs = {}

logger = logging.getLogger(__name__)


def createLookup(
        name: str,
        df: DataFrame,
        spark: SparkSession,
        keyCols: List[str],
        valueCols: List[str],
):
    schema = {f.name.lower(): f for f in df.schema}
    missing_cols = list(
        filter(lambda x: x not in schema, [n.lower() for n in keyCols] + [n.lower() for n in valueCols]))
    if missing_cols:
        raise Exception("columns not found: {} ".format(missing_cols))

    key_col_true_names = [schema[n.lower()].name for n in keyCols]
    value_col_true_names = [schema[n.lower()].name for n in valueCols]

    value_schema = StructType([schema[k.lower()] for k in valueCols])
    data_map = {}

    import time
    start_time = time.time()
    for row in df.collect():
        x = row.asDict()
        key_list = tuple([x[y] for y in key_col_true_names])
        new_values_row = Row(**{y: x[y] for y in value_col_true_names})
        data_map[key_list] = data_map.get(key_list, []) + [new_values_row]

    end_time = time.time()
    logger.info("time to collect and populate data_map %s", end_time - start_time)

    start_time = time.time()
    # no call_udf before 3.4, so storing function handles explicitly
    func = functools.partial(_lookup, data_map)
    setattr(func, "__name__", name)
    lookup_udfs[name] = udf(func, value_schema)

    func = functools.partial(_lookup_last, data_map)
    setattr(func, "__name__", name + "_last")
    lookup_last_udfs[name] = udf(func, value_schema)

    func = functools.partial(_lookup_match, data_map)
    setattr(func, "__name__", name + "_match")
    lookup_match_udfs[name] = udf(func, BooleanType())

    func = functools.partial(_lookup_count, data_map)
    setattr(func, "__name__", name + "_count")
    lookup_count_udfs[name] = udf(func, IntegerType())

    func = functools.partial(_lookup_nth, data_map)
    setattr(func, "__name__", name + "_nth")
    lookup_nth_udfs[name] = udf(func, value_schema)

    func = functools.partial(_lookup_row, data_map)
    setattr(func, "__name__", name + "_row")
    lookup_row_udfs[name] = udf(func, ArrayType(value_schema))

    func = functools.partial(_lookup_row_reverse, data_map)
    setattr(func, "__name__", name + "_row_reverse")
    lookup_row_reverse_udfs[name] = udf(func, ArrayType(value_schema))

    register_lookup_udfs(spark, name)
    end_time = time.time()
    logger.info("time to create and register udfs %s", end_time - start_time)


def createRangeLookup(
        name: str,
        df: DataFrame,
        spark: SparkSession,
        min_column: str,
        max_column: str,
        value_columns: List[str],
):
    schema = {f.name.lower(): f for f in df.schema}
    if min_column.lower() not in schema:
        raise Exception("Min column {} doesn't exist in the DataFrame ({}).".format(min_column, schema.keys()))
    if max_column.lower() not in schema:
        raise Exception("Max column {} doesn't exist in the DataFrame ({}).".format(max_column, schema.keys()))
    if schema[min_column.lower()].dataType != schema[max_column.lower()].dataType:
        raise Exception(
            "Max and min column types have to be the same, but found {} and {}".format(schema[min_column.lower()],
                                                                                       schema[max_column.lower()]))

    value_col_true_names = [schema[n.lower()].name for n in value_columns]
    all_columns = [schema[min_column.lower()].name, schema[max_column.lower()].name] + value_col_true_names
    value_schema = StructType([schema[k.lower()] for k in value_columns])

    import time
    start_time = time.time()
    data_list = []
    for row in df.collect():
        x = row.asDict()
        new_values_row = Row(**{y: x[y] for y in all_columns})
        data_list.append(new_values_row)
    end_time = time.time()
    logger.info("time to collect and populate data_list %s", end_time - start_time)

    start_time = time.time()
    # no call_udf before 3.4, so storing function handles explicitly
    func = functools.partial(_range_lookup, data_list, value_col_true_names)
    setattr(func, "__name__", name)
    lookup_udfs[name] = udf(func, value_schema)

    func = functools.partial(_range_lookup_last, data_list, value_col_true_names)
    setattr(func, "__name__", name + "_last")
    lookup_last_udfs[name] = udf(func, value_schema)

    func = functools.partial(_range_lookup_match, data_list, value_col_true_names)
    setattr(func, "__name__", name + "_match")
    lookup_match_udfs[name] = udf(func, BooleanType())

    func = functools.partial(_range_lookup_count, data_list, value_col_true_names)
    setattr(func, "__name__", name + "_count")
    lookup_count_udfs[name] = udf(func, IntegerType())

    func = functools.partial(_range_lookup_nth, data_list, value_col_true_names)
    setattr(func, "__name__", name + "_nth")
    lookup_nth_udfs[name] = udf(func, value_schema)

    func = functools.partial(_range_lookup_row, data_list, value_col_true_names)
    setattr(func, "__name__", name + "_row")
    lookup_row_udfs[name] = udf(func, ArrayType(value_schema))

    func = functools.partial(_range_lookup_row_reverse, data_list, value_col_true_names)
    setattr(func, "__name__", name + "_row_reverse")
    lookup_row_reverse_udfs[name] = udf(func, ArrayType(value_schema))

    register_lookup_udfs(spark, name)
    end_time = time.time()
    logger.info("time to create and register udfs %s", end_time - start_time)


class LookupCondition:
    lookupColumn = ""
    comparisonOp = ""
    inputParam = ""

    def __init__(self, lookupColumn, camparisonOp, inputParam):
        self.lookupColumn = lookupColumn
        self.comparisonOp = camparisonOp
        self.inputParam = inputParam


def createExtendedLookup(name: str,
                         df: DataFrame,
                         spark: SparkSession,
                         conditions: List[LookupCondition],
                         input_params: List[str],
                         value_columns: List[str]):
    schema = {f.name.lower(): f for f in df.schema}
    value_column_schema = [schema[f.lower()] for f in value_columns]
    conditions_with_true_names = [LookupCondition(schema[c.lookupColumn.lower()].name, c.comparisonOp, c.inputParam)
                                  for c in conditions]
    lookup_columns_with_true_names = list(set([c.lookupColumn for c in conditions_with_true_names]))
    value_col_true_names = [schema[n.lower()].name for n in value_columns]
    all_columns = list(set(lookup_columns_with_true_names + value_col_true_names))
    value_schema = StructType(value_column_schema)

    import time
    start_time = time.time()
    data_list = []
    for row in df.collect():
        x = row.asDict()
        new_values_row = Row(**{y: x[y] for y in all_columns})
        data_list.append(new_values_row)
    end_time = time.time()
    logger.info("time to collect and populate data_list %s", end_time - start_time)

    start_time = time.time()
    func = functools.partial(_extended_lookup, data_list, input_params, value_col_true_names,
                             conditions_with_true_names)
    setattr(func, "__name__", name)
    lookup_udfs[name] = udf(func, value_schema)

    func = functools.partial(_extended_lookup_last, data_list, input_params, value_col_true_names,
                             conditions_with_true_names)
    setattr(func, "__name__", name + "_last")
    lookup_last_udfs[name] = udf(func, value_schema)

    func = functools.partial(_extended_lookup_match, data_list, input_params, value_col_true_names,
                             conditions_with_true_names)
    setattr(func, "__name__", name + "_match")
    lookup_match_udfs[name] = udf(func, BooleanType())

    func = functools.partial(_extended_lookup_count, data_list, input_params, value_col_true_names,
                             conditions_with_true_names)
    setattr(func, "__name__", name + "_count")
    lookup_count_udfs[name] = udf(func, IntegerType())

    func = functools.partial(_extended_lookup_nth, data_list, input_params, value_col_true_names,
                             conditions_with_true_names)
    setattr(func, "__name__", name + "_nth")
    lookup_nth_udfs[name] = udf(func, value_schema)

    func = functools.partial(_extended_lookup_row, data_list, input_params, value_col_true_names,
                             conditions_with_true_names)
    setattr(func, "__name__", name + "_row")
    lookup_row_udfs[name] = udf(func, ArrayType(value_schema))

    func = functools.partial(_extended_lookup_row_reverse, data_list, input_params, value_col_true_names,
                             conditions_with_true_names)
    setattr(func, "__name__", name + "_row_reverse")
    lookup_row_reverse_udfs[name] = udf(func, ArrayType(value_schema))

    register_lookup_udfs(spark, name)
    end_time = time.time()
    logger.info("time to create and register udfs %s", end_time - start_time)


def register_lookup_udfs(spark, name):
    spark.udf.register(name, lookup_udfs[name])
    spark.udf.register(name + "_last", lookup_last_udfs[name])
    spark.udf.register(name + "_match", lookup_match_udfs[name])
    spark.udf.register(name + "_count", lookup_count_udfs[name])
    spark.udf.register(name + "_nth", lookup_nth_udfs[name])
    spark.udf.register(name + "_row", lookup_row_udfs[name])
    spark.udf.register(name + "_row_reverse", lookup_row_reverse_udfs[name])


def lookup(lookupName: str, *cols):
    if lookupName in lookup_udfs:
        return lookup_udfs[lookupName](*cols)
    else:
        raise Exception("No lookup UDF registered for {}".format(lookupName))


def lookup_last(lookupName: str, *cols):
    if lookupName in lookup_last_udfs:
        return lookup_last_udfs[lookupName](*cols)
    else:
        raise Exception("No lookup_last UDF registered for {}".format(lookupName))


def lookup_match(lookupName: str, *cols):
    if lookupName in lookup_match_udfs:
        return lookup_match_udfs[lookupName](*cols)
    else:
        raise Exception("No lookup_match UDF registered for {}".format(lookupName))


def lookup_count(lookupName: str, *cols):
    if lookupName in lookup_count_udfs:
        return lookup_count_udfs[lookupName](*cols)
    else:
        raise Exception("No lookup_count UDF registered for {}".format(lookupName))


def lookup_row(lookupName: str, *cols):
    if lookupName in lookup_row_udfs:
        return lookup_row_udfs[lookupName](*cols)
    else:
        raise Exception("No lookup_row UDF registered for {}".format(lookupName))


def lookup_row_reverse(lookupName: str, *cols):
    if lookupName in lookup_row_reverse_udfs:
        return lookup_row_reverse_udfs[lookupName](*cols)
    else:
        raise Exception("No lookup_row_reverse UDF registered for {}".format(lookupName))


def lookup_nth(lookupName: str, *cols):
    if lookupName in lookup_nth_udfs:
        return lookup_nth_udfs[lookupName](*cols)
    else:
        raise Exception("No lookup_nth UDF registered for {}".format(lookupName))


def lookup_helper(data: dict, *keys):
    keys = tuple(keys)
    if keys in data:
        return data[keys]
    else:
        return None


def _lookup(data: dict, *keys):
    res = lookup_helper(data, *keys)
    if res and len(res) > 0:
        return res[0]
    else:
        return None


def _lookup_last(data: dict, *keys):
    res = lookup_helper(data, *keys)
    if res and len(res) > 0:
        return res[-1]
    else:
        return None


def _lookup_match(data: dict, *keys):
    return lookup_helper(data, *keys) is not None


def _lookup_count(data: dict, *keys):
    res = lookup_helper(data, *keys)
    if res:
        return len(res)
    else:
        return 0


def _lookup_row(data: dict, *keys):
    res = lookup_helper(data, *keys)
    if res:
        return res
    else:
        return None


def _lookup_row_reverse(data: dict, *keys):
    res = lookup_helper(data, *keys)
    if res:
        return res[::-1]
    else:
        return None


def _lookup_nth(data: dict, *args):
    keys = args[:-1]
    index = args[-1]
    res = lookup_helper(data, *keys)
    if res and len(res) > index:
        return res[index]
    else:
        return None


def range_lookup_helper(data: List[Row], value_columns: List[str], key_col):
    filtered_data = list(filter(lambda x: x[0] <= key_col < x[1], data))
    res = []
    for r in filtered_data:
        d = r.asDict()
        output = {c: d[c] for c in value_columns}
        res.append(Row(**output))
    return res


def _range_lookup(data: List[Row], value_columns: List[str], key_col):
    res = range_lookup_helper(data, value_columns, key_col)
    if res and len(res) > 0:
        return res[0]
    else:
        return None


def _range_lookup_last(data: List[Row], value_columns: List[str], key_col):
    res = range_lookup_helper(data, value_columns, key_col)
    if res and len(res) > 0:
        return res[-1]
    else:
        return None


def _range_lookup_match(data: List[Row], value_columns: List[str], key_col):
    return range_lookup_helper(data, value_columns, key_col) is not None


def _range_lookup_count(data: List[Row], value_columns: List[str], key_col):
    res = range_lookup_helper(data, value_columns, key_col)
    if res:
        return len(res)
    else:
        return 0


def _range_lookup_row(data: List[Row], value_columns: List[str], key_col):
    res = range_lookup_helper(data, value_columns, key_col)
    if res:
        return res
    else:
        return None


def _range_lookup_row_reverse(data: List[Row], value_columns: List[str], key_col):
    res = range_lookup_helper(data, value_columns, key_col)
    if res:
        return res[::-1]
    else:
        return None


def _range_lookup_nth(data: List[Row], value_columns: List[str], key_col, index):
    res = range_lookup_helper(data, value_columns, key_col)
    if res and len(res) > index:
        return res[index]
    else:
        return None


def extended_lookup_helper(data: List[Row], input_params: List[str], value_columns: List[str],
                           conditions: List[LookupCondition], *keys):
    def comp(a, b, op):
        if op == "==":
            return a == b
        elif op == "<":
            return a < b
        elif op == ">":
            return a > b
        elif op == "<=":
            return a <= b
        elif op == ">=":
            return a >= b
        elif op == "!=":
            return a != b
        else:
            raise Exception("unsupported operator {}".format(op))

    filtered_data = []
    input_param_with_vals = {k: v for k, v in zip(input_params, keys)}
    for r in data:
        d = r.asDict()
        match = True
        for c in conditions:
            if not comp(d[c.lookupColumn], input_param_with_vals[c.inputParam], c.comparisonOp):
                match = False
                break
        if match:
            output = {c: d[c] for c in value_columns}
            filtered_data.append(Row(**output))

    return filtered_data


def _extended_lookup(data: List[Row], input_params: List[str], value_columns: List[str],
                     conditions: List[LookupCondition], *keys):
    res = extended_lookup_helper(data, input_params, value_columns, conditions, *keys)
    if res and len(res) > 0:
        return res[0]
    else:
        return None


def _extended_lookup_last(data: List[Row], input_params: List[str], value_columns: List[str],
                          conditions: List[LookupCondition], *keys):
    res = extended_lookup_helper(data, input_params, value_columns, conditions, *keys)
    if res and len(res) > 0:
        return res[-1]
    else:
        return None


def _extended_lookup_match(data: List[Row], input_params: List[str], value_columns: List[str],
                           conditions: List[LookupCondition], *keys):
    return extended_lookup_helper(data, input_params, value_columns, conditions, *keys) is not None


def _extended_lookup_count(data: List[Row], input_params: List[str], value_columns: List[str],
                           conditions: List[LookupCondition], *keys):
    res = extended_lookup_helper(data, input_params, value_columns, conditions, *keys)
    if res:
        return len(res)
    else:
        return 0


def _extended_lookup_row(data: List[Row], input_params: List[str], value_columns: List[str],
                         conditions: List[LookupCondition], *keys):
    res = extended_lookup_helper(data, input_params, value_columns, conditions, *keys)
    if res:
        return res
    else:
        return None


def _extended_lookup_row_reverse(data: List[Row], input_params: List[str], value_columns: List[str],
                                 conditions: List[LookupCondition], *keys):
    res = extended_lookup_helper(data, input_params, value_columns, conditions, *keys)
    if res:
        return res[::-1]
    else:
        return None


def _extended_lookup_nth(data: List[Row], input_params: List[str], value_columns: List[str],
                         conditions: List[LookupCondition], *args):
    keys = args[:-1]
    index = args[-1]
    res = extended_lookup_helper(data, input_params, value_columns, conditions, *keys)
    if res and len(res) > index:
        return res[index]
    else:
        return None


def extended_lookup(lookupName: str, *cols):
    if lookupName in lookup_udfs:
        return lookup_udfs[lookupName](*cols)
    else:
        raise Exception("No lookup UDF registered for {}".format(lookupName))
