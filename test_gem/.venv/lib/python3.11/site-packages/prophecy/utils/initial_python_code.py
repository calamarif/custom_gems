# EM - Disabled, DSM - Vanilla


from datetime import datetime
import time
from functools import wraps
import logging
import os
import sys
import re
import base64 as base64_std

# Attempt to initialize it using SparkSessionProxy for serverless
try:
    from server_rest import SparkSessionProxy

    spark = SparkSessionProxy.get_instance()
except Exception as e:
    print(f"Failed to initialize 'spark' instance. Error: {e}")
    raise Exception("Failed to initialize 'spark' instance")

# Monkey Patch Caching
try:
    from pyspark.sql.connect.dataframe import DataFrame

    DataFrame.cache = lambda self: self
    DataFrame.persist = lambda self: self
    DataFrame.unpersist = lambda self: self
except Exception as e:
    print(f"Failed to monkey patch DataFrame. Error: {e}")


class ProphecyConstants:
    BASE_URL = os.environ["EXECUTION_BASE_URL"]
    TOKEN = ""
    MAX_ROWS = 10000
    PAYLOAD_SIZE_LIMIT = 2621440
    CHAR_LIMIT = 204800


ENABLE_PROPHECY_PERF_TRACKING = (
    os.getenv("ENABLE_PROPHECY_PERF_TRACKING", "false").lower() == "true"
)

# Create a custom logger for this module
prophecy_logger = logging.getLogger("prophecy_logger")
prophecy_logger.setLevel(
    logging.INFO if ENABLE_PROPHECY_PERF_TRACKING else logging.CRITICAL
)

# Avoid duplicate handlers if re-imported in interactive environments
if not prophecy_logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(process)d - %(levelname)s - [%(funcName)s] %(message)s"
    )
    handler.setFormatter(formatter)
    prophecy_logger.addHandler(handler)
    prophecy_logger.propagate = False  # prevent passing to root logger


def prophecy_track_time(label):
    def decorator(func):
        if not ENABLE_PROPHECY_PERF_TRACKING:
            return func  # Return the original function unwrapped

        @wraps(func)
        def wrapper(*args, **kwargs):
            prophecy_logger.info(f"[{label}] Starting...")
            start = time.time()
            result = func(*args, **kwargs)
            end = time.time()
            prophecy_logger.info(f"[{label}] Completed in {end - start:.3f} seconds.")
            return result

        return wrapper

    return decorator


import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import gzip
import json
from pathlib import Path
import logging
from databricks.sdk.runtime import dbutils

try:
    import zstandard as zstd

    prophecy_zstd_compressor = zstd.ZstdCompressor()
except:
    prophecy_zstd_compressor = None

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class HTTPClientError(Exception):
    """Custom exception for HTTP client errors"""

    pass


print("I am coming from inside initial_python_code.py")


def prophecy_str_to_bytes(data):
    return data.encode("utf-8") if isinstance(data, str) else data


