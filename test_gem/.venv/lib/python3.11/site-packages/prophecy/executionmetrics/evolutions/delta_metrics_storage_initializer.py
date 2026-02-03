"""
Delta Metrics Storage Initializer for execution metrics.

This module handles initialization of Delta Lake tables for storing execution metrics.
"""

import logging

from pyspark.sql import SparkSession
from pyspark.sql.types import *
from pyspark.sql.utils import AnalysisException

from prophecy.executionmetrics.evolutions.models import (
    DeltaStorageMetadata,
    MetricsStorageDetails,
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


class ExecutionMetricsException(Exception):
    """Custom exception for execution metrics errors."""

    pass


def base_location(spark: SparkSession, suffix: str) -> str:
    """
    Get the base location for Delta tables.

    Args:
        spark: SparkSession
        suffix: Suffix to append to base path

    Returns:
        Base location path
    """
    spark_delta_path_prefix = "spark.prophecy.delta.path.prefix"
    default_path = "/prophecy/metadata/executionmetrics"
    try:
        base_path = spark.conf.get(spark_delta_path_prefix, default_path)
    except Exception as e:
        base_path = default_path
    return f"{base_path}{suffix}"


class DeltaMetricsStorageInitializer(MetricsStorageInitializer):
    """
    Initializer for Delta Lake storage of execution metrics.

    This class handles creation and initialization of Delta tables
    for storing pipeline and component execution metrics.
    """

    def __init__(self, spark: SparkSession, storage_details: MetricsStorageDetails):
        """
        Initialize the Delta storage initializer.

        Args:
            spark: SparkSession to use
            storage_details: Details about the storage configuration
        """
        super().__init__(spark, storage_details)
        self.logger = logger

        # Extract table names and database info
        self.fq_pr = storage_details.pipeline_metrics_table.fully_qualified_name
        self.fq_cr = storage_details.component_metrics_table.fully_qualified_name

        # Parse pipeline metrics namespace
        self.pipeline_metrics_namespace_split = self.fq_pr.split(".")

        # Determine fully qualified database name
        namespace_db_split = self.pipeline_metrics_namespace_split[:-1]
        if not namespace_db_split:
            self.fully_qualified_db_name = "default"
        else:
            self.fully_qualified_db_name = ".".join(namespace_db_split)

        # Extract table names
        self.pipeline_runs_table_name = self.pipeline_metrics_namespace_split[-1]
        self.component_runs_table_name = self.fq_cr.split(".")[-1]

        # Set base object location
        self.base_object_location = base_location(spark, storage_details.db_suffix)

        # Extract catalog name if using 3-level namespace
        if len(self.pipeline_metrics_namespace_split) >= 3:
            self.catalog_name = self.pipeline_metrics_namespace_split[0]
        else:
            self.catalog_name = None

        # SQL queries
        self.create_db_query = (
            f"CREATE DATABASE IF NOT EXISTS {self.fully_qualified_db_name} "
            f"COMMENT 'prophecy metadata' LOCATION '{self.base_object_location}'"
        )

        self.pipeline_runs_create_table_query = f"""
CREATE TABLE IF NOT EXISTS {self.fq_pr} (
    {UID} STRING NOT NULL,
    {PIPELINE_URI} STRING NOT NULL,
    {JOB_URI} STRING,
    {JOB_RUN_UID} STRING NOT NULL,
    {TASK_RUN_UID} STRING NOT NULL,
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
    {EXPIRED} BOOLEAN NOT NULL,
    {BRANCH} STRING,
    {PIPELINE_CONFIG} STRING,
    {USER_CONFIG} STRING,
    {EXPECTED_INTERIMS} INT,
    {ACTUAL_INTERIMS} INT,
    {LOGS} STRING)
USING DELTA
PARTITIONED BY ({FABRIC_UID}, {PIPELINE_URI}, {CREATED_BY})
LOCATION '{self.base_object_location}/{self.pipeline_runs_table_name}'
"""

        self.component_runs_create_table_query = f"""
CREATE TABLE IF NOT EXISTS {self.fq_cr} (
    {UID} STRING NOT NULL,
    {COMPONENT_URI} STRING NOT NULL,
    {PIPELINE_URI} STRING NOT NULL,
    {PIPELINE_RUN_UID} STRING NOT NULL,
    {FABRIC_UID} STRING NOT NULL,
    {COMPONENT_NAME} STRING NOT NULL,
    {INTERIM_COMPONENT_NAME} STRING NOT NULL,
    {COMPONENT_TYPE} STRING NOT NULL,
    {INTERIM_SUBGRAPH_NAME} STRING NOT NULL,
    {INTERIM_PROCESS_ID} STRING NOT NULL,
    {INTERIM_OUT_PORT} STRING NOT NULL,
    {CREATED_AT} TIMESTAMP NOT NULL,
    {CREATED_BY} STRING NOT NULL,
    {RECORDS} BIGINT,
    {BYTES} BIGINT,
    {PARTITIONS} BIGINT,
    {EXPIRED} BOOLEAN NOT NULL,
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
)
USING DELTA
PARTITIONED BY ({FABRIC_UID}, {COMPONENT_URI}, {CREATED_BY})
LOCATION '{self.base_object_location}/{self.component_runs_table_name}'
"""

    def initialize(self, read_only: bool = False) -> DeltaStorageMetadata:
        """
        Initialize Delta storage for metrics.

        Args:
            read_only: If True, skip table creation

        Returns:
            DeltaStorageMetadata with initialization details

        Raises:
            ExecutionMetricsException: If Unity Catalog setup is required
        """
        # Enable multi-cluster writes for Delta
        self.spark.conf.set("spark.databricks.delta.multiClusterWrites.enabled", "true")

        self.logger.info("Checking if the table and database exist")
        show_tables_query = f"show tables in {self.fully_qualified_db_name}"

        if not read_only:
            try:
                # Try to list tables in the database
                tables_df = self.spark.sql(show_tables_query)
                tables_list = []
                for row in tables_df.collect():
                    row_dict = row.asDict()
                    tables_list.append(
                        (
                            row_dict.get("namespace") or row_dict.get("database"),
                            row_dict.get("tableName"),
                            row_dict.get("isTemporary"),
                        )
                    )

                # tables_list = [
                #     (row.namespace, row.tableName, row.isTemporary)
                #     for row in tables_df.collect()
                # ]

                # Check if our tables exist
                tables_exist = any(
                    (
                        table == self.component_runs_table_name
                        or table == self.pipeline_runs_table_name
                    )
                    and not is_temp
                    for _, table, is_temp in tables_list
                )

                if not tables_exist:
                    self._create_db()
                else:
                    self.logger.info("Tables already exist")

            except AnalysisException as e:
                self.logger.info(
                    f"Error while initializing DeltaMetricsStorage - {e}, {e.getSqlState()}, {e.getErrorClass()}, {e.getMessageParameters()}"
                )
                if "SCHEMA_NOT_FOUND" in str(e):
                    self._create_db()
                elif "NoSuchCatalogException" in e.__class__.__name__:
                    self._unity_exception()
                else:
                    raise
            except Exception as e:
                self.logger.error(f"Error during initialization: {e}")
                raise

        return DeltaStorageMetadata(
            base_object_location=self.base_object_location,
            catalog_name=self.catalog_name,
            metrics_storage_details=self.storage_details,
        )

    def _unity_exception(self):
        """Raise exception for Unity Catalog setup."""
        raise ExecutionMetricsException(
            "For Unity Catalog, please create the catalog, database and tables manually by following this doc "
            "https://docs.prophecy.io/low-code-spark/execution/execution-metrics#creating-tables-for-databricks"
        )

    def _missing_tables(self):
        """Raise exception for missing tables."""
        raise ExecutionMetricsException(
            f"Execution Metrics Tables (`{self.fq_pr}` and `{self.fq_cr}`) don't exist. "
            f"Please pre-create them by following this doc "
            f"https://docs.prophecy.io/low-code-spark/execution/execution-metrics#creating-tables-for-databricks"
        )

    def _create_db(self):
        """Create database and tables if needed."""
        if self.storage_details.create_db:
            self.logger.info("Trying to create database for Execution Metrics")
            try:
                sql_with_logging(self.spark, self.create_db_query)
            except AnalysisException as e:
                if "Unity Catalog" in str(e):
                    self._unity_exception()
                else:
                    raise
        else:
            self.logger.info(
                "not trying to create database and assuming it would exist"
            )

        # Use catalog if specified
        if self.catalog_name:
            sql_with_logging(self.spark, f"USE CATALOG {self.catalog_name}")

        if self.storage_details.pipeline_metrics_table.create_table:
            self.logger.info("Trying to create Pipeline Runs tables now")
            sql_with_logging(self.spark, self.pipeline_runs_create_table_query)
            self.logger.info("Trying to create Component Runs tables now")
            sql_with_logging(self.spark, self.component_runs_create_table_query)
            self.logger.info("Created both tables")
        elif self._table_exists(self.fq_pr) and self._table_exists(self.fq_cr):
            self.logger.info("Both tables exist.")
        else:
            self._missing_tables()

        # TODO (KK)
        # Note: Z-ordering optimization is available in Delta 2.0+
        # Can be applied on client cluster as a one-time operation

    def _table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        try:
            return self.spark.catalog.tableExists(table_name)
        except Exception:
            return False
