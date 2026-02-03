from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DataType,
    NullType,
    BooleanType,
    IntegerType,
    LongType,
    FloatType,
    DoubleType,
    DecimalType,
    DateType,
    TimestampType,
    StringType,
    MapType,
)
import uuid, enum, json
from prophecy.config.config_base import is_serverless


class DiffKeys(enum.Enum):
    JOINED = "joined"
    SUMMARY = "summary"
    CLEANED = "cleaned"
    MISMATCHED = "mismatched"
    EXPECTED = "expected"
    GENERATED = "generated"
    KEY_COLUMNS = "keyCols"
    VALUE_COLUMNS = "valueCols"


# Vectorized version using pandas UDF
def compare_structs_vectorized(left_series, right_series):
    try:
        # Try newer import path first (PySpark 3.2+)
        from pyspark.sql.pandas.functions import pandas_udf
    except ImportError:
        # Fall back to older import path
        from pyspark.sql.functions import pandas_udf

    import pandas as pd

    # Insert the following helper function after the import statements
    def compare_structs(l, r):
        """
        Recursively compare two complex structures for equality.
        This function supports dicts, lists, and primitive types.
        """
        if l is None and r is None:
            return True
        if l is None or r is None:
            return False
        if isinstance(l, dict) and isinstance(r, dict):
            if set(l.keys()) != set(r.keys()):
                return False
            return all(compare_structs(l[k], r[k]) for k in l)
        if isinstance(l, list) and isinstance(r, list):
            if len(l) != len(r):
                return False
            return all(compare_structs(li, ri) for li, ri in zip(l, r))
        return l == r

    @pandas_udf("boolean")
    def udf_compare_structs(left_series, right_series):
        """
        Vectorized version of compare_structs using pandas UDF.
        Processes data in batches for better performance.
        """
        result = pd.Series([False] * len(left_series))

        for i in range(len(left_series)):
            left = left_series.iloc[i]
            right = right_series.iloc[i]
            # Still use the recursive comparison for individual elements
            result.iloc[i] = compare_structs(left, right)

        return result

    return udf_compare_structs(left_series, right_series)


def needs_complex_comparison(data_type):
    """
    Determines if a data type requires complex comparison logic.
    Returns True for: MapType, ArrayType, and StructType with nested complex types.
    """
    from pyspark.sql.types import MapType, ArrayType, StructType

    if isinstance(data_type, MapType):
        return True
    elif isinstance(data_type, ArrayType):
        return needs_complex_comparison(data_type.elementType)
    elif isinstance(data_type, StructType):
        return any(
            needs_complex_comparison(field.dataType) for field in data_type.fields
        )
    return False


