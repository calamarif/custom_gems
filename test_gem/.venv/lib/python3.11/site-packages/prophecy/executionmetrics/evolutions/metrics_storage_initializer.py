"""
Metrics Storage Initializer base module.

This module provides base classes and utilities for initializing storage
for execution metrics, supporting both Delta and Hive storage formats.
"""

import logging
import re
from abc import ABC, abstractmethod
from typing import Optional

from pyspark.sql import SparkSession

from prophecy.executionmetrics.evolutions.models import (
    MetricsStorageDetails,
    MetricsStore,
    StorageMetadata,
    TableMetadata,
)
from prophecy.executionmetrics.schemas.external import MetricsTableNames
from prophecy.executionmetrics.utils.common import is_databricks_environment
from prophecy.executionmetrics.utils.external import create_db_suffix_from_url

logger = logging.getLogger(__name__)


class MetricsStorageInitializer(ABC):
    """
    Abstract base class for metrics storage initializers.

    This class defines the interface for storage-specific initializers.
    """

    def __init__(self, spark: SparkSession, storage_details: MetricsStorageDetails):
        """
        Initialize the storage initializer.

        Args:
            spark: SparkSession to use
            storage_details: Storage configuration details
        """
        self.spark = spark
        self.storage_details = storage_details
        self.logger = logger

    @abstractmethod
    def initialize(self, read_only: bool) -> StorageMetadata:
        """
        Initialize the storage.

        Args:
            read_only: If True, skip table creation

        Returns:
            StorageMetadata with initialization results
        """
        pass

    def cleanup(self) -> None:
        """
        Clean up storage (drop database). Only for tests.
        """
        self.logger.info("------- DROPPING DB -------------")
        db_name = schema_name(self.storage_details.db_suffix)
        query = f"DROP DATABASE {db_name} CASCADE"
        self.spark.sql(query)


# Constants for default table names
DEFAULT_PIPELINE_RUNS_TABLE_NAME = "pipeline_runs"
DEFAULT_COMPONENT_RUNS_TABLE_NAME = "component_runs"
DEFAULT_INTERIM_TABLE_NAME = "interims"

# Regular expressions for name parsing
SIMPLE_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z_0-9]*$")
ESCAPED_NAME_PATTERN = re.compile(r"^`(.*?)`$")
DATABASE_ENTITY_NAME_PATTERN = re.compile(r"`([^`]+)`|([^.]+)")

# Default catalog and database
DEFAULT_CATALOG = "spark_catalog"
DEFAULT_DATABASE = "default"


def schema_name(suffix: str) -> str:
    """
    Generate schema name with suffix.

    Args:
        suffix: Suffix to append to schema name

    Returns:
        Backtick-quoted schema name
    """
    return f"`prophecy_{suffix}`"


def pipeline_runs_table_with_schema(suffix: str) -> str:
    """Get pipeline runs table name with schema."""
    return f"{schema_name(suffix)}.{DEFAULT_PIPELINE_RUNS_TABLE_NAME}"


def component_runs_table_with_schema(suffix: str) -> str:
    """Get component runs table name with schema."""
    return f"{schema_name(suffix)}.{DEFAULT_COMPONENT_RUNS_TABLE_NAME}"


def interims_table_with_schema(suffix: str, user: str) -> str:
    """
    Get interims table name with schema.

    Args:
        suffix: Database suffix
        user: Username to append to table name

    Returns:
        Fully qualified interims table name
    """
    # Replace non-alphanumeric characters with underscore
    clean_user = re.sub(r"[^a-zA-Z0-9]", "_", user)
    return f"{schema_name(suffix)}.{DEFAULT_INTERIM_TABLE_NAME}{clean_user}"


def with_backticks(s: str) -> str:
    """
    Add backticks to identifier if needed.

    Args:
        s: Identifier string

    Returns:
        Properly quoted identifier
    """
    # Check if already escaped
    if ESCAPED_NAME_PATTERN.match(s):
        return s
    # Check if simple name (doesn't need escaping)
    if SIMPLE_NAME_PATTERN.match(s):
        return s
    # Needs escaping
    return f"`{s}`"