class HttpClient:
    DEFAULT_TIMEOUT = (10, 30)  # (connect timeout, read timeout)
    _shared_session = None

    @classmethod
    def _create_session(cls) -> requests.Session:
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=1,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )

        # Configure the adapter with retry strategy and pooling
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=5,
            pool_block=True,
        )

        # Mount the adapter for both HTTP and HTTPS
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update(
            {
                "Accept": "application/json",
                "Authorization": f"Bearer {ProphecyConstants.TOKEN}",
                "Connection": "keep-alive",
            }
        )

        session.params = {"language": "python"}

        return session

    @classmethod
    def _get_session(cls) -> requests.Session:
        if cls._shared_session is None:
            cls._shared_session = cls._create_session()
        return cls._shared_session

    @classmethod
    def _handle_response(cls, response: requests.Response) -> str:
        """Handle the HTTP response and return the response body"""
        try:
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            raise HTTPClientError(f"HTTP Request failed: {str(e)}") from e

    @classmethod
    def _build_url(cls, endpoint: str) -> str:
        """Build the full URL from the endpoint"""
        return f"{ProphecyConstants.BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"

    @classmethod
    def get(cls, endpoint: str) -> str:
        """
        Execute a GET request

        Args:
            endpoint: The API endpoint to call

        Returns:
            The response body as a string

        Raises:
            HTTPClientError: If the request fails
        """
        try:
            response = cls._get_session().get(
                cls._build_url(endpoint), timeout=cls.DEFAULT_TIMEOUT
            )
            return cls._handle_response(response)
        except Exception as e:
            raise HTTPClientError(f"GET request failed: {str(e)}") from e

    @classmethod
    def post(cls, endpoint: str, body: str) -> str:
        """
        Execute a POST request

        Args:
            endpoint: The API endpoint to call
            body: The request body as a string

        Returns:
            The response body as a string

        Raises:
            HTTPClientError: If the request fails
        """
        try:
            response = cls._get_session().post(
                cls._build_url(endpoint),
                data=body,
                headers={"Content-Type": "application/json"},
                timeout=cls.DEFAULT_TIMEOUT,
            )
            return cls._handle_response(response)
        except Exception as e:
            raise HTTPClientError(f"POST request failed: {str(e)}") from e

    @classmethod
    @prophecy_track_time("compress")
    def _compress(cls, body):
        if prophecy_zstd_compressor:
            try:
                return "zstd", prophecy_zstd_compressor.compress(body)
            except Exception:
                pass
        return "gzip", gzip.compress(body)

    @classmethod
    def post_compressed(cls, endpoint: str, body: str) -> str:
        """
        Execute a POST request with gzipped body

        Args:
            endpoint: The API endpoint to call
            body: The request body as a string

        Returns:
            The response body as a string

        Raises:
            HTTPClientError: If the request fails
        """
        try:
            encoding, compressed_data = cls._compress(prophecy_str_to_bytes(body))

            response = cls._get_session().post(
                cls._build_url(endpoint),
                data=compressed_data,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": encoding,
                },
                timeout=cls.DEFAULT_TIMEOUT,
            )
            return cls._handle_response(response)
        except Exception as e:
            raise HTTPClientError(f"Compressed POST request failed: {str(e)}") from e


class ProphecyRequests:
    @staticmethod
    def ping():
        try:
            print(f"Prophecy Base URL: {ProphecyConstants.BASE_URL}")
            response = HttpClient.get("/ping")
            print(f"Ping Response (python): {response}")
        except HTTPClientError as e:
            print(f"Ping Request Failed (python): {str(e)}")

    @staticmethod
    @prophecy_track_time("send_dataframe_payload")
    def send_dataframe_payload(
        key: str, job: str, df_offset: int = 0, use_collect: bool = True
    ):
        try:
            payload = DataSampleLoader.get_payload(key, job, df_offset, use_collect)
            if payload != None:
                response = HttpClient.post_compressed("/interims", payload)
                try:
                    from server_rest import SparkSessionProxy  # lazy import

                    spark_proxy = SparkSessionProxy.get_instance()
                    MetricsCollector.offload_interims(spark_proxy, key, payload)
                except Exception as e1:
                    print(f"Updating interims in memory store failed: {str(e1)}")
        except Exception as e:
            print(f"Interims Request Failed: {str(e)}")
            raise e

    @staticmethod
    @prophecy_track_time('send_dataframe_records_count_payload')
    def send_dataframe_records_count_payload(key: str, job: str):
        try:
            payload = DataSampleLoader.get_records_count_payload(key, job)
            if (payload != None):
                response = HttpClient.post("/interims", payload)
        except Exception as e:
            print(f"Records Count Request Failed: {str(e)}")
            raise e


ProphecyRequests.ping()

from typing import Optional, Dict, Tuple, List, Iterator
from pyspark.sql import DataFrame, Row, functions as F
from pyspark.sql.types import (
    DataType,
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
    StructField,
)
from datetime import datetime, date, timedelta
from decimal import Decimal
import json

try:
    import msgspec

    prophecy_msgspec_encoder = msgspec.json.Encoder()
    prophecy_msgspec_decoder = msgspec.json.Decoder()
except Exception:
    prophecy_msgspec_encoder = None
    prophecy_msgspec_decoder = None


