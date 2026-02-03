from pyspark.sql import Column, DataFrame, Row, SparkSession, functions as F
from pyspark.sql.types import (
    DataType,
    StringType,
    NumericType,
    DateType,
    TimestampType,
    ArrayType,
    StructType,
)
from pyspark.sql.types import *
import json
from typing import List, Optional, Any
import builtins
import math


class DataProfiler:

    class Bin:
        def __init__(
            self,
            bucket_number: int,
            is_bucketed: bool,
            start_value: Optional[str],
            end_value: Optional[str],
            count: int,
            percentage: float,
            is_others: Optional[bool] = None,
        ):
            self.bucket_number = bucket_number
            self.is_bucketed = is_bucketed
            self.start_value = start_value
            self.end_value = end_value
            self.count = count
            self.percentage = percentage
            self.is_others = is_others

    class TopBin(Bin):
        def __init__(
            self,
            bucket_number: int,
            start_value: Optional[str],
            count: int,
            percentage: float,
            is_others: Optional[bool] = None,
        ):
            super().__init__(
                bucket_number=bucket_number,
                is_bucketed=False,
                start_value=start_value,
                end_value=None,
                count=count,
                percentage=percentage,
                is_others=is_others,
            )

    class HistogramBin(Bin):
        def __init__(
            self,
            bucket_number: int,
            start_value: Optional[str],
            end_value: Optional[str],
            count: int,
            percentage: float,
        ):
            super().__init__(
                bucket_number=bucket_number,
                is_bucketed=True,
                start_value=start_value,
                end_value=end_value,
                count=count,
                percentage=percentage,
                is_others=None,
            )

    class Profile:
        def __init__(
            self,
            column_name: str,
            data_type: str,
            unsupported_data_type: Optional[bool] = None,
            unique_count: int = 0,
            all_values_unique: bool = False,
            null_count: int = 0,
            null_percentage: float = 0.0,
            blank_count: int = 0,
            blank_percentage: float = 0.0,
            non_blank_non_null_count: int = 0,
            non_blank_non_null_percentage: float = 0.0,
            avg_length: Optional[float] = None,
            shortest_value: Optional[str] = None,
            longest_value: Optional[str] = None,
            min_value: Optional[str] = None,
            max_value: Optional[str] = None,
            most_frequent_value: Optional[str] = None,
            most_frequent_count: int = 0,
            least_frequent_value: Optional[str] = None,
            least_frequent_count: int = 0,
            top_values: Optional[List["DataProfiler.TopBin"]] = None,
            histograms: Optional[List["DataProfiler.HistogramBin"]] = None,
        ):
            self.column_name = column_name
            self.data_type = data_type
            self.unsupported_data_type = unsupported_data_type
            self.unique_count = unique_count
            self.all_values_unique = all_values_unique
            self.null_count = null_count
            self.null_percentage = null_percentage
            self.blank_count = blank_count
            self.blank_percentage = blank_percentage
            self.non_blank_non_null_count = non_blank_non_null_count
            self.non_blank_non_null_percentage = non_blank_non_null_percentage
            self.avg_length = avg_length
            self.shortest_value = shortest_value
            self.longest_value = longest_value
            self.min_value = min_value
            self.max_value = max_value
            self.most_frequent_value = most_frequent_value
            self.most_frequent_count = most_frequent_count
            self.least_frequent_value = least_frequent_value
            self.least_frequent_count = least_frequent_count
            self.top_values = top_values or []
            self.histograms = histograms or []

    @classmethod
    def to_dict(cls, obj):
        if isinstance(obj, list):
            return [cls.to_dict(item) for item in obj]
        elif hasattr(obj, "__dict__"):
            return {key: cls.to_dict(value) for key, value in obj.__dict__.items()}
        else:
            return obj  # Return primitive values as-is

    class EnhancedJSONEncoder(json.JSONEncoder):
        """Custom JSON encoder to handle complex data types"""

        def default(self, obj):
            if hasattr(obj, "_asdict"):
                return obj._asdict()
            elif hasattr(obj, "__dict__"):
                return obj.__dict__
            try:
                return super().default(obj)
            except TypeError:
                return f"Preview for `{type(obj).__name__}` not supported"

    @classmethod
    def _preprocess_json_data(cls, obj: Any) -> Any:
        """
        Preprocess various data types for JSON serialization
        """
        import base64
        import math
        from decimal import Decimal
        from datetime import datetime, date, timedelta
        from uuid import UUID

        if isinstance(obj, Decimal):
            if math.isinf(obj):
                return "Infinity" if obj > 0 else "-Infinity"
            elif math.isnan(obj):
                return "NaN"
            else:
                return str(obj)
        elif isinstance(obj, float):
            if math.isinf(obj):
                return "Infinity" if obj > 0 else "-Infinity"
            elif math.isnan(obj):
                return "NaN"
            else:
                return obj
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, timedelta):
            return str(obj.total_seconds())
        elif isinstance(obj, UUID):
            return str(obj)
        elif isinstance(obj, (bytes, bytearray)):
            return base64.b64encode(obj).decode("utf-8")
        elif isinstance(obj, complex):
            return {"real": obj.real, "imag": obj.imag}
        elif isinstance(obj, (list, tuple, set, frozenset)):
            return [cls._preprocess_json_data(item) for item in obj]
        elif hasattr(obj, "_asdict"):
            return cls._preprocess_json_data(obj._asdict())
        elif hasattr(obj, "__dict__"):
            return cls._preprocess_json_data(obj.__dict__)
        elif isinstance(obj, dict):
            return {key: cls._preprocess_json_data(value) for key, value in obj.items()}
        else:
            return obj

    @classmethod
    def _safe_json_serialize(cls, data: Any) -> str:
        """
        Safely serialize data to JSON, handling complex types
        """
        try:
            return json.dumps(data)
        except (TypeError, OverflowError):
            try:
                return json.dumps(
                    cls._preprocess_json_data(data), cls=cls.EnhancedJSONEncoder
                )
            except:
                return str(data)

    @staticmethod
    def _is_timestamp_type(col_type: DataType) -> bool:
        if isinstance(col_type, TimestampType):
            return True

        try:
            # For TimestampNTZType (got added in 3.4)
            from pyspark.sql.types import TimestampNTZType

            return isinstance(col_type, TimestampNTZType)
        except:
            return False

    @staticmethod
    def _is_string_type(col_type: DataType) -> bool:
        if isinstance(col_type, StringType):
            return True
        
        try:
            # For CharType and VarcharType (got added in 3.4 PySpark)
            from pyspark.sql.types import CharType, VarcharType
            return isinstance(col_type, (CharType, VarcharType))
        except:
            return False

    @staticmethod
    def _is_aggregatable_type(col_type: DataType) -> bool:
        if isinstance(
            col_type, (NumericType, DateType)
        ) or DataProfiler._is_timestamp_type(col_type):
            return True

        try:
            # For DayTimeIntervalType and YearMonthIntervalType (got added in 3.2)
            from pyspark.sql.types import DayTimeIntervalType, YearMonthIntervalType

            return isinstance(col_type, (DayTimeIntervalType, YearMonthIntervalType))
        except:
            return False

    @staticmethod
    def _is_skippable_type(col_type: DataType) -> bool:
        if DataProfiler._is_string_type(col_type) or DataProfiler._is_aggregatable_type(col_type):
            return False
        
        if isinstance(col_type, BooleanType):
            return False
        
        return True

    @staticmethod
    def _get_first_value_else_default(value_arr: List[Row]):
        if value_arr:
            value = value_arr[0][0]
            count = value_arr[0][1]
            return (str(value) if value is not None else None, count)
        return (None, 0)

    @staticmethod
    def _percentage(count: int, total_count: int) -> float:
        return (
            0.0
            if total_count == 0
            else builtins.round((float(count) / total_count) * 100.0, 2)
        )

    @staticmethod
    def _row_to_histogram_bin(row: Row, total_count: int) -> HistogramBin:
        # TODO: Implement type-specific handling if needed
        count = row["count"]
        return DataProfiler.HistogramBin(
            bucket_number=row["bucket"],
            start_value=str(row["start_value"]),
            end_value=str(row["end_value"]),
            count=count,
            percentage=DataProfiler._percentage(count, total_count),
        )

    @staticmethod
    def _aggregates_for_string_type(sanitized_col: Column):
        # min_by, max_by functions for String type got added in 3.3
        try:
            return [
                F.min_by(sanitized_col, F.length(sanitized_col)).alias("shortest_value"),
                F.max_by(sanitized_col, F.length(sanitized_col)).alias("longest_value"),
            ]
        except:
            return []

    @classmethod
    def _profile_columns(
        cls,
        spark: SparkSession,
        df: DataFrame,
        top_n: int = 50,
        num_buckets: int = 20,
        expected_cols: Optional[List[str]] = None,
        calculate_histograms: bool = True,
    ) -> List[Profile]:
        """
        Generate profiling information for all columns in a Spark DataFrame.

        Args:
            df: Spark DataFrame
            top_n: Number of top occurring values to return (default 50)
            num_buckets: Buckets for histograms (default 20)
            expected_cols: List of columns on which profiling is needed

        Returns:
            DataFrame containing profiling information.
        """

        if spark is None or df is None:
            return None

        columns_info = [(field.name, field.dataType) for field in df.schema.fields]
        profile_data: List[DataProfiler.Profile] = []

        for col_name, col_type in columns_info:
            if cls._is_skippable_type(col_type):
                profile = DataProfiler.Profile(
                    column_name=col_name,
                    data_type=col_type.simpleString(),
                    unsupported_data_type=True,
                )
                profile_data.append(profile)
                continue

            if expected_cols is not None and col_name not in expected_cols:
                continue

            sanitized_col = F.col(f"`{col_name}`")
            is_agg_type = cls._is_aggregatable_type(col_type)
            is_str_type = cls._is_string_type(col_type)
            is_min_max_agg_type = is_agg_type or is_str_type

            agg_cols = [
                F.count(sanitized_col).alias("total_count"),
                F.count(F.when(sanitized_col.isNull(), True)).alias("null_count"),
                F.countDistinct(sanitized_col).alias("unique_count"),
                (
                    F.min(sanitized_col).alias("min_value")
                    if is_min_max_agg_type
                    else F.lit(None).alias("min_value")
                ),
                (
                    F.max(sanitized_col).alias("max_value")
                    if is_min_max_agg_type
                    else F.lit(None).alias("max_value")
                ),
            ]

            if is_str_type:
                agg_cols.extend(
                    [
                        F.count(F.when(F.trim(sanitized_col) == "", True)).alias(
                            "blank_count"
                        ),
                        F.round(F.avg(F.length(sanitized_col)), 2).alias("avg_length"),
                    ]
                )
                agg_cols.extend(cls._aggregates_for_string_type(sanitized_col))

            # Compute basic statistics
            basic_stats = df.agg(*agg_cols).collect()[0]

            # Compute null and total counts
            null_count = basic_stats["null_count"] or 0
            total_count = basic_stats["total_count"] + null_count

            # Compute blank count (only for string types)
            blank_count = (basic_stats["blank_count"] or 0) if is_str_type else 0

            # Compute top N values and least frequent value
            value_counts_expr = df.filter(sanitized_col.isNotNull())
            if is_str_type:
                value_counts_expr.filter(F.trim(sanitized_col) != "")

            value_counts = (
                value_counts_expr.groupBy(sanitized_col)
                .count()
                .orderBy(F.col("count").desc(), sanitized_col.asc())
            )

            limit_top_n = 1 if is_agg_type else (top_n - 1)

            top_values = value_counts.limit(limit_top_n).collect()

            # Structure the results
            structured_top_values = []
            most_frequent_value = None
            most_frequent_count = None
            least_frequent_value = None
            least_frequent_count = None

            total_top_values_count = 0
            for index, row in enumerate(top_values):
                value = row[col_name]
                count = row["count"]
                total_top_values_count += count

                if index == 0:
                    most_frequent_value = str(value) if value is not None else None
                    most_frequent_count = count

                structured_top_values.append(
                    DataProfiler.TopBin(
                        bucket_number=index,
                        start_value=str(value) if value is not None else None,
                        count=count,
                        percentage=cls._percentage(count, total_count),
                    )
                )

            # Add 'Others' bin
            others_count = total_count - total_top_values_count
            if others_count != 0:
                structured_top_values.append(
                    DataProfiler.TopBin(
                        bucket_number=len(top_values),
                        start_value=None,
                        count=others_count,
                        percentage=cls._percentage(others_count, total_count),
                        is_others=True,
                    )
                )

            least_frequent_rows = (
                value_counts.orderBy(F.col("count").asc(), sanitized_col.asc())
                .limit(1)
                .collect()
            )
            if least_frequent_rows:
                least_frequent_row = least_frequent_rows[0]
                value = least_frequent_row[col_name]
                count = least_frequent_row["count"]
                least_frequent_value = str(value) if value is not None else None
                least_frequent_count = count

            min_val, max_val = basic_stats["min_value"], basic_stats["max_value"]

            histograms: List[DataProfiler.HistogramBin] = []

            # Generate histograms for numeric, date, and timestamp columns
            if calculate_histograms and min_val is not None and max_val is not None:
                # Filter to non-null values for histogram
                filtered_df = df.filter(sanitized_col.isNotNull())

                if isinstance(col_type, NumericType):
                    # Calculate bucket size
                    range_value = max_val - min_val + 1
                    if isinstance(
                        col_type, (ByteType, ShortType, IntegerType, LongType)
                    ):
                        bucket_size = builtins.max(
                            1, int(math.ceil(range_value / num_buckets))
                        )
                    else:
                        bucket_size = math.ceil(range_value / num_buckets)
                        if bucket_size == 0:
                            bucket_size = 0.1

                    # Create bucket expression
                    bucket_expr = F.floor((sanitized_col - min_val) / bucket_size).cast(
                        "int"
                    )

                    # Generate histogram
                    histogram_df = (
                        filtered_df.groupBy(bucket_expr.alias("bucket"))
                        .agg(F.count("*").alias("count"))
                        .select(
                            F.col("bucket").alias("bucket_number"),
                            (min_val + F.col("bucket") * bucket_size).alias(
                                "start_value"
                            ),
                            (min_val + (F.col("bucket") + 1) * bucket_size).alias(
                                "end_value"
                            ),
                            F.col("count"),
                        )
                        .orderBy("bucket_number")
                    )

                elif isinstance(col_type, DateType):
                    # Calculate date range in days
                    days_range = F.datediff(F.lit(max_val), F.lit(min_val)) + 1
                    bucket_size_days = F.greatest(
                        F.lit(1), F.ceil(days_range / F.lit(num_buckets))
                    ).cast("int")

                    # Create bucket expression for dates
                    bucket_expr = F.floor(
                        F.datediff(sanitized_col, F.lit(min_val)) / bucket_size_days
                    ).cast("int")

                    # Generate histogram for dates
                    histogram_df = (
                        filtered_df.groupBy(bucket_expr.alias("bucket"))
                        .agg(F.count("*").alias("count"))
                        .select(
                            F.col("bucket").alias("bucket_number"),
                            F.date_add(
                                F.lit(min_val), F.col("bucket") * bucket_size_days
                            ).alias("start_value"),
                            F.date_add(
                                F.lit(min_val), (F.col("bucket") + 1) * bucket_size_days
                            ).alias("end_value"),
                            F.col("count"),
                        )
                        .orderBy("bucket_number")
                    )

                elif cls._is_timestamp_type(col_type):
                    # Calculate time range in seconds
                    seconds_range = F.unix_timestamp(F.lit(max_val)) - F.unix_timestamp(
                        F.lit(min_val)
                    ) + 1
                    bucket_size_seconds = F.greatest(
                        F.lit(1), F.ceil(seconds_range / F.lit(num_buckets))
                    ).cast("long")

                    # Create bucket expression for timestamps
                    bucket_expr = F.floor(
                        (
                            F.unix_timestamp(sanitized_col)
                            - F.unix_timestamp(F.lit(min_val))
                        )
                        / bucket_size_seconds
                    ).cast("long")

                    # Generate histogram for timestamps
                    histogram_df = (
                        filtered_df.groupBy(bucket_expr.alias("bucket"))
                        .agg(F.count("*").alias("count"))
                        .select(
                            F.col("bucket").alias("bucket_number"),
                            F.from_unixtime(
                                F.unix_timestamp(F.lit(min_val))
                                + F.col("bucket") * bucket_size_seconds
                            ).alias("start_value"),
                            F.from_unixtime(
                                F.unix_timestamp(F.lit(min_val))
                                + (F.col("bucket") + 1) * bucket_size_seconds
                            ).alias("end_value"),
                            F.col("count"),
                        )
                        .orderBy("bucket_number")
                    )

                else:
                    bucket_expr = None

                if bucket_expr is not None:
                    # Collect histogram data
                    histograms = [
                        DataProfiler.HistogramBin(
                            row["bucket_number"],
                            str(row["start_value"]),
                            str(row["end_value"]),
                            row["count"],
                            percentage=cls._percentage(row["count"], total_count),
                        )
                        for row in histogram_df.collect()
                    ]

            non_blank_non_null_count = total_count - null_count - blank_count
            unique_count = basic_stats["unique_count"]
            profile = DataProfiler.Profile(
                column_name=col_name,
                data_type=col_type.simpleString(),
                unsupported_data_type=False,
                unique_count=unique_count,
                all_values_unique=unique_count == total_count,
                null_count=null_count,
                null_percentage=cls._percentage(null_count, total_count),
                blank_count=blank_count,
                blank_percentage=cls._percentage(blank_count, total_count),
                non_blank_non_null_count=non_blank_non_null_count,
                non_blank_non_null_percentage=cls._percentage(
                    non_blank_non_null_count, total_count
                ),
                avg_length=(
                    basic_stats["avg_length"] if "avg_length" in basic_stats else None
                ),
                shortest_value=(
                    basic_stats["shortest_value"]
                    if "shortest_value" in basic_stats
                    else None
                ),
                longest_value=(
                    basic_stats["longest_value"]
                    if "longest_value" in basic_stats
                    else None
                ),
                min_value=str(min_val or ""),
                max_value=str(max_val or ""),
                most_frequent_value=most_frequent_value,
                most_frequent_count=most_frequent_count,
                least_frequent_value=least_frequent_value,
                least_frequent_count=least_frequent_count,
                top_values=structured_top_values if not is_agg_type else None,
                histograms=histograms,
            )
            profile_data.append(profile)

        return profile_data

    @classmethod
    def profile_columns_as_dataframe(
        cls,
        spark: SparkSession,
        df: DataFrame,
        top_n: int = 50,
        num_buckets: int = 25,
        expected_cols: Optional[List[str]] = None,
        calculate_histograms: bool = True,
    ) -> DataFrame:
        profiles = cls._profile_columns(
            spark=spark,
            df=df,
            top_n=top_n,
            num_buckets=num_buckets,
            expected_cols=expected_cols,
            calculate_histograms=calculate_histograms,
        )

        if profiles is None:
            return None

        # Define schema for TopBin
        bin_schema = StructType(
            [
                StructField("is_bucketed", BooleanType(), False),
                StructField("bucket_number", IntegerType(), False),
                StructField("start_value", StringType(), True),
                StructField("end_value", StringType(), True),
                StructField("count", IntegerType(), False),
                StructField("percentage", FloatType(), False),
                StructField("is_others", BooleanType(), True),
            ]
        )

        schema = StructType(
            [
                StructField("column_name", StringType(), False),
                StructField("data_type", StringType(), False),
                StructField("unsupported_data_type", BooleanType(), True),
                StructField("unique_count", LongType(), True),
                StructField("all_values_unique", BooleanType(), True),
                StructField("null_count", LongType(), True),
                StructField("null_percentage", DoubleType(), True),
                StructField("blank_count", LongType(), True),
                StructField("blank_percentage", DoubleType(), True),
                StructField("non_blank_non_null_count", LongType(), True),
                StructField("non_blank_non_null_percentage", DoubleType(), True),
                StructField("avg_length", DoubleType(), True),
                StructField("shortest_value", StringType(), True),
                StructField("longest_value", StringType(), True),
                StructField("min_value", StringType(), True),
                StructField("max_value", StringType(), True),
                StructField("most_frequent_value", StringType(), True),
                StructField("most_frequent_count", LongType(), True),
                StructField("least_frequent_value", StringType(), True),
                StructField("least_frequent_count", LongType(), True),
                StructField("top_values", ArrayType(bin_schema), True),
                StructField("histograms", ArrayType(bin_schema), True),
            ]
        )

        return spark.createDataFrame(
            [cls.to_dict(profile) for profile in profiles], schema
        )

    @classmethod
    def profile_columns_as_json(
        cls,
        spark: SparkSession,
        df: DataFrame,
        job: str,
        top_n: int = 50,
        num_buckets: int = 25,
        expected_cols: Optional[List[str]] = None,
        calculate_histograms: bool = True,
    ) -> str:
        profiles = cls._profile_columns(
            spark=spark,
            df=df,
            top_n=top_n,
            num_buckets=num_buckets,
            expected_cols=expected_cols,
            calculate_histograms=calculate_histograms,
        )

        if profiles is None:
            return None

        # data = [cls._safe_json_serialize(profile) for profile in profiles]
        # data_json = f'[{",".join(data)}]'

        payload = {"job": job, "schema": "", "data": profiles}

        return cls._safe_json_serialize(payload)
