from datetime import datetime, timezone
from logging import Logger
import os
import time
from typing import Optional
from pyspark.sql import SparkSession
import re


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_millis() -> int:
    """
    Return the current UTC time as milliseconds since the Unix epoch.

    Mirrors Scala's `System.currentTimeMillis()`.
    """
    return int(time.time_ns() / 1000000)


def timestamp_from_long(epoch_millis: Optional[int]) -> datetime:
    """
    Convert an epoch-millisecond value to a timezone-aware `datetime`.

    If `epoch_millis` is ``None`` (Scala's `Option.empty`), the current time is used.

    Args:
        epoch_millis: Epoch time in **milliseconds**; may be ``None``.

    Returns:
        A `datetime` instance in UTC.
    """
    millis = epoch_millis if epoch_millis is not None else now_millis()
    # `datetime.fromtimestamp` expects seconds, so convert ms → s.
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc)


def is_databricks_environment(spark: SparkSession) -> bool:
    """Check if running in Databricks environment."""
    return (
        spark.conf.get("spark.databricks.cloudProvider", None) is not None
        or is_serverless_env()
    )


def is_serverless_env() -> bool:
    return bool(int(os.environ.get("DATABRICKS_SERVERLESS_MODE_ENABLED", "0")))


def get_spark_property(conf_key: str, spark: SparkSession) -> Optional[str]:
    """Get spark property with or without spark prefix."""
    conf_without_prefix = re.sub(r"^spark\.", "", conf_key, count=1)

    # Try without prefix first
    value = spark.conf.get(conf_without_prefix, None)
    if value is not None:
        return value

    # Try with full key
    return spark.conf.get(conf_key, None)


def get_spark_property_with_logging(
    conf_key: str, spark: SparkSession, logger: Logger
) -> Optional[str]:
    """Get spark property with logging."""
    logger.info(f"Getting spark property {conf_key}")
    conf_without_prefix = re.sub(r"^spark\.", "", conf_key, count=1)

    value = spark.conf.get(conf_without_prefix, None)
    if value is not None:
        logger.info(f"spark conf has value of `{conf_without_prefix}` is {value}")
        return value

    logger.info(f"Spark conf doesn't have `{conf_without_prefix}`")

    value = spark.conf.get(conf_key, None)
    if value is not None:
        logger.info(f"spark conf has value of `{conf_key}` is {value}")
        return value

    logger.info(f"Spark conf doesn't have `{conf_key}`")
    return None
