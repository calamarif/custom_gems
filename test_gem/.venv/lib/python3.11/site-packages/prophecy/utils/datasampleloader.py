from typing import Optional, Dict, Tuple, List, Iterator
from pyspark.sql import DataFrame, Row, functions as F, SparkSession
from pyspark.sql.types import (
    StructType,
    StringType,
    ArrayType,
    MapType,
    BinaryType,
    TimestampType,
    DateType,
    DecimalType,
    DoubleType,
    IntegerType,
)
from datetime import datetime, date, timedelta
from decimal import Decimal
import json


# Copy of class from prophecy initialize.py
class ComprehensiveJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, "_asdict"):  # To handle nested data types
            return obj._asdict()
        elif hasattr(obj, "__dict__"):  # To handle nested data types
            return obj.__dict__
        try:
            # Use the default serialization for standard objects
            return super(ComprehensiveJSONEncoder, self).default(obj)
        except TypeError:
            # Fallback: Convert any unhandled objects to strings
            return f"Preview for `{type(obj).__name__}` data type not supported"


# Conditionally import TimestampNTZType which is only available in Spark 3.4+
try:
    from pyspark.sql.types import TimestampNTZType

    HAS_TIMESTAMP_NTZ = True
except ImportError:
    # Fallback for older Spark versions
    HAS_TIMESTAMP_NTZ = False

    # Define a placeholder class for type checking
    class TimestampNTZType(TimestampType):
        pass


# Conditionally import DayTimeIntervalType which is only available in newer Spark versions
try:
    from pyspark.sql.types import DayTimeIntervalType

    HAS_DAYTIME_INTERVAL = True
except ImportError:
    # Fallback for older Spark versions
    HAS_DAYTIME_INTERVAL = False

    # Define a placeholder class for type checking
    class DayTimeIntervalType(object):
        pass