class DataSampleLoader:
    # Constants
    MAX_ROWS: int = ProphecyConstants.MAX_ROWS
    PAYLOAD_SIZE_LIMIT: int = ProphecyConstants.PAYLOAD_SIZE_LIMIT
    CHAR_LIMIT: int = ProphecyConstants.CHAR_LIMIT
    # Class-level variables (shared state)
    _dataframes_map: Dict[str, Tuple[DataFrame, bool, int]] = {}
    _row_cache: List = []
    _cached_dataframe_schema: Optional[StructType] = None
    _cached_dataframe_key: Optional[str] = None
    _real_dataframe_offset: int = 0

    @classmethod
    def _json_serialize(cls, data):
        if prophecy_msgspec_encoder:
            try:
                return prophecy_msgspec_encoder.encode(data)
            except Exception:
                pass
        try:
            return json.dumps(data)
        except Exception:
            return json.dumps(cls._preprocess_data(data), cls=ComprehensiveJSONEncoder)

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
    def _preprocess_data(cls, obj):

        import math
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
            return str(obj.total_seconds())
        elif isinstance(obj, UUID):
            return str(obj)
        elif isinstance(obj, (bytes, bytearray)):
            return base64_std.b64encode(obj).decode("utf-8")
        elif isinstance(obj, complex):
            return {"real": obj.real, "imag": obj.imag}
        elif isinstance(obj, (list, tuple)):
            return [cls._preprocess_data(item) for item in obj]
        elif isinstance(obj, set):
            return [cls._preprocess_data(item) for item in obj]
        elif isinstance(obj, frozenset):
            return [cls._preprocess_data(item) for item in obj]
        elif hasattr(obj, "_asdict"):  # For namedtuples
            return cls._preprocess_data(obj._asdict())
        elif hasattr(obj, "__dict__"):  # For general custom objects
            return cls._preprocess_data(obj.__dict__)
        elif isinstance(obj, dict):
            return {key: cls._preprocess_data(value) for key, value in obj.items()}
        else:
            return obj

    @classmethod
    @prophecy_track_time("_cache_dataframe_rows")
    def _cache_dataframe_rows(
        cls,
        df: DataFrame,
        create_truncated_columns: bool,
        df_offset: int,
        limit: int,
        use_collect: bool,
    ) -> None:
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

        prophecy_logger.info(f"Collected {limit} records")

        json_encoded_len_to_subtract = cls._get_json_encoded_len(df.schema)

        size_so_far = 0
        try:
            for row in iterator:
                row_json = cls._json_serialize(row.asDict(recursive=True))
                row_size = (
                    len(prophecy_str_to_bytes(row_json)) - json_encoded_len_to_subtract
                )
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
                    f"{field.name}",
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
    def _is_timestamp_type(cls, col_type: DataType) -> bool:
        if isinstance(col_type, TimestampType):
            return True

        try:
            # For TimestampNTZType (got added in 3.4)
            from pyspark.sql.types import TimestampNTZType

            return isinstance(col_type, TimestampNTZType)
        except:
            return False

    @classmethod
    def _is_interval_type(cls, col_type: DataType) -> bool:
        try:
            # For DayTimeIntervalType and YearMonthIntervalType (got added in 3.2)
            from pyspark.sql.types import DayTimeIntervalType, YearMonthIntervalType

            return isinstance(col_type, (DayTimeIntervalType, YearMonthIntervalType))
        except:
            return False

    @classmethod
    def _convert_to_schema_type(cls, value, field_type):
        if value is None:
            return None

        try:
            if cls._is_timestamp_type(field_type):
                if isinstance(value, str):
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                return value
            elif isinstance(field_type, DateType):
                if isinstance(value, str):
                    return datetime.fromisoformat(value).date()
                return value
            elif cls._is_interval_type(field_type):
                if isinstance(value, str):
                    try:
                        return timedelta(seconds=float(value))
                    except:
                        return eval(f"timedelta({value})")
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
            elif isinstance(field_type, BinaryType):
                base64_std.b64decode(value.encode("utf-8"))
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
        data = (
            prophecy_msgspec_decoder.decode(json_str)
            if prophecy_msgspec_decoder
            else json.loads(json_str)
        )

        converted_data = {}
        for field in schema.fields:
            field_value = data.get(field.name)
            converted_data[field.name] = cls._convert_to_schema_type(
                field_value, field.dataType
            )

        return Row(**converted_data)

    @classmethod
    @prophecy_track_time("populate_cache")
    def populate_cache(
        cls,
        key: str,
        cache_offset: int = 0,
        df_offset: int = 0,
        use_collect: bool = True,
    ):
        cls.get_cached_data(key, cache_offset, df_offset, use_collect)

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
            # Because of difference in return type of msgspec.encode vs json.dumps
            processed_data = [
                row.decode("utf-8") if isinstance(row, bytes) else row for row in data
            ]
            data_json = f'[{",".join(processed_data)}]'

            result = {"job": job, "schema": schema_json, "data": data_json}

            return cls._json_serialize(result)
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
    @prophecy_track_time("clear")
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

        return spark.createDataFrame(data=[], schema=df.schema)

    @classmethod
    def display(cls, df: Optional[DataFrame]) -> None:
        """
        Lightweight replacement for Databricks' built-in ``display`` that returns the
        exact JSON payload your code receives through the DBX Commands API.
        """

        def to_ddl(dt: DataType) -> str:
            _valid_ident = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

            def quote_ident(name: str) -> str:
                return (
                    name
                    if _valid_ident.fullmatch(name)
                    else f"`{name.replace('`', '``')}`"
                )

            if isinstance(dt, ArrayType):
                return f"array<{to_ddl(dt.elementType)}>"
            if isinstance(dt, MapType):
                return f"map<{to_ddl(dt.keyType)},{to_ddl(dt.valueType)}>"
            if isinstance(dt, StructType):
                inner = ",".join(
                    f"{quote_ident(f.name)}:{to_ddl(f.dataType)}" for f in dt.fields
                )
                return f"struct<{inner}>"
            return dt.simpleString()

        if df is None:
            return

        # ----- schema -----
        # DBX wraps the type and metadata values in *stringified* JSON, so we do the same
        schema: list[dict] = [
            {
                "name": field.name,
                "type": json.dumps(to_ddl(field.dataType)),
                "metadata": json.dumps(field.metadata or {}),
            }
            for field in df.schema  # type: StructField
        ]

        # ----- data -----
        # Collect up to `limit` rows and turn each Row into a plain list
        limit = 100
        data = [list(row) for row in df.limit(limit).collect()]

        display_res = {"data": data, "schema": schema}
        OUTPUT_FILE = "/tmp/display_output.json"
        if not Path(OUTPUT_FILE).exists():
            try:
                serialized = cls._json_serialize(display_res)
                if isinstance(serialized, bytes):
                    serialized = serialized.decode("utf-8")
                Path(OUTPUT_FILE).write_text(serialized, encoding="utf-8")
                logging.info(
                    f"Successfully wrote display_res: {serialized} to {OUTPUT_FILE}"
                )
            except Exception as e:
                logging.error("Failed to write %s: %s", OUTPUT_FILE, e)
        else:
            logging.info(
                f"Skipping writing to %s since file already exists.", OUTPUT_FILE
            )

    @classmethod
    def get_dataframe(
        cls,
        key: str,
    ) -> Optional[DataFrame]:
        """Get DataFrame for display with caching."""
        df, _, _ = cls._get_entry_from_dataframes_map(key)
        return df

    @classmethod
    def get_records_count_payload(cls, key: str, job: str) -> Optional[str]:
        """Get payload with proper JSON handling."""
        df, _, _ = cls._get_entry_from_dataframes_map(key)

        if df is None:
            return None

        try:
            cnt = df.count()
            result = {'job': job, 'schema':'', 'data': str(cnt), 'op': 'count'}
            return cls._json_serialize(result)
        except Exception as e:
            print(f"Error creating payload for records count: {str(e)}")
            raise ValueError(f"Error creating payload: {str(e)}")


