"""
Hive Parquet Storage Initializer for execution metrics.

This module handles initialization of Hive tables with Parquet format for storing execution metrics.
"""

import logging

from pyspark.sql import SparkSession

from prophecy.executionmetrics.evolutions.models import (
    HiveStorageMetadata,
    MetricsStorageDetails,
    StorageMetadata,
)
from prophecy.executionmetrics.evolutions.package import (
    ComponentRunsSchema,
    PipelineRunsSchema,
    perform_up_evolutions,
)
from prophecy.executionmetrics.logging_spark_session import (
    sql_with_logging,
)
from prophecy.executionmetrics.evolutions.metrics_storage_initializer import (
    MetricsStorageInitializer,
)
from prophecy.executionmetrics.utils.constants import (
    UID,
    PIPELINE_URI,
    JOB_URI,
    JOB_RUN_UID,
    TASK_RUN_UID,
    STATUS,
    FABRIC_UID,
    TIME_TAKEN,
    ROWS_READ,
    ROWS_WRITTEN,
    CREATED_AT,
    CREATED_BY,
    RUN_TYPE_COLUMN,
    INPUT_DATASETS,
    OUTPUT_DATASETS,
    WORKFLOW_CODE,
    PIPELINE_CONFIG,
    USER_CONFIG,
    EXPECTED_INTERIMS,
    ACTUAL_INTERIMS,
    LOGS,
    COMPONENT_URI,
    PIPELINE_RUN_UID,
    COMPONENT_NAME,
    INTERIM_COMPONENT_NAME,
    RECORDS,
    BYTES,
    PARTITIONS,
    COMPONENT_TYPE,
    INTERIM_OUT_PORT,
    INTERIM_SUBGRAPH_NAME,
    INTERIM_PROCESS_ID,
    EXPIRED,
    BRANCH,
    GEM_NAME,
    PROCESS_ID,
    GEM_TYPE,
    INPUT_GEMS,
    OUTPUT_GEMS,
    IN_PORTS,
    OUT_PORTS,
    NUM_ROWS_OUTPUT,
    NUM_ROWS,
    STDOUT,
    STDERR,
    START_TIME,
    END_TIME,
    STATE,
    EXCEPTION,
    FROM_PORT,
    TO_PORT,
    EXCEPTION_TYPE,
    MSG,
    CAUSE_MSG,
    STACK_TRACE,
    TIME,
    CONTENT,
)

logger = logging.getLogger(__name__)


