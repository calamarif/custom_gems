"""
Delta Interims implementation for execution metrics.

This module provides Delta Lake storage implementation for interim data
during pipeline execution.
"""

import logging
from typing import List, Dict

from pyspark.sql import DataFrame, SparkSession

from prophecy.executionmetrics.logging_spark_session import (
    sql_with_logging,
    write_to_delta_with_logging,
)
from prophecy.executionmetrics.package import InterimResponse
from prophecy.executionmetrics.schemas.external import ComponentRunIdAndInterims
from prophecy.executionmetrics.evolutions.models import DeltaStorageMetadata
from prophecy.executionmetrics.utils.constants import (
    UID,
    INTERIM,
    RUN_ID,
    CREATED_AT,
    CREATED_BY,
    FABRIC_UID,
)
from prophecy.executionmetrics.interims.interims_table import (
    InterimsTable,
    INTERIMS_SCHEMA,
)

logger = logging.getLogger(__name__)


RunConfigMap = Dict[str, Dict[str, str]]


class DeltaInterims(InterimsTable):
    """
    Delta Lake implementation of interims table.

    This class provides Delta-specific storage operations for interim data,
    including table creation, schema evolution, and data operations.
    """

    def __init__(
        self,
        spark: SparkSession,
        user: str,
        storage_metadata: DeltaStorageMetadata,
    ):
        """
        Initialize Delta interims table.

        Args:
            spark: SparkSession to use
            user: Username for table location
            storage_metadata: Delta storage configuration
        """
        super().__init__(spark)
        self.user = user
        self.storage_metadata = storage_metadata

        # Set table name from storage metadata
        self._table_name = (
            storage_metadata.metrics_storage_details.interims_table.fully_qualified_name
        )

        # Set default location for Delta table
        self._default_interims_location = (
            f"{storage_metadata.base_object_location}/interims/created_by={user}"
        )

        # Create table query
        self.create_table_query = f"""
CREATE TABLE IF NOT EXISTS {self._table_name} (
    {UID} STRING NOT NULL,
    {INTERIM} STRING NOT NULL,
    {RUN_ID} STRING,
    {CREATED_BY} STRING NOT NULL,
    {CREATED_AT} TIMESTAMP,
    {FABRIC_UID} STRING
) USING DELTA
PARTITIONED BY ({CREATED_BY}, {FABRIC_UID})
LOCATION '{self._default_interims_location}'
"""

        # Check schema compatibility
        self.schema_to_table_compatibility = (
            self.check_table_with_schema_compatibility()
        )

        # Check if RUN_ID column exists
        self.run_id_column_exists = self.schema_to_table_compatibility.get(
            RUN_ID, False
        )

        # Try to add RUN_ID column if it doesn't exist
        self.is_column_added_successfully = self._add_run_id_column_if_needed()

    @property
    def table_name(self) -> str:
        """Get the table name."""
        return self._table_name

    @property
    def default_interims_location(self) -> str:
        """Get the default location for interims storage."""
        return self._default_interims_location

    def initialize(self) -> DataFrame:
        """
        Initialize the Delta table by creating it.

        Returns:
            DataFrame result of CREATE TABLE
        """
        return sql_with_logging(self.spark, self.create_table_query)

    def evolve(self) -> None:
        """
        Apply schema evolutions to the table.

        For Delta tables, evolutions are handled through ALTER TABLE
        statements when needed (like adding RUN_ID column).
        """
        # Currently no additional evolutions needed beyond RUN_ID column
        pass

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

        # Write to Delta table
        write_to_delta_with_logging(
            self.spark,
            table_name=self._table_name,
            data=data_to_insert,
            schema=INTERIMS_SCHEMA,
            partition_columns=[],  # Partitioning is handled by Delta
        )

        # Return the interim strings that were added
        return [item.interims for item in list_of_id_to_interims]

    def _add_run_id_column_if_needed(self) -> bool:
        """
        Add RUN_ID column if it doesn't exist.

        Returns:
            True if column was added successfully or already exists, False otherwise
        """
        if not self.run_id_column_exists:
            alter_table_query = (
                f"ALTER TABLE {self._table_name} ADD COLUMNS ({RUN_ID} STRING)"
            )
            try:
                sql_with_logging(self.spark, alter_table_query)
                self.logger.info(
                    f"Successfully added column {RUN_ID} to table {self._table_name}"
                )
                return True
            except Exception as e:
                self.logger.error(
                    f"Error on adding column {RUN_ID} to table {self._table_name}",
                    exc_info=e,
                )
                return False
        else:
            # Column already exists
            return True


# Additional helper functions that might be needed


def create_interims_response_from_runs(
    runs: InterimResponse, run_confs: RunConfigMap
) -> Dict:
    """
    Create interim response with run configuration.

    Args:
        runs: Interim response data
        run_confs: Run configuration map

    Returns:
        Dictionary with interim response data
    """
    result = {
        "uid": runs.uid,
        "interimComponentName": runs.interim_component_name,
        "interimOutPort": runs.interim_out_port,
        "interimProcessId": runs.interim_process_id,
        "interim": runs.interim,
        "runId": runs.run_id,
    }

    # Add run config if available
    if runs.run_id and runs.interim_out_port in run_confs:
        port_configs = run_confs[runs.interim_out_port]
        if runs.run_id in port_configs:
            result["runConfig"] = port_configs[runs.run_id]

    return result