import itertools
import re
import json

from pyspark.sql import *  # noqa
from pyspark.sql.functions import *  # noqa
from pyspark.sql.types import *  # noqa

from urllib.parse import urlparse

try:  # uc-shared clusters won't have lib. handling it with a try-catch
    from prophecy.utils import *

    spark.sparkContext
except:
    # Defining dummy instrument decorator for clusters with no libraries or limited access to keep working
    def instrument(function):
        def inner_wrapper(spark, *args, **kwargs):
            try:
                result = function(spark, *args, **kwargs)
                return result
            except Exception as e:
                raise e

        return inner_wrapper


try:
    from prophecy.lookups import *
except:
    pass


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


def preprocess_data(obj):
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
        return base64_std.b64encode(obj).decode("utf-8")
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


class InterimDetail:
    df = None
    filter = None
    sorts = None
    subgraph = None
    pipeline = None
    process = None
    port = None
    is_last_node = None
    cached_df = None
    iterator = None
    final_df = None
    run_id = None

    def __init__(
        self,
        df,
        filter,
        sorts,
        subgraph,
        pipeline,
        process,
        port,
        is_last_node,
        run_id=None,
    ):
        self.df = df
        self.filter = filter
        self.sorts = sorts
        self.subgraph = subgraph
        self.pipeline = pipeline
        self.process = process
        self.port = port
        self.is_last_node = is_last_node
        self.run_id = run_id

    def get_iterator(self):
        if self.iterator == None:
            cached_df = self.df  # SVLESS_UNSUPPORTED # .cache() removed
            self.cached_df = cached_df

            if self.filter:
                cached_df = cached_df.filter(self.filter)

            if self.sorts:
                sorts = []
                for sort in self.sorts:
                    if len(sort) != 2:
                        raise Exception(f"Invalid sort: ${sort}")

                    (field, order) = sort
                    if order == "asc":
                        sorts.append(col(field))
                    else:
                        sorts.append(col(field).desc())

                cached_df = cached_df.sort(*sorts)

            self.final_df = cached_df
            try:
                self.iterator = cached_df.toJSON().toLocalIterator()
            except:
                try:
                    self.iterator = cached_df._jdf.toJSON().toLocalIterator()
                except:

                    def json_data_iterator(data):
                        for row in data:
                            yield json.dumps(
                                preprocess_data(row.asDict()),
                                cls=ComprehensiveJSONEncoder,
                            )

                    collected_data = cached_df.collect()
                    self.iterator = json_data_iterator(collected_data)

        return self.iterator

    # Getting partitions and rows safely. Refer https://app.asana.com/0/1201492708519695/1205426703610074/f
    def partitions(self):
        try:
            return self.df.rdd.getNumPartitions()
        except:
            PyProphecy.log("Error in getting partitions. Retrying it safely.")
            try:
                return self.df.toJSON().getNumPartitions()
            except BaseException as error:
                PyProphecy.log(f"Error in safely getting partitions. error:{error}")
                return 0

    def take(self, count):
        return json.dumps(
            preprocess_data(list(itertools.islice(self.get_iterator(), count))),
            cls=ComprehensiveJSONEncoder,
        )

    def json(self, count=50):
        rows = self.take(count)
        result = {
            "partitions": self.partitions(),
            "port": self.port,
            "process": self.process,
            "records": self.final_df.count(),
            "rows": rows,
            "schema": self.df.schema.json(),
        }

        if self.run_id:
            result["run_id"] = self.run_id

        return result

    @staticmethod
    def schema():
        return StructType(
            [
                StructField("partitions", IntegerType(), False),
                StructField("port", StringType(), False),
                StructField("process", StringType(), False),
                StructField("records", IntegerType(), True),
                StructField("rows", StringType(), True),
                StructField("schema", StringType(), False),
                StructField("run_id", StringType(), True),
            ]
        )

    def get_interim_store_key(self):
        return InterimStore.get_key(self.pipeline, self.process, self.port, self.run_id)

    def clean(self):
        pass
        # Commenting out, since not supported in SVLESS_UNSUPPORTED
        # if self.cached_df:
        #   self.cached_df.unpersist()


