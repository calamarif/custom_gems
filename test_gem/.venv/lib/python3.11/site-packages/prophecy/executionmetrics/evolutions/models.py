from abc import ABC
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Optional

from pyspark.sql import SparkSession

from prophecy.executionmetrics.utils.common import is_databricks_environment


class MetricsStore(Enum):
    """Enum for supported metrics storage types."""

    DELTA_STORE = "DELTA_STORE"
    HIVE = "HIVE"

    @classmethod
    def from_string(cls, store: Any) -> Optional["MetricsStore"]:
        """Create MetricsStore from string."""
        if isinstance(store, MetricsStore):
            return store
        if not store:
            return None
        store_upper = str(store).upper()
        if store_upper == "DELTASTORE" or store_upper == "DELTA_STORE":
            return cls.DELTA_STORE
        elif store_upper == "HIVE":
            return cls.HIVE
        return None

    @classmethod
    def from_spark_session(cls, spark: SparkSession) -> "MetricsStore":
        """Determine metrics store type based on Spark session."""
        # Check if running on Databricks
        if is_databricks_environment(spark):
            return cls.DELTA_STORE
        return cls.HIVE


@dataclass
class TableMetadata:
    """
    Metadata for a metrics table.

    Attributes:
        name: Simple table name
        fully_qualified_name: Full table name including database/catalog
        fully_qualified_db_name: Full database name including catalog
        create_table: Whether to create the table during initialization
    """

    name: str
    fully_qualified_name: str
    fully_qualified_db_name: str
    create_table: bool = False


@dataclass
class MetricsStorageDetails:
    """
    Storage configuration details for all metrics tables.

    Attributes:
        pipeline_metrics_table: Metadata for pipeline runs table
        component_metrics_table: Metadata for component runs table
        interims_table: Metadata for interims table
        create_db: Whether to create the database
        db_suffix: Suffix for database name
        is_partitioning_disabled: Whether to disable partitioning
    """

    pipeline_metrics_table: TableMetadata
    component_metrics_table: TableMetadata
    interims_table: TableMetadata
    create_db: bool = False
    db_suffix: str = ""
    is_partitioning_disabled: bool = False


@dataclass
class StorageMetadata(ABC):
    """Base class for storage metadata."""

    metrics_storage_details: MetricsStorageDetails = None


@dataclass
class DeltaStorageMetadata(StorageMetadata):
    """
    Storage metadata for Delta Lake tables.

    Attributes:
        base_object_location: Base path for Delta table storage
        catalog_name: Optional catalog name for Unity Catalog
        metrics_storage_details: Storage configuration details
    """

    base_object_location: str = ""
    catalog_name: Optional[str] = None
    metrics_storage_details: MetricsStorageDetails = None


@dataclass
class HiveStorageMetadata(StorageMetadata):
    """
    Storage metadata for Hive tables.

    Attributes:
        catalog_name: Optional catalog name
        metrics_storage_details: Storage configuration details
        is_partitioning_disabled: Whether partitioning is disabled
    """

    catalog_name: Optional[str] = None
    metrics_storage_details: MetricsStorageDetails = None
    is_partitioning_disabled: bool = False
