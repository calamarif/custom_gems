import logging
from datetime import datetime
from typing import List, Optional, Sequence, Any, Tuple, Union

# PySpark imports
from pyspark.sql import SparkSession, DataFrame, Row
from pyspark.sql.types import StructType

logger = logging.getLogger(__name__)


def _is_type_spark_dataframe(df: Any) -> bool:
    try:
        if isinstance(df, DataFrame):
            return True

        from pyspark.sql.connect.dataframe import DataFrame as SqlConnectDataFrame

        return isinstance(df, SqlConnectDataFrame)
    except Exception as e:
        return False


def _as_rows(values: Sequence[Any]) -> List[Row]:
    """Convert values to Row objects."""
    rows = []
    for value in values:
        if isinstance(value, Row):
            rows.append(value)
        elif hasattr(value, "_fields") or isinstance(
            value, (list, tuple)
        ):  # Named tuple or similar
            rows.append(Row(*value))
        else:
            rows.append(Row(value))
    return rows


def create_df(
    spark: SparkSession, data: Sequence[Any], schema: StructType
) -> DataFrame:
    """Create DataFrame from data and schema."""
    rows = _as_rows(data)
    return spark.createDataFrame(rows, schema)


def write_to_delta_with_logging(
    spark: SparkSession,
    table_name: str,
    data: Union[Sequence[Any], DataFrame],
    schema: Optional[StructType] = None,
    partition_columns: Optional[List[str]] = None,
) -> None:
    """Write data to Delta table with logging."""
    if partition_columns is None:
        partition_columns = []

    if _is_type_spark_dataframe(data):
        df = data
    else:
        if schema is None:
            raise ValueError("Schema must be provided for sequence data")
        df = create_df(spark, data, schema)

    logger.info(
        f"Writing to delta table {table_name} -- type: {type(data)} -- schema: {schema} "
    )

    writer = df.write.format("delta").option("mergeSchema", "true").mode("append")

    if partition_columns:
        writer = writer.partitionBy(*partition_columns)

    writer.saveAsTable(table_name)

    logger.info(f"Successfully wrote records to {table_name}")


def write_to_hive_with_logging(
    spark: SparkSession,
    table_name: str,
    data: Union[Sequence[Any], DataFrame],
    schema: Optional[StructType] = None,
    partition_columns: Optional[List[str]] = None,
) -> None:
    """Write data to Hive table with logging."""
    if partition_columns is None:
        partition_columns = []

    if _is_type_spark_dataframe(data):
        df = data
    else:
        if schema is None:
            raise ValueError("Schema must be provided for sequence data")
        df = create_df(spark, data, schema)

    logger.info(f"Start Writing to Hive table {table_name}")
    start_time = datetime.now()

    filtered_data, valid_partition_columns = _get_filtered_data_and_partitions(
        spark, table_name, df, partition_columns
    )

    writer = filtered_data.write.format("hive").mode("append")

    if valid_partition_columns:
        writer = writer.partitionBy(*valid_partition_columns)

    writer.saveAsTable(table_name)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds() * 1000
    logger.info(f"Done Writing to Hive table {table_name}. Time taken: {duration}ms")


def _get_filtered_data_and_partitions(
    spark: SparkSession, table_name: str, data: DataFrame, partition_columns: List[str]
) -> Tuple[DataFrame, List[str]]:
    """Get filtered data and valid partition columns."""
    try:
        # Get table schema from catalog
        table_columns = spark.catalog.listColumns(table_name).collect()
        table_column_names = [col.name for col in table_columns]
        partition_column_names = [col.name for col in table_columns if col.isPartition]

        # Filter data to matching columns
        matching_columns = [
            col_name for col_name in data.columns if col_name in table_column_names
        ]
        filtered_data = data.select(*matching_columns)

        # Filter partition columns to valid ones
        valid_partition_columns = [
            col_name
            for col_name in partition_columns
            if col_name in partition_column_names
        ]

        return filtered_data, valid_partition_columns
    except Exception:
        # If table doesn't exist or other error, return original data
        return data, partition_columns


def sql_with_logging(spark: SparkSession, query: str) -> DataFrame:
    """Execute SQL query with logging."""
    logger.info(f"Running spark sql query {query}")
    start_time = datetime.now()

    result = spark.sql(query)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds() * 1000
    logger.info(f"Spark sql query took {duration}ms.")

    return result


def refresh_table_if_exists(spark: SparkSession, fqtn: str) -> None:
    """Refresh table if it exists."""
    if spark.catalog.tableExists(fqtn):
        spark.catalog.refreshTable(fqtn)