class DataSampleLoaderLib:

    MAX_ROWS = 10000
    PAYLOAD_SIZE_LIMIT = 1024 * 1024 * 2.5
    CHAR_LIMIT = 1024 * 200

    @classmethod
    def initialize(
        cls,
        MAX_ROWS: int = None,
        PAYLOAD_SIZE_LIMIT: int = None,
        CHAR_LIMIT: int = None,
        **kwargs,
    ):
        if MAX_ROWS is not None:
            cls.MAX_ROWS = MAX_ROWS
        if PAYLOAD_SIZE_LIMIT is not None:
            cls.PAYLOAD_SIZE_LIMIT = PAYLOAD_SIZE_LIMIT
        if CHAR_LIMIT is not None:
            cls.CHAR_LIMIT = CHAR_LIMIT

        # Can keep this but this can cause issues across releases
        # for key, value in kwargs.items():
        #     setattr(cls, key, value)

    # Class-level variables (shared state)
    _dataframes_map: Dict[str, Tuple[DataFrame, bool, int]] = (
        {}
    )  # Map to store registered DataFrames
    _row_cache: List = []  # Cache for storing rows of the DataFrame
    _cached_dataframe_schema: Optional[StructType] = (
        None  # Schema of the cached DataFrame
    )
    _cached_dataframe_key: Optional[str] = None  # Key of the cached DataFrame
    _real_dataframe_offset: int = 0  # Offset for the real DataFrame

    @classmethod
    def interim_key(cls, component: str, port: str, run_id=None) -> str:
        run_id_part = f"__{run_id}" if run_id else ""
        return f"{component}__{port}{run_id_part}_interim"

    @classmethod
    def interim_key_dx(cls, component: str, port: str, run_id=None) -> str:
        run_id_part = f"__{run_id}" if run_id else ""
        return f"{component}__{port}{run_id_part}_interim_dx"

    @classmethod
    def _get_entry_from_dataframes_map(cls, key: str) -> Tuple[DataFrame, bool, int]:
        return cls._dataframes_map.get(key, (None, False, cls.MAX_ROWS))

    @classmethod
    def _get_json_encoded_len(cls, schema: StructType) -> int:
        # We want to restrict the overall payload size to 2MB
        # Easiest way of doing that with built-in functionality is to look at JSON representation of a Row
        # Since, the JSON string would have field names as well, along with quotes and colon,
        # we can subtract that while calculating the payload size
        # Nested fields (schemas) are not considered for now - to keep the calculation simple
        total_fields = len(schema.fields)
        fields_name_len = 0
        try:
            for f in schema.fields:
                fields_name_len += len(f.name)
        except Exception as e:
            print("calculating fields name length", e)
            fields_name_len = total_fields * 5

        return fields_name_len + (3 * total_fields)

    @classmethod
    def _cache_dataframe_rows(
        cls,
        df: DataFrame,
        create_truncated_columns: bool,
        df_offset: int,
        limit: int,
        use_collect: bool,
    ) -> None:

        # Copy of function from prophecy initialize.py
        def preprocess_data(obj):
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
            elif isinstance(obj, (timedelta)):
                return str(obj)
            elif isinstance(obj, UUID):
                return str(obj)
            elif isinstance(obj, (bytes, bytearray)):
                return base64.b64encode(obj).decode("utf-8")
            elif isinstance(obj, complex):
                return {"real": obj.real, "imag": obj.imag}
            elif isinstance(obj, (list, tuple)):
                return [preprocess_data(item) for item in obj]
            elif isinstance(obj, set):
                return [preprocess_data(item) for item in obj]
            elif isinstance(obj, frozenset):
                return [preprocess_data(item) for item in obj]
            elif hasattr(obj, "_asdict"):  # For namedtuples
                return preprocess_data(obj._asdict())
            elif hasattr(obj, "__dict__"):  # For general custom objects
                return preprocess_data(obj.__dict__)
            elif isinstance(obj, dict):
                return {key: preprocess_data(value) for key, value in obj.items()}
            else:
                return obj

        cls._row_cache.clear()

        df_new = (
            cls._create_truncated_columns_dataframe(df)
            if create_truncated_columns
            else df
        )
        cls._cached_dataframe_schema = df_new.schema

        # "offset" is available from Spark 3.4 onwards
        # Using limit(dfOffset + limit).tail(limit) for older versions
        iterator: Iterator[Row] = None
        try:
            if use_collect:
                iterator = iter(df_new.offset(df_offset).limit(limit).collect())
            else:
                iterator = df_new.offset(df_offset).limit(limit).toLocalIterator()
        except Exception as e:
            iterator = iter(df_new.limit(df_offset + limit).tail(limit))
        finally:
            cls._real_dataframe_offset = df_offset

        json_encoded_len_to_subtract = cls._get_json_encoded_len(df.schema)

        size_so_far = 0
        try:
            for row in iterator:
                try:
                    row_json = json.dumps(row.asDict(recursive=True))
                except:
                    row_json = json.dumps(
                        preprocess_data(row.asDict()), cls=ComprehensiveJSONEncoder
                    )
                row_size = len(row_json.encode("utf-8")) - json_encoded_len_to_subtract
                # Stop if we exceed constraints
                if (
                    size_so_far + row_size > cls.PAYLOAD_SIZE_LIMIT
                    and len(cls._row_cache) != 0
                ):
                    break

                cls._row_cache.append(row_json)
                size_so_far += row_size
        except Exception as e:
            print(e)

    @classmethod
    def _create_truncated_columns_dataframe(
        cls, df: DataFrame, limit: int = CHAR_LIMIT
    ) -> DataFrame:
        """Create DataFrame with truncated columns."""

        # Quick check if truncation is needed
        truncatable_types = (StringType, ArrayType, MapType, StructType, BinaryType)
        if not any(
            isinstance(field.dataType, truncatable_types) for field in df.schema.fields
        ):
            return df

        # Process binary columns first
        # binary_columns = [
        #     field.name for field in df.schema.fields
        #     if isinstance(field.dataType, BinaryType)
        # ]
        # result_df = df.drop(*binary_columns) if binary_columns else df

        # Build all column expressions at once
        for field in df.schema.fields:
            if isinstance(field.dataType, truncatable_types):
                if isinstance(field.dataType, StringType):
                    substitute_col = F.col(f"`{field.name}`")
                elif isinstance(field.dataType, BinaryType):
                    substitute_col = F.base64(F.col(f"`{field.name}`"))
                else:
                    substitute_col = F.to_json(F.col(f"`{field.name}`"))

                df = df.withColumn(
                    f"`{field.name}`",
                    F.when(
                        F.length(F.coalesce(substitute_col, F.lit(""))) > limit,
                        F.concat(
                            F.substring(substitute_col, 1, limit - 3), F.lit("...")
                        ),
                    )
                    .otherwise(substitute_col)
                    .cast("string"),
                )

        return df

    @classmethod
    def register(
        cls,
        key: str,
        df: DataFrame,
        limit: int = MAX_ROWS,
        create_truncated_columns: bool = True,
    ) -> DataFrame:
        """Register a DataFrame with optional truncation."""

        cls._dataframes_map[key] = (df, create_truncated_columns, limit)
        if cls._cached_dataframe_key == key:
            cls._clear_cache()

        return df

    @classmethod
    def get_cached_data(
        cls, key: str, cache_offset: int, df_offset: int, use_collect: bool
    ) -> Optional[List]:
        """Get DataFrame for display with caching."""
        df, create_truncated_columns, limit = cls._get_entry_from_dataframes_map(key)

        if df is None:
            return None

        if (
            cls._cached_dataframe_key != key
            or not cls._row_cache
            or len(cls._row_cache) == 0
            or df_offset != cls._real_dataframe_offset
        ):
            cls._cached_dataframe_key = key
            cls._cache_dataframe_rows(
                df, create_truncated_columns, df_offset, limit, use_collect
            )

        safe_offset = cache_offset if cache_offset > 0 else 0
        return cls._row_cache[safe_offset:]

    @classmethod
    def _get_spark_session(cls):
        """Get the current Spark session or create a new one."""
        return SparkSession.builder.getOrCreate()

    @classmethod
    def _convert_to_schema_type(cls, value, field_type):
        if value is None:
            return None

        try:
            # Check both types separately to handle older Spark versions
            if isinstance(field_type, TimestampType):
                if isinstance(value, str):
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                return value
            # Only check TimestampNTZType if it's available (Spark 3.4+)
            elif HAS_TIMESTAMP_NTZ and isinstance(field_type, TimestampNTZType):
                if isinstance(value, str):
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                return value
            elif isinstance(field_type, DateType):
                if isinstance(value, str):
                    return datetime.fromisoformat(value).date()
                return value
            # Only check DayTimeIntervalType if it's available
            elif HAS_DAYTIME_INTERVAL and isinstance(field_type, DayTimeIntervalType):
                if isinstance(value, str):
                    return (
                        timedelta(seconds=float(value))
                        if value.isdigit()
                        else eval(f"timedelta({value})")
                    )
                return value
            elif isinstance(field_type, DecimalType):
                if value in ("Infinity", "-Infinity", "NaN"):
                    return float(value)
                return Decimal(str(value))
            elif isinstance(field_type, DoubleType):
                if value in ("Infinity", "-Infinity", "NaN"):
                    return float(value)
                return float(value)
            elif isinstance(field_type, IntegerType):
                return int(value)
            elif isinstance(field_type, ArrayType):
                return [
                    cls._convert_to_schema_type(item, field_type.elementType)
                    for item in value
                ]
            elif isinstance(field_type, MapType):
                return {
                    k: cls._convert_to_schema_type(v, field_type.valueType)
                    for k, v in value.items()
                }
            elif isinstance(field_type, StructType):
                return {
                    f.name: cls._convert_to_schema_type(value.get(f.name), f.dataType)
                    for f in field_type.fields
                }
            return value
        except (ValueError, TypeError) as e:
            return value

    @classmethod
    def _create_row_from_json(cls, json_str, schema):
        data = json.loads(json_str)

        converted_data = {}
        for field in schema.fields:
            field_value = data.get(field.name)
            converted_data[field.name] = cls._convert_to_schema_type(
                field_value, field.dataType
            )

        return Row(**converted_data)

    @classmethod
    def get_dataframe_for_display(
        cls,
        key: str,
        cache_offset: int = 0,
        df_offset: int = 0,
        use_collect: bool = True,
    ) -> Optional[DataFrame]:
        """Get DataFrame for display with caching."""
        data = cls.get_cached_data(key, cache_offset, df_offset, use_collect)

        if data is None:
            return None

        # Convert JSON rows back to dict
        rows = [
            cls._create_row_from_json(row, cls._cached_dataframe_schema) for row in data
        ]

        spark = cls._get_spark_session()
        return spark.createDataFrame(data=rows, schema=cls._cached_dataframe_schema)

    @classmethod
    def get_payload(
        cls, key: str, job: str, df_offset: int = 0, use_collect: bool = True
    ) -> Optional[str]:
        """Get payload with proper JSON handling."""
        data = cls.get_cached_data(key, 0, df_offset, use_collect)
        df, _, _ = cls._get_entry_from_dataframes_map(key)

        if data is None or df is None:
            return None

        try:
            schema_json = df.schema.json()
            data_json = f'[{",".join(data)}]'  # json.dumps(data)

            spark = cls._get_spark_session()
            result = spark.createDataFrame(
                [(job, schema_json, data_json)], ["job", "schema", "data"]
            )
            try:
                return result.toJSON().first()
            except Exception as e:
                from pyspark.sql.functions import struct, col, to_json

                row = result.select(to_json(struct(col("*")))).first()
                if row is not None:
                    # Extract the string from the Row (first value)
                    return row[0]
                else:
                    return None
        except Exception as e:
            print(f"Error creating payload: {str(e)}")  # Log error before raising
            raise ValueError(f"Error creating payload: {str(e)}")

    @classmethod
    def _clear_cache(cls) -> None:
        """Clear cached dataframe rows."""
        cls._row_cache.clear()
        cls._cached_dataframe_key = None
        cls._real_dataframe_offset = 0

    @classmethod
    def clear(cls) -> None:
        """Clear cached dataframe rows."""
        cls._clear_cache()
        cls._dataframes_map = {}

    @classmethod
    def get_original_schema_for_dataframe(
        cls,
        key: str,
    ) -> Optional[DataFrame]:
        """Get DataFrame for display with caching."""
        df, _, _ = cls._get_entry_from_dataframes_map(key)

        if df is None:
            return None

        return df.sparkSession.createDataFrame(data=[], schema=df.schema)

    @classmethod
    def display(cls, df: Optional[DataFrame]) -> None:
        """Calls Databricks display function."""
        if df != None:
            display(df)
