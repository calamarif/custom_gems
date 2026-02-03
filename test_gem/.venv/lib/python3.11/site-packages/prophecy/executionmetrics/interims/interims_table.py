"""
Interims Table module for execution metrics.

This module provides abstract interface and factory for creating interims tables
that store intermediate data during pipeline execution.
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import StructType, StructField, StringType, TimestampType

from prophecy.executionmetrics.evolutions.models import (
    DeltaStorageMetadata,
    HiveStorageMetadata,
    StorageMetadata,
)
from prophecy.executionmetrics.logging_spark_session import (
    refresh_table_if_exists,
    sql_with_logging,
)
from prophecy.executionmetrics.package import Filters
from prophecy.executionmetrics.schemas.external import ComponentRunIdAndInterims
from prophecy.executionmetrics.utils.constants import (
    CREATED_AT,
    CREATED_BY,
    FABRIC_UID,
    INTERIM,
    RUN_ID,
    UID,
)

logger = logging.getLogger(__name__)

# Schema definition for interims table
INTERIMS_SCHEMA = StructType(
    [
        StructField(UID, StringType(), nullable=False),
        StructField(INTERIM, StringType(), nullable=False),
        StructField(RUN_ID, StringType(), nullable=True),
        StructField(CREATED_BY, StringType(), nullable=False),
        StructField(CREATED_AT, TimestampType(), nullable=False),
        StructField(FABRIC_UID, StringType(), nullable=False),
    ]
)


class InterimsTable(ABC):
    """
    Abstract base class for interims table operations.

    This class defines the interface for storing and retrieving interim
    data during pipeline execution.
    """

    def __init__(self, spark: SparkSession):
        """
        Initialize the interims table.

        Args:
            spark: SparkSession to use
        """
        self.spark = spark
        self.logger = logger

    @property
    @abstractmethod
    def table_name(self) -> str:
        """Get the table name."""
        pass

    @property
    @abstractmethod
    def default_interims_location(self) -> str:
        """Get the default location for interims storage."""
        pass

    def check_table_with_schema_compatibility(self) -> Dict[str, bool]:
        """
        Check if table schema is compatible with expected schema.

        Returns:
            Dictionary mapping column names to existence status
        """
        try:
            # Get current table columns
            table_columns = self.spark.catalog.listColumns(self.table_name)
            table_column_names = [col.name for col in table_columns]

            # Check each expected column
            compatibility = {}
            for field in INTERIMS_SCHEMA.fields:
                compatibility[field.name] = field.name in table_column_names

            return compatibility

        except Exception as e:
            self.logger.warning(f"Failed to describe table {self.table_name}: {e}")
            # Return required columns as True if we can't check
            compatibility = {}
            for field in INTERIMS_SCHEMA.fields:
                # Only required (non-nullable) fields are unavoidable
                compatibility[field.name] = not field.nullable
            return compatibility

    @abstractmethod
    def initialize(self) -> DataFrame:
        """
        Initialize the table by creating it if needed.

        Returns:
            DataFrame result of table creation
        """
        pass

    @abstractmethod
    def evolve(self) -> None:
        """Apply schema evolutions to the table."""
        pass

    @abstractmethod
    def check_record_status(self) -> Dict[str, bool]:
        """
        Check the status of records/columns in the table.

        Returns:
            Dictionary with column status information
        """
        pass

    @abstractmethod
    def add_multi(
        self,
        list_of_id_to_interims: List[ComponentRunIdAndInterims],
        updated_by: str,
        fabric_id: str,
        created_at,
    ) -> List[str]:
        """
        Add multiple interim records to the table.

        Args:
            list_of_id_to_interims: List of component run IDs and interim data
            updated_by: User who created the records
            fabric_id: Fabric ID for partitioning
            created_at: Timestamp for record creation

        Returns:
            List of interim data strings that were added
        """
        pass

    def get(self, uid: str, filters: Filters) -> Optional[str]:
        """
        Get interim data by UID.

        Args:
            uid: Unique identifier
            filters: Query filters

        Returns:
            Interim data string if found, None otherwise
        """
        partition_filters = Filters.partition_queries(filters)
        query = f"SELECT {INTERIM} FROM {self.table_name} WHERE {UID} = '{uid}' {partition_filters}"

        result = sql_with_logging(self.spark, query)
        rows = result.collect()

        if rows:
            return rows[0][0]
        return None

    def get_by_ids(self, uids: List[str], filters: Filters) -> List[str]:
        """
        Get multiple interim records by UIDs.

        Args:
            uids: List of unique identifiers
            filters: Query filters

        Returns:
            List of UIDs that were found
        """
        if not uids:
            return []

        uid_list = ", ".join([f"'{uid}'" for uid in uids])
        partition_filters = Filters.partition_queries(filters)
        query = f"SELECT {UID} FROM {self.table_name} WHERE {UID} IN ({uid_list}) {partition_filters}"

        result = sql_with_logging(self.spark, query)
        return [row[0] for row in result.collect()]

    def refresh(self) -> None:
        """Refresh the table if it exists."""
        refresh_table_if_exists(self.spark, self.table_name)


def create_interims_table(
    spark_session: SparkSession, user: str, storage_metadata: StorageMetadata
) -> InterimsTable:
    """
    Factory function to create appropriate InterimsTable implementation.

    Args:
        spark_session: SparkSession to use
        user: Username for table naming
        storage_metadata: Storage configuration

    Returns:
        InterimsTable implementation based on storage type
    """
    # Determine storage type and create appropriate implementation
    if isinstance(storage_metadata, DeltaStorageMetadata):
        from prophecy.executionmetrics.interims.delta_interims import DeltaInterims

        interims_table = DeltaInterims(spark_session, user, storage_metadata)
    elif isinstance(storage_metadata, HiveStorageMetadata):
        from prophecy.executionmetrics.interims.hive_parquet_interims import (
            HiveParquetInterims,
        )

        interims_table = HiveParquetInterims(spark_session, user, storage_metadata)
    else:
        raise ValueError(f"Unknown storage metadata type: {type(storage_metadata)}")

    # Initialize or evolve based on configuration
    if storage_metadata.metrics_storage_details.interims_table.create_table:
        interims_table.initialize()
    else:
        # Right now this performs evolutions for read path as well
        # Re-visit if needed
        interims_table.evolve()

    return interims_table
