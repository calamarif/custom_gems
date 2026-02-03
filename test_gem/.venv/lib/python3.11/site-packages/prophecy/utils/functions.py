import inspect
from typing import Tuple

from pyspark.sql import Column
from pyspark.sql import DataFrame
from pyspark.sql.functions import col, expr
from pyspark.sql.types import StructType


def get_alias(column: Column):
    # In case of UC Shared cluster, `._jc` is unavailable. Keeping this for backward compatibility purpose.
    try:
        return column._jc.expr().name()
    except:
        return column._jc.expr().sql()


def flatten_struct(df: DataFrame, parent_column: str, struct_type: StructType) -> DataFrame:
    expanded_columns = [(field.name, col(f"`{parent_column}`.`{field.name}`").alias(field.name)) for field in
                        struct_type.fields]
    new_df = df
    for (alias, column) in expanded_columns:
        new_df = new_df.withColumn(alias, column)
    new_df = new_df.drop(parent_column)

    return new_df


def flatten_column_if_required(df, column_name):
    column_schema = df.schema[column_name]
    is_multi_column_output = next(
        (field.metadata.get("isMultiColumnOutput", False)
         for field in df.schema.fields
         if field.name == column_name),
        False
    )
    if is_multi_column_output and isinstance(column_schema.dataType, StructType):
        return flatten_struct(df, column_name, column_schema.dataType)
    else:
        return df

def add_rule(df: DataFrame, column: Column) -> DataFrame:
    old_column_names = df.columns
    # In case of UC Shared cluster, since column._jc isn't available we cannot access the alias from Column datatype.
    # That's why we need to firstly create a dummy dataframe with new column. The last column will be the newly added one.
    new_df = df.select(expr("*"), column)
    old_columns_and_new_column = new_df.columns
    newly_added_column_name = old_columns_and_new_column[-1]
    """
    If column name with name same as that of newly added column already existed, 
    then `df.select(expr("*"), column)` will add two columns with the same name.
    All the subsequent operations referring to this duplicate column will throw ambiguity error. 
    Hence, we need to replace the existing column with the new column expression. We need to manually drop the column. 
    """
    case_insensitive_old_column_names = [name.lower() for name in old_column_names]
    if newly_added_column_name.lower() in case_insensitive_old_column_names:
        # include all except the one which has the name same as the newly_added_column_name
        already_added = False
        all_column_exprs = []
        for c in old_column_names:
            if c.lower() != newly_added_column_name.lower():
                all_column_exprs.append(col(c))
            elif c.lower() == newly_added_column_name.lower() and not already_added:
                already_added = True
                all_column_exprs.append(column)
            else:
                pass
        new_df = df.select(*all_column_exprs)
    return flatten_column_if_required(new_df, newly_added_column_name)


def get_column_metadata():
    return {"isMultiColumnOutput": True}


def execute_rule(rule_func):
    """
    Decorator to be used with rule definitions. This will do lazy evaluation of
    default values of rules param.
    """

    def get_value(argument):
        if isinstance(argument, Column):
            return argument
        if callable(argument):
            return argument()
        else:
            return argument

    def wrapper(*args, **kwargs):
        args_with_default = {}
        for (name, param) in inspect.signature(rule_func).parameters.items():
            if param.default is not param.empty:
                args_with_default[name] = param.default
            else:
                args_with_default[name] = None
        to_be_updated_keys = list(args_with_default.keys())[0:len(args)]
        for index in range(len(args)):
            args_with_default.update({to_be_updated_keys[index]: args[index]})
        updated_args = {**args_with_default, **kwargs}
        result = rule_func(**{key: get_value(value) for (key, value) in updated_args.items()})
        return result

    return wrapper