class DataFrameDiff:
    COMPUTED_DIFFS = {}

    # ---------------------------------------------------------------------------
    # Helpers for safe identifier handling
    # ---------------------------------------------------------------------------
    @staticmethod
    def prophecy_q(name: str) -> str:
        """Quote a Spark identifier so it can contain any character."""
        return f"`{name.replace('`', '``')}`"

    @staticmethod
    def prophecy_sc(struct: str, field: str) -> str:
        """Return 'struct.`field`' with the field safely quoted."""
        return f"{struct}.{DataFrameDiff.prophecy_q(field)}"

    @classmethod
    def get_precedence(cls, dt: DataType) -> int:
        """
        Assign a numeric precedence/rank to Spark data types.
        Lower value = narrower type, Higher value = broader type.
        """
        if isinstance(dt, NullType):
            # Null can be promoted to anything else
            return 0
        elif isinstance(dt, BooleanType):
            return 1
        elif isinstance(dt, IntegerType):
            return 2
        elif isinstance(dt, LongType):
            return 3
        elif isinstance(dt, FloatType):
            return 4
        elif isinstance(dt, DoubleType):
            return 5
        elif isinstance(dt, DecimalType):
            # Treat decimal as broader than basic floats/doubles for numeric contexts
            return 6
        elif isinstance(dt, DateType):
            return 7
        elif isinstance(dt, TimestampType):
            return 8
        elif isinstance(dt, StringType):
            return 9
        # Fallback for complex or unhandled types
        return 99

    @classmethod
    def find_common_type(cls, dt1: DataType, dt2: DataType) -> DataType:
        """
        Find a 'common' Spark data type for dt1 and dt2 based on simplified precedence rules.
        """
        # If they're exactly the same (including decimal precision/scale), just return dt1
        if dt1 == dt2:
            return dt1

        # Both are DecimalType but differ in precision or scale
        if isinstance(dt1, DecimalType) and isinstance(dt2, DecimalType):
            # Pick the "wider" decimal
            precision = max(dt1.precision, dt2.precision)
            scale = max(dt1.scale, dt2.scale)
            return DecimalType(precision=precision, scale=scale)

        # If either is NullType, pick the other
        if isinstance(dt1, NullType):
            return dt2
        if isinstance(dt2, NullType):
            return dt1

        # Otherwise, compare precedence
        prec1 = cls.get_precedence(dt1)
        prec2 = cls.get_precedence(dt2)

        # If both are numeric (including decimals), pick the broader
        numeric_types = (
            BooleanType,
            IntegerType,
            LongType,
            FloatType,
            DoubleType,
            DecimalType,
        )
        if isinstance(dt1, numeric_types) and isinstance(dt2, numeric_types):
            return dt1 if prec1 >= prec2 else dt2

        # Date <-> Timestamp => Timestamp
        if (isinstance(dt1, DateType) and isinstance(dt2, TimestampType)) or (
            isinstance(dt2, DateType) and isinstance(dt1, TimestampType)
        ):
            return TimestampType()

        # In all other cases (e.g. one is StringType, or higher precedence):
        # todo recursive handling for array and struct types.
        return dt1 if prec1 > prec2 else dt2

    @classmethod
    def align_dataframes_schemas(
        cls, df1: DataFrame, df2: DataFrame
    ) -> (DataFrame, DataFrame):
        """
        Aligns df1 and df2 so that columns with the same name have the same data type.
        Returns two new DataFrames (df1_aligned, df2_aligned).
        """
        df1_aligned = df1
        df2_aligned = df2

        # Columns that exist in both DataFrames
        common_cols = set(df1.columns).intersection(set(df2.columns))

        for col_name in common_cols:
            dt1 = df1.schema[col_name].dataType
            dt2 = df2.schema[col_name].dataType

            # Determine the common type
            common_dt = cls.find_common_type(dt1, dt2)

            # Important: Compare the entire DataType object, not just the class.
            if dt1 != common_dt:
                df1_aligned = df1_aligned.withColumn(
                    col_name, F.col(col_name).cast(common_dt)
                )
            if dt2 != common_dt:
                df2_aligned = df2_aligned.withColumn(
                    col_name, F.col(col_name).cast(common_dt)
                )

        return df1_aligned, df2_aligned

    # Helper function to avoid column name collisions.
    @classmethod
    def get_unique_col_name(cls, df, base_name):
        candidate = base_name
        i = 0
        while candidate in df.columns:
            candidate = f"{base_name}_diffcol_{i}"
            i += 1
        return candidate

    @classmethod
    def split_df_by_pk_uniqueness(cls, df, key_columns):
        """
        Returns two DataFrames:
        1) df_unique: Rows where 'key_columns' is unique (exactly 1 occurrence)
        2) df_not_unique: Rows where 'key_columns' occur more than once

        This version handles NULL values by creating a null-safe representation using structs.
        """

        ns_columns = []
        for col in key_columns:
            ns_col = cls.get_unique_col_name(df, f"__ns_{col}")
            # Create a struct that holds a flag and the original value.
            df = df.withColumn(
                ns_col,
                F.struct(F.col(col).isNull().alias("is_null"), F.col(col).alias("val")),
            )
            ns_columns.append(ns_col)

        # Generate a unique alias for the count column.
        count_alias = cls.get_unique_col_name(df, "__count__")

        # Group by the null-safe key columns and count occurrences.
        pk_counts = df.groupBy(ns_columns).agg(F.count("*").alias(count_alias))

        # Separate groups with a single occurrence vs. multiple occurrences.
        pk_once = pk_counts.filter(F.col(count_alias) == 1).select(*ns_columns)
        pk_not_once = pk_counts.filter(F.col(count_alias) > 1).select(*ns_columns)

        # Join back with the original DataFrame on the null-safe columns.
        df_unique = df.join(pk_once, on=ns_columns, how="inner")
        df_not_unique = df.join(pk_not_once, on=ns_columns, how="inner")

        # Drop the temporary null-safe columns.
        df_unique = df_unique.drop(*ns_columns)
        df_not_unique = df_not_unique.drop(*ns_columns)

        return df_unique, df_not_unique

    @classmethod
    def create_joined_df(
        cls,
        generated_df,
        expected_df,
        key_columns,
        value_columns,
        join_type="full_outer",
    ):
        """
        Compare two DataFrames and identify presence in left, right, and differences in values.

        :param generated_df: First / Calculated DataFrame (left)
        :param expected_df: Second / Expected DataFrame (right)
        :param key_columns: List of key columns for joining
        :param value_columns: List of value columns to compare
        :return: Resultant DataFrame with key columns, presence flags, and value comparison
        """

        join_type = join_type.lower()
        if join_type not in {"full_outer", "left", "right", "inner"}:
            raise ValueError(f"Unsupported join_type '{join_type}'.")

        generated_df, expected_df = cls.align_dataframes_schemas(
            generated_df, expected_df
        )

        # Construct a null-safe join condition for each key column.
        join_condition = [F.expr(f"left.{col} <=> right.{col}") for col in key_columns]

        # Perform a full outer join on the key columns
        joined_df = generated_df.alias("left").join(
            expected_df.alias("right"), on=join_condition, how=join_type
        )

        # Compute coalesced key columns and presence flags
        coalesced_keys = [
            F.coalesce(
                F.col(DataFrameDiff.prophecy_sc("left", col)),
                F.col(DataFrameDiff.prophecy_sc("right", col)),
            ).alias(col)
            for col in key_columns
        ]

        presence_in_left = (
            F.when(
                F.expr(
                    " AND ".join(
                        [
                            f"coalesce(left.{DataFrameDiff.prophecy_q(col)}, right.{DataFrameDiff.prophecy_q(col)}) <=> left.{DataFrameDiff.prophecy_q(col)}"
                            for col in key_columns
                        ]
                    )
                ),
                1,
            )
            .otherwise(0)
            .alias("presence_in_left")
        )

        presence_in_right = (
            F.when(
                F.expr(
                    " AND ".join(
                        [
                            f"coalesce(left.{DataFrameDiff.prophecy_q(col)}, right.{DataFrameDiff.prophecy_q(col)}) <=> right.{DataFrameDiff.prophecy_q(col)}"
                            for col in key_columns
                        ]
                    )
                ),
                1,
            )
            .otherwise(0)
            .alias("presence_in_right")
        )

        # Build the left and right structs for the value columns.
        # If a column is missing in a DataFrame, we substitute it with a null literal.
        left_value_exprs = [
            (
                F.col(DataFrameDiff.prophecy_sc("left", col)).alias(col)
                if col in generated_df.columns
                else F.lit(None).alias(col)
            )
            for col in value_columns
        ]
        right_value_exprs = [
            (
                F.col(DataFrameDiff.prophecy_sc("right", col)).alias(col)
                if col in expected_df.columns
                else F.lit(None).alias(col)
            )
            for col in value_columns
        ]

        left_struct = F.struct(*left_value_exprs).alias("left_values")
        right_struct = F.struct(*right_value_exprs).alias("right_values")

        # Select the final result
        result_df = joined_df.select(
            *coalesced_keys,  # Coalesced key columns
            presence_in_left,  # Presence flag for left
            presence_in_right,  # Presence flag for right
            left_struct,  # Struct containing left values (with missing columns as null)
            right_struct,  # Struct containing right values
        )

        return result_df

    @classmethod
    def add_row_matches_column(cls, joined_df):
        """
        Adds a new column 'row_matches' to the DataFrame that indicates whether
        the values in 'left_values' and 'right_values' columns are equal.
        Uses <=> operator for simple structures and UDF for complex ones.
        """
        left_struct = "left_values"
        right_struct = "right_values"

        # Get the struct type for left_values
        left_struct_type = joined_df.schema[left_struct].dataType

        # Check if the struct contains complex types that require UDF
        if needs_complex_comparison(left_struct_type):
            # Use vectorized UDF for complex structures
            return joined_df.withColumn(
                "row_matches",
                compare_structs_vectorized(F.col(left_struct), F.col(right_struct)),
            )
        else:
            # Use <=> operator for simple structures (more efficient)
            return joined_df.withColumn(
                "row_matches", F.expr(f"{left_struct} <=> {right_struct}")
            )

    @classmethod
    def add_column_comparison_results(cls, joined_df):
        """
        Adds a new column to the DataFrame containing comparison results between two struct columns.
        Uses <=> operator for simple types and UDF for complex types like MapType.
        """
        left_struct = "left_values"
        right_struct = "right_values"
        comparison_struct = "compared_values"

        # Retrieve the fields (with types) from the left struct column
        left_struct_fields = joined_df.schema[left_struct].dataType.fields

        # First determine if both rows exist in their respective dataframes
        both_rows_exist = (F.col("presence_in_left") == 1) & (
            F.col("presence_in_right") == 1
        )

        # Generate comparison expressions for each field in the struct
        comparison_expressions = []
        for field in left_struct_fields:
            field_name = field.name

            # Check if this field requires complex comparison
            if needs_complex_comparison(field.dataType):
                comparison_expr = (
                    F.when(
                        both_rows_exist,
                        compare_structs_vectorized(
                            F.col(f"{left_struct}.{field_name}"),
                            F.col(f"{right_struct}.{field_name}"),
                        ),
                    )
                    .otherwise(F.lit(False))
                    .alias(field_name)
                )
            else:
                # For simple types, use the original approach with <=>
                expr_str = f"{DataFrameDiff.prophecy_sc(left_struct, field_name)} <=> {DataFrameDiff.prophecy_sc(right_struct, field_name)}"
                comparison_expr = (
                    F.when(both_rows_exist, F.expr(expr_str))
                    .otherwise(F.lit(False))
                    .alias(field_name)
                )

            comparison_expressions.append(comparison_expr)

        # Combine individual comparison results into a single struct column
        comparison_struct_col = F.struct(*comparison_expressions)

        # Add the comparison struct column to the DataFrame
        return joined_df.withColumn(comparison_struct, comparison_struct_col)

    @classmethod
    def compute_mismatch_summary(cls, joined_df):
        """
        Computes summary statistics for mismatches across specified columns in the joined DataFrame.

        This function calculates:
        - The number of rows where all specified columns match.
        - The number of rows with at least one mismatch.
        - The total number of mismatches across all specified columns and rows.
        - The count of matches and mismatches for each individual specified column.

        Args:
            joined_df (DataFrame): The input Spark DataFrame containing a `compared_values` struct column
                                   with boolean fields indicating match status for each specified column,
                                   and a `row_matches` boolean column indicating if the entire row matches.

        Returns:
            DataFrame: A summary DataFrame with the following columns:
                - rows_matching (Long): Number of rows where all specified columns match.
                - rows_not_matching (Long): Number of rows with at least one mismatch.
                - <column>_match_count (Long): Number of matches for each specified column.
                - <column>_mismatch_count (Long): Number of mismatches for each specified column.
        """

        comparison_struct = "compared_values"

        fields = joined_df.select(f"{comparison_struct}.*").columns

        # Build aggregators for match and mismatch counts for each specified column
        per_column_aggregators = []
        for column in fields:
            # Aggregator for the number of matches in the current column
            match_aggregator = F.coalesce(
                F.sum(
                    F.when(
                        F.col(DataFrameDiff.prophecy_sc(comparison_struct, column)), 1
                    ).otherwise(0)
                ),
                F.lit(0),
            ).alias(f"{column}_match_count")
            per_column_aggregators.append(match_aggregator)

            # Aggregator for the number of mismatches in the current column
            mismatch_aggregator = F.coalesce(
                F.sum(
                    F.when(
                        ~F.col(DataFrameDiff.prophecy_sc(comparison_struct, column)), 1
                    ).otherwise(0)
                ),
                F.lit(0),
            ).alias(f"{column}_mismatch_count")
            per_column_aggregators.append(mismatch_aggregator)

        # New aggregators for key column matching.
        # A key is considered matching if both presence_in_left and presence_in_right are 1.
        key_cols_match_expr = F.coalesce(
            F.sum(
                F.when(
                    (F.col("presence_in_left") == 1)
                    & (F.col("presence_in_right") == 1),
                    1,
                ).otherwise(0)
            ),
            F.lit(0),
        ).alias("key_columns_match_count")

        key_cols_mismatch_expr = F.coalesce(
            F.sum(
                F.when(
                    ~(
                        (F.col("presence_in_left") == 1)
                        & (F.col("presence_in_right") == 1)
                    ),
                    1,
                ).otherwise(0)
            ),
            F.lit(0),
        ).alias("key_columns_mismatch_count")

        # Aggregate all summary statistics into a single DataFrame.
        summary_df = joined_df.agg(
            # Count of rows where all specified columns match
            F.coalesce(
                F.sum(F.when(F.col("row_matches"), 1).otherwise(0)), F.lit(0)
            ).alias("rows_matching"),
            # Count of rows with at least one mismatch
            F.coalesce(
                F.sum(F.when(~F.col("row_matches"), 1).otherwise(0)), F.lit(0)
            ).alias("rows_not_matching"),
            # Count of key column matches and mismatches
            key_cols_match_expr,
            key_cols_mismatch_expr,
            # Include all per-column match and mismatch aggregators
            *per_column_aggregators,
        )

        return summary_df

    @classmethod
    def get_value_columns(cls, df1, df2, key_columns):
        _all_columns = set(df1.columns).union(set(df2.columns))
        return list(_all_columns - set(key_columns))

    @classmethod
    def get_columns_schema(cls, df):
        return [
            {"name": field.name, "type": field.dataType.simpleString()}
            for field in df.schema.fields
        ]

    @classmethod
    def get_diff_summary_dict(cls, diff_key):
        diff_entry = cls.COMPUTED_DIFFS[diff_key]
        summary_df, value_columns = (
            diff_entry[DiffKeys.SUMMARY.value],
            diff_entry[DiffKeys.VALUE_COLUMNS.value],
        )
        key_columns = diff_entry[DiffKeys.KEY_COLUMNS.value]
        expected_df = diff_entry[DiffKeys.EXPECTED.value]
        generated_df = diff_entry[DiffKeys.GENERATED.value]

        summary_row = summary_df.collect()[0].asDict()
        rows_matching = summary_row["rows_matching"]
        rows_not_matching = summary_row["rows_not_matching"]
        total_rows = rows_matching + rows_not_matching

        # Calculate column match statistics
        perfect_val_column_matches = 0
        for col in value_columns:
            if summary_row[f"{col}_match_count"] == total_rows:
                perfect_val_column_matches += 1

        # Calculate if key columns match in all rows
        key_columns_match = summary_row["key_columns_match_count"] == total_rows
        key_columns_match_count = len(key_columns) if key_columns_match else 0

        # Calculate dataset matching status
        dataset_match_status = "Matching" if rows_not_matching == 0 else "Not Matching"
        match_percentage = (
            int((rows_matching / total_rows * 100)) if total_rows > 0 else 0
        )

        # Helper function to get dataset stats
        def get_dataset_stats(df, key_cols):
            unique_df, duplicate_df = cls.split_df_by_pk_uniqueness(df, key_cols)
            return {
                "columns": cls.get_columns_schema(df),
                "rowsCount": df.count(),
                "uniquePkCount": unique_df.count(),
                "duplicatePkCount": duplicate_df.count(),
            }

        diff_summary = {
            "label": diff_key,
            "data": {
                "summaryTiles": [
                    {
                        "title": "Datasets matching status",
                        "text": dataset_match_status,
                        "badgeContent": f"{match_percentage}",
                        "isPositive": rows_not_matching == 0,
                        "order": 0,
                        "orderType": "MatchingStatus",
                        "toolTip": "The percentage of rows that match between the expected and generated datasets.",
                    },
                    {
                        "title": "Number of columns matching",
                        "text": f"{perfect_val_column_matches + key_columns_match_count}/{len(value_columns) + len(key_columns)}",
                        "badgeContent": f"{int(((perfect_val_column_matches + key_columns_match_count)/(len(value_columns) + len(key_columns)))*100)}",
                        "isPositive": perfect_val_column_matches == len(value_columns)
                        and key_columns_match,
                        "order": 1,
                        "orderType": "ColumnMatch",
                        "toolTip": "The percentage of columns that match between the expected and generated datasets.",
                    },
                    {
                        "title": "Number of rows matching",
                        "text": f"{rows_matching:,}/{total_rows:,}",
                        "badgeContent": f"{match_percentage}",
                        "isPositive": rows_matching == total_rows,
                        "order": 2,
                        "orderType": "RowMatch",
                        "toolTip": "The percentage of rows that match between the expected and generated datasets.",
                    },
                ],
                "expData": get_dataset_stats(expected_df, key_columns),
                "genData": get_dataset_stats(generated_df, key_columns),
                "commonData": {
                    "keyColumns": key_columns,
                    "columnComparisons": {
                        col: {
                            "matches": summary_row[f"{col}_match_count"],
                            "mismatches": summary_row[f"{col}_mismatch_count"],
                        }
                        for col in set(expected_df.columns)
                        .intersection(set(generated_df.columns))
                        .intersection(set(value_columns))
                    },
                    "rowsMatchingCount": rows_matching,
                    "rowsMismatchingCount": rows_not_matching,
                    "keyColumnsMatchCount": summary_row["key_columns_match_count"],
                    "keyColumnsMismatchCount": summary_row[
                        "key_columns_mismatch_count"
                    ],
                },
            },
        }

        if is_serverless:
            # printing diff summary to support serverless
            # do not print if not serverless
            print(json.dumps(diff_summary))
        return diff_summary

    @classmethod
    def clean_joined_df(cls, joined_df, key_columns, value_columns, left_df, right_df):
        """
        Transforms the joined DataFrame into a cleaned DataFrame with the following structure:

        - For each key column: selects the value from the coalesced key column.
        - For each value column (from the union of left and right values):
            • If the compared field (from 'compared_values') is True (i.e. the left and right values match),
              then include an array with a single element (the common value).
            • If not and the column exists in both DataFrames, include an array with both values [left_value, right_value].
            • If the column exists only in one DataFrame, then include an array with the available value only.
        - Also preserves the 'row_matches', 'presence_in_left', and 'presence_in_right' columns.

        Example output schema for a given row:
        ┌───────────┬───────────┬──────────────────┬─────────────────┬─────────────────────┬─────────────────────┬─────────────────────┐
        │ FirstName │ LastName  │      Class       │     Region      │   row_matches       │  presence_in_left   │  presence_in_right  │
        │           │           │  (array<double>) │ (array<string>) │   (boolean)         │   (boolean)         │   (boolean)         │
        │           │           │      ...         │     ...         │                     │                     │                     │
        └───────────┴───────────┴──────────────────┴─────────────────┴─────────────────────┴─────────────────────┴─────────────────────┘
        (Each value column becomes an array of either one or two elements.)
        """
        select_exprs = []

        # Add key columns directly.
        for col_name in key_columns:
            select_exprs.append(F.col(col_name))

        # For each value column, decide whether to create an array
        # with one value (if only exists in one DataFrame, or if left and right match)
        # or two values (if they differ and exist in both DataFrames).
        for col_name in value_columns:
            if col_name in left_df.columns and col_name in right_df.columns:
                select_exprs.append(
                    F.when(
                        F.col(DataFrameDiff.prophecy_sc("compared_values", col_name))
                        == True,
                        F.array(
                            F.col(DataFrameDiff.prophecy_sc("left_values", col_name))
                        ),
                    )
                    .otherwise(
                        F.array(
                            F.col(DataFrameDiff.prophecy_sc("left_values", col_name)),
                            F.col(DataFrameDiff.prophecy_sc("right_values", col_name)),
                        )
                    )
                    .alias(col_name)
                )
            elif col_name in left_df.columns:
                select_exprs.append(
                    F.array(
                        F.col(DataFrameDiff.prophecy_sc("left_values", col_name))
                    ).alias(col_name)
                )
            elif col_name in right_df.columns:
                select_exprs.append(
                    F.array(
                        F.col(DataFrameDiff.prophecy_sc("right_values", col_name))
                    ).alias(col_name)
                )

        # Append the additional columns.
        select_exprs.append(F.col("row_matches"))
        select_exprs.append(F.col("presence_in_left"))
        select_exprs.append(F.col("presence_in_right"))

        return joined_df.select(*select_exprs)

    @classmethod
    def create_diff(
        cls,
        expected_df,
        generated_df,
        key_columns,
        diff_key,
        column_subset=None,
        join_type: str = "full_outer",
    ):
        # First, validate that all key columns exist in both full DataFrames.
        missing_in_expected = [
            col for col in key_columns if col not in expected_df.columns
        ]
        missing_in_generated = [
            col for col in key_columns if col not in generated_df.columns
        ]

        if missing_in_expected or missing_in_generated:
            error_message = "Key column validation failed:\n"

            if missing_in_generated:
                error_message += f"Key columns missing in generated dataset: {missing_in_generated}\n"
                error_message += (
                    f"Available columns in generated dataset: {generated_df.columns}\n"
                )

            if missing_in_expected:
                error_message += (
                    f"Key columns missing in expected dataset: {missing_in_expected}\n"
                )
                error_message += (
                    f"Available columns in expected dataset: {expected_df.columns}\n"
                )

            raise ValueError(error_message)

        # If a column_subset is provided, perform additional checks.
        if column_subset is not None:
            # Ensure that all key columns are in column_subset.
            missing_keys = set(key_columns) - set(column_subset)
            if missing_keys:
                raise ValueError(
                    f"Key columns {list(missing_keys)} must be included in column_subset."
                )

            # Check that all columns in column_subset exist in both DataFrames.
            missing_expected = set(column_subset) - set(expected_df.columns)
            missing_generated = set(column_subset) - set(generated_df.columns)
            error_msgs = []
            if missing_expected:
                error_msgs.append(
                    f"Columns missing in expected dataset: {list(missing_expected)}"
                )
            if missing_generated:
                error_msgs.append(
                    f"Columns missing in generated dataset: {list(missing_generated)}"
                )
            if error_msgs:
                raise ValueError(" ".join(error_msgs))

            # Use the subset for the diff computation.
            processed_expected_df = expected_df.select(*column_subset)
            processed_generated_df = generated_df.select(*column_subset)
        else:
            processed_expected_df = expected_df
            processed_generated_df = generated_df

        # Determine the value columns for diff using the (possibly subsetted) DataFrames.
        value_columns = cls.get_value_columns(
            processed_expected_df, processed_generated_df, key_columns
        )

        # Create the joined DataFrame after splitting on primary key uniqueness.
        joined_df = cls.create_joined_df(
            generated_df=cls.split_df_by_pk_uniqueness(
                processed_generated_df, key_columns=key_columns
            )[0],
            expected_df=cls.split_df_by_pk_uniqueness(
                processed_expected_df, key_columns=key_columns
            )[0],
            key_columns=key_columns,
            value_columns=value_columns,
            join_type=join_type,
        )
        joined_df = cls.add_row_matches_column(joined_df)
        joined_df = cls.add_column_comparison_results(joined_df)
        summary_df = cls.compute_mismatch_summary(joined_df)
        clean_joined_df = cls.clean_joined_df(
            joined_df,
            key_columns,
            value_columns,
            left_df=processed_generated_df,
            right_df=processed_expected_df,
        )

        # Create mismatched dataframe by filtering for non-matching rows only
        mismatched_df = clean_joined_df.filter(F.col("row_matches") == False)

        # Register the diff results with the full DataFrames.
        cls.COMPUTED_DIFFS[diff_key] = {
            DiffKeys.JOINED.value: joined_df,
            DiffKeys.SUMMARY.value: summary_df,
            DiffKeys.CLEANED.value: clean_joined_df,
            DiffKeys.MISMATCHED.value: mismatched_df,  # Only non-matching rows
            DiffKeys.EXPECTED.value: expected_df,  # full expected DataFrame registered.
            DiffKeys.GENERATED.value: generated_df,  # full generated DataFrame registered.
            DiffKeys.KEY_COLUMNS.value: key_columns,
            DiffKeys.VALUE_COLUMNS.value: value_columns,
        }

    @classmethod
    def datasampleloader_register(cls, diff_key: str, _type: DiffKeys) -> str:
        from .datasampleloader import DataSampleLoaderLib

        diff_entry = cls.COMPUTED_DIFFS[diff_key]
        df = diff_entry[_type.value]
        dsl_key = str(uuid.uuid4())
        DataSampleLoaderLib.register(key=dsl_key, df=df, create_truncated_columns=False)
        return dsl_key