class InterimStore:
    _store = {}

    @staticmethod
    def get_key(pipeline, process, port, run_id=None):
        if run_id:
            return f"{pipeline}__{process}__{port}__{run_id}"
        else:
            return f"{pipeline}__{process}__{port}"

    @staticmethod
    def update(interim_detail):
        key = interim_detail.get_interim_store_key()
        if key in InterimStore._store:
            InterimStore._store[key].clean()

        InterimStore._store[key] = interim_detail

    @staticmethod
    def load_more(rows, pipeline, process, port, run_id=None):
        key = InterimStore.get_key(pipeline, process, port, run_id)
        if key in InterimStore._store:
            data = InterimStore._store[key].json(rows)
            # passing schema for all the rows
            display(spark.createDataFrame([data], InterimDetail.schema()))
        else:
            message = f"Interims are not generated for this gem. Please run the pipeline again for python code to be generated. key: {key} not found in {list(InterimStore._store.keys())}"
            raise Exception(message)


class PyProphecy:

    @staticmethod
    def log(message, ex=None):
        # TODO: Tracked in https://app.asana.com/0/1201492708519695/1205475826048726/f
        pass

    @staticmethod
    def encode(s):
        import gzip

        return base64_std.encodebytes(gzip.compress(bytes(s, "utf-8"))).decode("utf-8")

    backticked_name_pattern = re.compile("`(.*?)`")
    simple_name_pattern = re.compile("([a-zA-Z][a-zA-Z_0-9]*)")
    _dbfs_volume_pattern = re.compile(
        "^(?:dbfs:/|/?)(Volumes)(?:/([^/]+))?(?:/([^/]+))?/?$"
    )

    @staticmethod
    def escape(s):
        if PyProphecy.backticked_name_pattern.fullmatch(s):
            return s
        elif PyProphecy.simple_name_pattern.fullmatch(s):
            return s
        else:
            return "`" + s + "`"

    @staticmethod
    def display_functions(catalog, schema, filter):
        if catalog:
            query = (
                "select * from "
                + PyProphecy.escape(catalog)
                + ".information_schema.routines"
            )
            conditions = []
            if schema:
                conditions.append(f"specific_schema = '{schema}'")
            if filter:
                conditions.append(f"specific_name ilike '%{filter}%'")
            # Add conditions to the query if any exist
            if conditions:
                query += " where " + " and ".join(conditions)
            display(spark.sql(query))
        else:
            from functools import reduce

            catalogs = PyProphecy.get_catalog_names()

            def df(c):
                query = (
                    "select * from "
                    + PyProphecy.escape(c)
                    + ".information_schema.routines"
                )
                if filter:
                    query += " where " + f"specific_name ilike '%{filter}%'"
                return spark.sql(query)

            candidates = []
            for catalog in catalogs:
                try:
                    candidates.append(df(catalog))
                except:
                    pass
            if candidates:
                d = reduce(PyProphecy.union, candidates)
            else:
                d = spark.createDataFrame([], StructType([]))
            display(d)

    @staticmethod
    def display_params(catalog, schema, filter):
        if catalog:
            query = (
                "select * from "
                + PyProphecy.escape(catalog)
                + ".information_schema.parameters"
            )
            conditions = []
            if schema:
                conditions.append(f"specific_schema = '{schema}'")
            if filter:
                conditions.append(f"specific_name ilike '%{filter}%'")
            # Add conditions to the query if any exist
            if conditions:
                query += " where " + " and ".join(conditions)
            display(spark.sql(query))
        else:
            from functools import reduce

            catalogs = PyProphecy.get_catalog_names()

            def df(c):
                query = (
                    "select * from "
                    + PyProphecy.escape(c)
                    + ".information_schema.parameters"
                )
                if filter:
                    query += " where " + f"specific_name ilike '%{filter}%'"
                return spark.sql(query)

            candidates = []
            for catalog in catalogs:
                try:
                    candidates.append(df(catalog))
                except:
                    pass
            if candidates:
                d = reduce(PyProphecy.union, candidates)
            else:
                d = spark.createDataFrame([], StructType([]))
            display(d)

    @staticmethod
    def print_catalogs(filter):
        try:
            query = "SHOW CATALOGS"
            if filter:
                query = query + " LIKE '*" + filter + "*' "
            catalogs_as_list = "\n".join(
                [x.catalog for x in spark.sql(query).collect()]
            )
            _result = PyProphecy.encode(catalogs_as_list)
        except:
            _result = PyProphecy.encode("")
        print(_result)
        return _result

    @staticmethod
    def get_databases(catalog, filter):
        try:
            query = "SHOW DATABASES"
            if catalog:
                query = query + " IN " + PyProphecy.escape(catalog)
            if filter:
                query = query + " LIKE '*" + filter + "*'"
            return [db[0] for db in spark.sql(query).collect()]
        except:  # errors in case of livy environment tabs, which we ignore.
            return []

    @staticmethod
    def print_databases(catalog, filter):
        _pdbs_list = "\n".join(
            ["[" + db + "]" for db in PyProphecy.get_databases(catalog, filter)]
        )
        _encoded_value = PyProphecy.encode(_pdbs_list)
        print(_encoded_value)
        return _encoded_value

    @staticmethod
    def get_tables(catalog, databases, filter):
        """
        Catalog scenerios:
          1. If catalog is available use it otherwise empty string.
        DB Scenarios:
          1. databases is None ==> None
          2. databases is [*dbs], filter is None ==> All tables of database from the list `dbs`
          3. databases is [*dbs], filter is "q" ==> All tables of database from the list `dbs` which match name `q`
        """
        from functools import reduce

        if not databases:
            return None

        def db_query(database):
            query = "SHOW TABLES"
            if database:
                query += f" IN {(PyProphecy.escape(catalog) + '.' if catalog else '')}{PyProphecy.escape(database)}"
            if filter is not None:
                query = query + " LIKE '*" + filter + "*'"
            return spark.sql(query)

        return reduce(PyProphecy.union, map(db_query, databases))

    @staticmethod
    def union(df1, df2):
        return df1.union(df2)

    @staticmethod
    def default_catalog():
        try:
            _result = spark.conf.get("spark.sql.defaultCatalog")
        except:
            _result = ""
        print(_result)
        return _result

    @staticmethod
    def print_tables(catalog, databases, filter):
        from functools import reduce

        if databases is None:  # means all databases, let's fetch them first.
            databases = PyProphecy.get_databases(catalog, None)

        if filter is None:  # means you want all tables within the databases list above
            databaseWithMatchingNames = databases
            databasesWithoutMatchingNames = []
        else:  # means you want filtered tables.
            databaseWithMatchingNames = [x for x in databases if filter in x]
            databasesWithoutMatchingNames = [x for x in databases if filter not in x]
        # self explanatory variable names
        allTablesOfMatchingDatabases = PyProphecy.get_tables(
            catalog, databaseWithMatchingNames, None
        )
        filteredTablesOfOtherDatabases = PyProphecy.get_tables(
            catalog, databasesWithoutMatchingNames, filter
        )

        candidates = []
        if allTablesOfMatchingDatabases is not None:
            candidates.append(allTablesOfMatchingDatabases)
        if filteredTablesOfOtherDatabases is not None:
            candidates.append(filteredTablesOfOtherDatabases)

        _ptables_list = []
        if candidates:
            _ptables_list = reduce(PyProphecy.union, candidates).collect()
        _plisted_view = "\n".join(
            [
                "["
                + table[0]
                + ","
                + table.tableName
                + ","
                + str(table.isTemporary).lower()
                + "]"
                for table in _ptables_list
            ]
        )
        display(spark.createDataFrame([[PyProphecy.encode(_plisted_view)]]))

    @staticmethod
    def extract_url_parts(url: str) -> tuple:
        parsed_url = urlparse(url)
        scheme = parsed_url.scheme
        authority = parsed_url.netloc
        path = parsed_url.path
        return scheme, authority, path

    @staticmethod
    def fs_prefix(url: str) -> str:
        scheme, authority, path = PyProphecy.extract_url_parts(url)
        if not authority:
            return scheme + ":"
        else:
            return scheme + "://" + authority

    @staticmethod
    def get_catalogs():
        try:
            query = "SHOW CATALOGS"
            catalogs_as_list = "\n".join(
                [
                    "FileInfo("
                    + ", ".join(
                        [f"dbfs:/Volumes/{x.catalog}/", f"{x.catalog}/", str(0)]
                    )
                    + ")"
                    for x in spark.sql(query).collect()
                ]
            )
            _result = catalogs_as_list
        except:
            _result = ""
        return _result

    @staticmethod
    def get_catalog_names():
        return [x.catalog for x in spark.sql("SHOW CATALOGS").collect()]

    @staticmethod
    def get_schemas(catalog):
        try:
            query = "SHOW SCHEMAS"
            if catalog is not None:
                query = query + " IN " + PyProphecy.escape(catalog)
            schemas_as_list = "\n".join(
                [
                    "FileInfo("
                    + ", ".join(
                        [
                            f"dbfs:/Volumes/{catalog}/{x.databaseName}/",
                            f"{x.databaseName}/",
                            str(0),
                        ]
                    )
                    + ")"
                    for x in spark.sql(query).collect()
                ]
            )
            _result = schemas_as_list
        except:
            _result = ""
        return _result

    @staticmethod
    def get_volumes(catalog, schema):
        try:
            query = "SHOW VOLUMES"
            if catalog is not None:
                query = (
                    query
                    + " IN "
                    + PyProphecy.escape(catalog)
                    + "."
                    + PyProphecy.escape(schema)
                )
            volumes_as_list = "\n".join(
                [
                    "FileInfo("
                    + ", ".join(
                        [
                            f"dbfs:/Volumes/{catalog}/{schema}/{x.volume_name}/",
                            f"{x.volume_name}/",
                            str(0),
                        ]
                    )
                    + ")"
                    for x in spark.sql(query).collect()
                ]
            )
            _result = volumes_as_list
        except:
            _result = ""
        return _result

    @staticmethod
    def fs_list(path: str):
        import gzip

        def _get_entities(path):
            match = re.match(PyProphecy._dbfs_volume_pattern, path)
            if match is None:
                return None
            path_entities = [s for s in match.groups() if s is not None]
            if len(path_entities) == 1:
                return PyProphecy.get_catalogs()
            elif len(path_entities) == 2:
                return PyProphecy.get_schemas(path_entities[-1])
            elif len(path_entities) == 3:
                return PyProphecy.get_volumes(path_entities[-2], path_entities[-1])
            return None

        _fs_prefix = PyProphecy.fs_prefix(path)
        files_list = []
        result = None
        try:
            files_list = dbutils.fs.ls(path)
        except Exception as e:
            result = _get_entities(path)
            if result is None:
                raise e

        try:
            listed = result or "\n".join(
                [
                    "FileInfo("
                    + ", ".join(
                        [
                            file_info.path,
                            file_info.name,
                            str(file_info.size),
                            str(file_info.modificationTime),
                        ]
                    )
                    + ")"
                    for file_info in files_list
                ]
            )
        except:
            listed = "\n".join(
                [
                    "FileInfo("
                    + ", ".join([file_info.path, file_info.name, str(file_info.size)])
                    + ")"
                    for file_info in files_list
                ]
            )
        _out = base64_std.encodebytes(gzip.compress(bytes(listed, "utf-8"))).decode(
            "utf-8"
        )

        def output_data():
            if len(_out) < 48000:
                fslist_result = _fs_prefix + "\\n" + _out
                print(fslist_result)
                return fslist_result
            else:
                schema = StructType([StructField("value", StringType(), True)])
                display(spark.createDataFrame([[_fs_prefix], [_out]], schema))

        return output_data()

    @staticmethod
    def sync_prophecy_job(job, job_description, codegen_mode):
        def decorator(func):
            def wrapper(*args, **kwargs):
                import warnings
                import sys

                _default_redirection_stdout = sys.stdout
                _default_redirection_stderr = sys.stderr

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    try:
                        from prophecy.utils import MetricsCollector
                    except Exception as e:
                        PyProphecy.log(
                            "Metrics Collector doesn't exist in classpath", e
                        )

                    try:
                        spark.sparkContext.setJobDescription(job_description)
                        spark.sparkContext.setLocalProperty("prophecy.job.id", job)
                    except Exception as e:
                        PyProphecy.log(
                            "Could not set spark context properties. Proceeding without setting job description"
                        )

                    # current_rules = spark.conf.get("spark.sql.optimizer.excludedRules")
                    try:
                        if (
                            codegen_mode == "vanilla"
                            or codegen_mode == "vanillawithmetrics"
                        ):
                            # if current_rules:
                            #     spark.conf.set("spark.sql.optimizer.excludedRules", "")
                            result = func(*args, **kwargs)
                        else:
                            result = func(*args, **kwargs)

                    except Exception as e:
                        PyProphecy.log("Error in executing user code", e)
                        raise e

                    finally:
                        # if current_rules:
                        #     spark.conf.set(
                        #         "spark.sql.optimizer.excludedRules", current_rules
                        #     )
                        sys.stdout = _default_redirection_stdout
                        sys.stderr = _default_redirection_stderr
                        try:
                            from prophecy.utils import MetricsCollector

                            MetricsCollector.end(spark=spark)
                        except Exception as e:
                            PyProphecy.log("Couldn't end Metrics Collector", e)

                    return result

            return wrapper

        return decorator

    @staticmethod
    def raw_prophecy_code(job, job_description):
        def decorator(func):
            def wrapper(*args, **kwargs):
                import warnings
                import sys

                _default_redirection_stdout = sys.stdout
                _default_redirection_stderr = sys.stderr

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    try:
                        spark.sparkContext.setJobDescription(job_description)
                        spark.sparkContext.setLocalProperty("prophecy.job.id", job)
                    except Exception as e:
                        """"""

                    # current_rules = spark.conf.get("spark.sql.optimizer.excludedRules")
                    try:
                        result = func(*args, **kwargs)
                    except Exception as e:
                        PyProphecy.log("Error in executing user code", e)
                        raise e
                    finally:
                        # if current_rules:
                        #     spark.conf.set(
                        #         "spark.sql.optimizer.excludedRules", current_rules
                        #     )
                        sys.stdout = _default_redirection_stdout
                        sys.stderr = _default_redirection_stderr

                    return result

            return wrapper

        return decorator

    @staticmethod
    def update_global_interim_store(interim_detail):
        InterimStore.update(interim_detail)

    @staticmethod
    def load_more(rows, pipeline, process, port, run_id=None):
        InterimStore.load_more(rows, pipeline, process, port, run_id)


# SVLESS_UNSUPPORTED: Configs are not supported
# # basic stats always enabled for all interims
# spark.conf.set("prophecy.collect.basic.stats", "true")
#
# # this is for scala 3.1.1. udf decode_datetime in prophecy-libs SparkFunctions.scala
# spark.conf.set("spark.sql.legacy.allowUntypedScalaUDF", "true")
#
# spark.conf.set("spark.sql.crossJoin.enabled", "true")
try:
    from prophecy.utils import MetricsCollector

    MetricsCollector.initializeMetrics(spark)
except Exception as e:
    PyProphecy.log("Metrics Collector doesn't exist in classpath", e)

# had to add this, since display call is unresolved at runtime, not sure how it works for cluster-based
display = DataSampleLoader.display
