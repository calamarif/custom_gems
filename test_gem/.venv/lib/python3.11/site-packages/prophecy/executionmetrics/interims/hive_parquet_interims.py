"""
Hive Parquet Interims implementation for execution metrics.

This module provides Hive table with Parquet format storage implementation
for interim data during pipeline execution.
"""

import logging
from typing import List, Dict, Optional

from pyspark.sql import DataFrame, SparkSession

from prophecy.executionmetrics.evolutions.package import (
    InterimsSchema,
    perform_up_evolutions,
)
from prophecy.executionmetrics.logging_spark_session import (
    sql_with_logging,
    write_to_hive_with_logging,
)
from prophecy.executionmetrics.schemas.external import ComponentRunIdAndInterims
from prophecy.executionmetrics.evolutions.models import HiveStorageMetadata
from prophecy.executionmetrics.interims.interims_table import (
    INTERIMS_SCHEMA,
    InterimsTable,
)
from prophecy.executionmetrics.utils.constants import (
    UID,
    INTERIM,
    RUN_ID,
    CREATED_AT,
    CREATED_BY,
    FABRIC_UID,
)

logger = logging.getLogger(__name__)


class HiveParquetInterims(InterimsTable):
    """
    Hive Parquet implementation of interims table.

    This class provides Hive-specific storage operations for interim data,
    using Parquet format for efficient storage and querying.
    """

    def __init__(
        self,
        spark: SparkSession,
        user: str,
        storage_metadata: HiveStorageMetadata,
    ):
        """
        Initialize Hive Parquet interims table.

        Args:
            spark: SparkSession to use
            user: Username (used for table naming but not location in Hive)
            storage_metadata: Hive storage configuration
        """
        super().__init__(spark)
        self.user = user
        self.storage_metadata = storage_metadata

        # Set table name from storage metadata
        self._table_name = (
            storage_metadata.metrics_storage_details.interims_table.fully_qualified_name
        )

        # Hive doesn't use custom locations like Delta
        self._default_interims_location = ""

        # Create table query
        self.create_table_query = f"""
CREATE TABLE IF NOT EXISTS {self._table_name} (
    {UID} STRING NOT NULL,
    {INTERIM} STRING,
    {RUN_ID} STRING,
    {CREATED_BY} STRING,
    {CREATED_AT} TIMESTAMP,
    {FABRIC_UID} STRING
) STORED AS PARQUET
PARTITIONED BY ({CREATED_BY}, {FABRIC_UID})
"""

        # Partition columns for Hive
        self.partition_columns = [CREATED_BY, FABRIC_UID]

        # Check schema compatibility
        self.schema_to_table_compatibility = (
            self.check_table_with_schema_compatibility()
        )

    @property
    def table_name(self) -> str:
        """Get the table name."""
        return self._table_name

    @property
    def default_interims_location(self) -> str:
        """
        Get the default location for interims storage.

        For Hive tables, this is empty as Hive manages the location.
        """
        return self._default_interims_location

    def initialize(self) -> DataFrame:
        """
        Initialize the Hive table by creating it.

        Returns:
            DataFrame result of CREATE TABLE
        """
        return sql_with_logging(self.spark, self.create_table_query)

    def evolve(self) -> None:
        """
        Apply schema evolutions to the table.

        This delegates to the general evolution framework for Hive tables.
        """
        perform_up_evolutions(self.spark, self._table_name, InterimsSchema)

    def check_record_status(self) -> Dict[str, bool]:
        """
        Check the status of records/columns in the table.

        Returns:
            Dictionary with column existence status
        """
        return self.schema_to_table_compatibility

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
        if not list_of_id_to_interims:
            self.logger.warning(f"No interims found to insert for fabric `{fabric_id}`")
            return []

        # Prepare data for insertion
        data_to_insert = []
        for item in list_of_id_to_interims:
            data_to_insert.append(
                (
                    item.uid,
                    item.interims,
                    item.run_id,
                    updated_by,
                    created_at,
                    fabric_id,
                )
            )

        # Write to Hive table based on partitioning configuration
        if not self.storage_metadata.is_partitioning_disabled:
            write_to_hive_with_logging(
                self.spark,
                table_name=self._table_name,
                data=data_to_insert,
                schema=INTERIMS_SCHEMA,
                partition_columns=self.partition_columns,
            )
        else:
            # Write without partitioning
            write_to_hive_with_logging(
                self.spark,
                table_name=self._table_name,
                data=data_to_insert,
                schema=INTERIMS_SCHEMA,
            )

        # Return the interim strings that were added
        return [item.interims for item in list_of_id_to_interims]


# Additional utility functions


def create_hive_ddl_for_interims(
    table_name: str, partition_columns: Optional[List[str]] = None
) -> str:
    """
    Create DDL statement for Hive interims table.

    Args:
        table_name: Fully qualified table name
        partition_columns: Optional partition columns

    Returns:
        DDL string for creating the table
    """
    ddl = f"""
CREATE TABLE IF NOT EXISTS {table_name} (
    {UID} STRING NOT NULL,
    {INTERIM} STRING,
    {RUN_ID} STRING,
    {CREATED_BY} STRING,
    {CREATED_AT} TIMESTAMP,
    {FABRIC_UID} STRING
) STORED AS PARQUET
"""

    if partition_columns:
        ddl += f"PARTITIONED BY ({', '.join(partition_columns)})"

    return ddl.strip()