def get_table_metadata(
    spark: SparkSession, provided_fqtn: Optional[str], default_fqtn_func
) -> TableMetadata:
    """
    Get table metadata from provided or default table name.

    Args:
        spark: SparkSession
        provided_fqtn: Optionally provided fully qualified table name
        default_fqtn_func: Function to generate default FQTN

    Returns:
        TableMetadata instance
    """
    is_databricks = is_databricks_environment(spark)

    if provided_fqtn:
        # Parse provided table name
        matches = DATABASE_ENTITY_NAME_PATTERN.findall(provided_fqtn)
        namespace_split = [with_backticks(m[0] or m[1]) for m in matches]

        # Handle different namespace lengths
        if len(namespace_split) == 1 and is_databricks:
            # Add default catalog and database
            effective_fqtn = [DEFAULT_CATALOG, DEFAULT_DATABASE] + namespace_split
        elif len(namespace_split) == 2 and is_databricks:
            # Add default catalog
            effective_fqtn = [DEFAULT_CATALOG] + namespace_split
        else:
            effective_fqtn = namespace_split

        return TableMetadata(
            name=effective_fqtn[-1],
            fully_qualified_name=".".join(effective_fqtn),
            fully_qualified_db_name=".".join(effective_fqtn[:-1]),
        )
    else:
        # Use default table name
        default_fqtn = default_fqtn_func()
        namespace_split = [with_backticks(part) for part in default_fqtn.split(".")]

        return TableMetadata(
            name=namespace_split[-1],
            fully_qualified_name=".".join(namespace_split),
            fully_qualified_db_name=".".join(namespace_split[:-1]),
            create_table=True,
        )


def initialize(
    spark: SparkSession,
    storage_details: MetricsStorageDetails,
    store: MetricsStore,
    read_only: bool,
) -> StorageMetadata:
    """
    Initialize storage based on the store type.

    Args:
        spark: SparkSession
        storage_details: Storage configuration
        store: Type of storage (Delta or Hive)
        read_only: Whether to skip table creation

    Returns:
        Initialized StorageMetadata
    """

    from prophecy.executionmetrics.evolutions.delta_metrics_storage_initializer import (
        DeltaMetricsStorageInitializer,
    )
    from prophecy.executionmetrics.evolutions.hive_parquet_storage_initializer import (
        HiveParquetStorageInitializer,
    )

    if store == MetricsStore.DELTA_STORE:
        initializer = DeltaMetricsStorageInitializer(spark, storage_details)
    else:  # MetricsStore.HIVE
        initializer = HiveParquetStorageInitializer(spark, storage_details)

    return initializer.initialize(read_only)


def create_storage_metadata(
    spark: SparkSession,
    execution_metrics_tables: MetricsTableNames,
    db_suffix: Optional[str],
    user: str,
    metrics_store: MetricsStore,
    read_only: bool,
    is_partitioning_disabled: bool = False,
) -> StorageMetadata:
    """
    Create and initialize storage metadata.

    This is the main entry point for creating storage metadata with all
    necessary tables and configurations.

    Args:
        spark: SparkSession to use
        execution_metrics_tables: Configured table names
        db_suffix: Optional database suffix
        user: Username for table naming
        metrics_store: Type of storage to use
        read_only: Whether to skip table creation
        is_partitioning_disabled: Whether to disable partitioning

    Returns:
        Initialized StorageMetadata
    """
    # Create database suffix
    suffix = create_db_suffix_from_url(db_suffix)

    # Get table metadata for each table
    pipeline_metrics_table = get_table_metadata(
        spark,
        execution_metrics_tables.pipeline_metrics,
        lambda: pipeline_runs_table_with_schema(suffix),
    )

    component_metrics_table = get_table_metadata(
        spark,
        execution_metrics_tables.component_metrics,
        lambda: component_runs_table_with_schema(suffix),
    )

    interims_table = get_table_metadata(
        spark,
        execution_metrics_tables.interims,
        lambda: interims_table_with_schema(suffix, user),
    )

    # Create storage details
    storage_details = MetricsStorageDetails(
        pipeline_metrics_table=pipeline_metrics_table,
        component_metrics_table=component_metrics_table,
        interims_table=interims_table,
        create_db=execution_metrics_tables.is_empty(),
        db_suffix=suffix,
        is_partitioning_disabled=is_partitioning_disabled,
    )

    # Initialize storage
    return initialize(spark, storage_details, metrics_store, read_only)