class HiveParquetStorageInitializer(MetricsStorageInitializer):
    """
    Initializer for Hive storage with Parquet format for execution metrics.

    This class handles creation and initialization of Hive tables
    for storing pipeline and component execution metrics in Parquet format.
    """

    def __init__(self, spark: SparkSession, storage_details: MetricsStorageDetails):
        """
        Initialize the Hive Parquet storage initializer.

        Args:
            spark: SparkSession to use
            storage_details: Details about the storage configuration
        """
        super().__init__(spark, storage_details)
        self.logger = logger

        # Set table names
        self.pipeline_table_name = (
            storage_details.pipeline_metrics_table.fully_qualified_name
        )
        self.component_table_name = (
            storage_details.component_metrics_table.fully_qualified_name
        )

        # Parse pipeline metrics namespace
        self.pipeline_metrics_namespace_split = (
            storage_details.pipeline_metrics_table.fully_qualified_name.split(".")
        )

        # Determine fully qualified database name
        namespace_db_split = self.pipeline_metrics_namespace_split[:-1]
        if not namespace_db_split:
            self.fully_qualified_db_name = "default"
        else:
            self.fully_qualified_db_name = ".".join(namespace_db_split)

        # SQL queries
        self.create_db_query = (
            f"CREATE DATABASE IF NOT EXISTS {self.fully_qualified_db_name}"
        )

        self.pipeline_runs_create_table_query = f"""
CREATE TABLE IF NOT EXISTS {self.pipeline_table_name} (
    {UID} STRING NOT NULL,
    {PIPELINE_URI} STRING NOT NULL,
    {JOB_URI} STRING,
    {JOB_RUN_UID} STRING,
    {TASK_RUN_UID} STRING,
    {STATUS} STRING,
    {FABRIC_UID} STRING NOT NULL,
    {TIME_TAKEN} BIGINT,
    {ROWS_READ} BIGINT,
    {ROWS_WRITTEN} BIGINT,
    {CREATED_AT} TIMESTAMP,
    {CREATED_BY} STRING NOT NULL,
    {RUN_TYPE_COLUMN} STRING,
    {INPUT_DATASETS} ARRAY<STRING>,
    {OUTPUT_DATASETS} ARRAY<STRING>,
    {WORKFLOW_CODE} MAP<STRING, STRING>,
    {EXPIRED} BOOLEAN,
    {BRANCH} STRING,
    {PIPELINE_CONFIG} STRING,
    {USER_CONFIG} STRING,
    {EXPECTED_INTERIMS} INT,
    {ACTUAL_INTERIMS} INT,
    {LOGS} STRING
) STORED AS PARQUET
PARTITIONED BY ({FABRIC_UID}, {PIPELINE_URI}, {CREATED_BY})
"""

        self.component_runs_table_query = f"""
CREATE TABLE IF NOT EXISTS {self.component_table_name} (
    {UID} STRING NOT NULL,
    {COMPONENT_URI} STRING NOT NULL,
    {PIPELINE_URI} STRING,
    {PIPELINE_RUN_UID} STRING,
    {FABRIC_UID} STRING NOT NULL,
    {COMPONENT_NAME} STRING,
    {INTERIM_COMPONENT_NAME} STRING,
    {COMPONENT_TYPE} STRING,
    {INTERIM_SUBGRAPH_NAME} STRING,
    {INTERIM_PROCESS_ID} STRING,
    {INTERIM_OUT_PORT} STRING,
    {CREATED_AT} TIMESTAMP,
    {CREATED_BY} STRING NOT NULL,
    {RECORDS} BIGINT,
    {BYTES} BIGINT,
    {PARTITIONS} BIGINT,
    {EXPIRED} BOOLEAN,
    {RUN_TYPE_COLUMN} STRING,
    {JOB_URI} STRING,
    {BRANCH} STRING,
    {GEM_NAME} STRING,
    {PROCESS_ID} STRING,
    {GEM_TYPE} STRING,
    {INPUT_GEMS} ARRAY<STRUCT<{GEM_NAME}: STRING, {FROM_PORT}: STRING, {TO_PORT}: STRING, {NUM_ROWS}: BIGINT>>,
    {OUTPUT_GEMS} ARRAY<STRUCT<{GEM_NAME}: STRING, {FROM_PORT}: STRING, {TO_PORT}: STRING, {NUM_ROWS}: BIGINT>>,
    {IN_PORTS} ARRAY<STRING>,
    {OUT_PORTS} ARRAY<STRING>,
    {NUM_ROWS_OUTPUT} BIGINT,
    {STDOUT} ARRAY<STRUCT<{CONTENT}: STRING, {TIME}: BIGINT>>,
    {STDERR} ARRAY<STRUCT<{CONTENT}: STRING, {TIME}: BIGINT>>,
    {START_TIME} BIGINT,
    {END_TIME} BIGINT,
    {STATE} STRING,
    {EXCEPTION} STRUCT<{EXCEPTION_TYPE}: STRING, {MSG}: STRING, {CAUSE_MSG}: STRING, {STACK_TRACE}: STRING, {TIME}: BIGINT>
) STORED AS PARQUET
PARTITIONED BY ({FABRIC_UID}, {COMPONENT_URI}, {CREATED_BY})
"""

    def initialize(self, read_only: bool = False) -> StorageMetadata:
        """
        Initialize Hive Parquet storage for metrics.

        Args:
            read_only: If True, skip table creation

        Returns:
            HiveStorageMetadata with initialization details
        """
        if self.spark.catalog.databaseExists(self.fully_qualified_db_name):
            try:
                # List tables in the database
                show_tables_query = f"SHOW TABLES IN {self.fully_qualified_db_name}"
                tables_df = sql_with_logging(self.spark, show_tables_query)

                # Convert to list of tuples (namespace, tableName, isTemporary)
                tables_list = [
                    (row.namespace, row.tableName, row.isTemporary)
                    for row in tables_df.collect()
                ]

                # Check if our tables exist
                tables_found_in_db = any(
                    (
                        table == self.component_table_name
                        or table == self.pipeline_table_name
                    )
                    and not is_temp
                    for _, table, is_temp in tables_list
                )

                if not tables_found_in_db and not read_only:
                    self._create_schemas()

                return HiveStorageMetadata(
                    catalog_name=None, metrics_storage_details=self.storage_details
                )

            except Exception as e:
                self.logger.error(
                    "Failed to initialize Hive Metastore Storage", exc_info=e
                )
                raise
        else:
            # Database doesn't exist
            if not read_only:
                self._create_schemas()

            return HiveStorageMetadata(
                catalog_name=None, metrics_storage_details=self.storage_details
            )

    def _create_schemas(self) -> None:
        """Create database and tables with schema evolutions."""
        # Create database if configured
        if self.storage_details.create_db:
            sql_with_logging(self.spark, self.create_db_query)

        # Show databases for debugging
        sql_with_logging(self.spark, "SHOW DATABASES").show()

        # Create pipeline runs table if configured
        if self.storage_details.pipeline_metrics_table.create_table:
            sql_with_logging(self.spark, self.pipeline_runs_create_table_query)

        # Perform evolutions on pipeline runs table
        perform_up_evolutions(self.spark, self.pipeline_table_name, PipelineRunsSchema)

        # Create component runs table if configured
        if self.storage_details.component_metrics_table.create_table:
            sql_with_logging(self.spark, self.component_runs_table_query)

        # Perform evolutions on component runs table
        perform_up_evolutions(
            self.spark, self.component_table_name, ComponentRunsSchema
        )
