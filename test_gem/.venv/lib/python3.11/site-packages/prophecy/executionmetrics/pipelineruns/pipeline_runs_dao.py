"""
Pipeline Runs DAO (Data Access Object) for execution metrics.

This module provides data access operations for pipeline runs, including
CRUD operations and queries for pipeline execution metrics.
"""

import logging
from typing import List, Optional

from pyspark.sql import DataFrame, Row, SparkSession
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    LongType,
    BooleanType,
    TimestampType,
    ArrayType,
    MapType,
    IntegerType,
)

from prophecy.executionmetrics.logging_spark_session import (
    refresh_table_if_exists,
    sql_with_logging,
    write_to_delta_with_logging,
    write_to_hive_with_logging,
)
from prophecy.executionmetrics.utils.external import Filters
from prophecy.executionmetrics.evolutions.models import (
    DeltaStorageMetadata,
    HiveStorageMetadata,
    StorageMetadata,
)
from prophecy.executionmetrics.package import (
    Config,
    PipelineRuns,
    SchemaEvolvingDataFrame,
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
    EXPIRED,
    BRANCH,
)

logger = logging.getLogger(__name__)


class ExecutionMetricsDAO:
    """Base class for execution metrics DAOs."""

    def check_expired_row(self, uid: str, row: PipelineRuns) -> PipelineRuns:
        """Check if row is expired and raise error if so."""
        if row.expired:
            raise RuntimeError(f"Pipeline run with uid `{uid}` has expired")
        return row

    def on_fail(self, uid: str):
        """Raise error for missing pipeline run."""
        raise RuntimeError(f"Pipeline run with uid `{uid}` not found")

    def error(self, msg: str):
        """Raise runtime error."""
        raise RuntimeError(msg)


# Schema definition for pipeline runs
PIPELINE_RUNS_SCHEMA = StructType(
    [
        StructField(UID, StringType(), nullable=False),
        StructField(PIPELINE_URI, StringType(), nullable=False),
        StructField(JOB_URI, StringType()),
        StructField(JOB_RUN_UID, StringType(), nullable=False),
        StructField(TASK_RUN_UID, StringType(), nullable=False),
        StructField(STATUS, StringType()),
        StructField(FABRIC_UID, StringType(), nullable=False),
        StructField(TIME_TAKEN, LongType()),
        StructField(ROWS_READ, LongType()),
        StructField(ROWS_WRITTEN, LongType()),
        StructField(CREATED_AT, TimestampType()),
        StructField(CREATED_BY, StringType(), nullable=False),
        StructField(RUN_TYPE_COLUMN, StringType()),
        StructField(INPUT_DATASETS, ArrayType(StringType())),
        StructField(OUTPUT_DATASETS, ArrayType(StringType())),
        StructField(WORKFLOW_CODE, MapType(StringType(), StringType())),
        StructField(EXPIRED, BooleanType()),
        StructField(BRANCH, StringType()),
        StructField(PIPELINE_CONFIG, StringType()),
        StructField(USER_CONFIG, StringType()),
        StructField(EXPECTED_INTERIMS, IntegerType()),
        StructField(ACTUAL_INTERIMS, IntegerType()),
        StructField(LOGS, StringType()),
    ]
)


class PipelineRunsDAO(ExecutionMetricsDAO):
    """
    Data Access Object for pipeline runs.

    Provides CRUD operations and queries for pipeline execution metrics.
    """

    def __init__(self, spark: SparkSession, storage_metadata: StorageMetadata):
        """
        Initialize the DAO.

        Args:
            spark: SparkSession to use
            storage_metadata: Storage configuration
        """
        self.spark = spark
        self.storage_metadata = storage_metadata
        self.logger = logger

        # Table name
        self.fully_qualified_table_name = (
            storage_metadata.metrics_storage_details.pipeline_metrics_table.fully_qualified_name
        )

        # Partition columns
        self.partition_columns = [FABRIC_UID, PIPELINE_URI, CREATED_BY]

    def _execute_query(self, query: str, uid: str) -> PipelineRuns:
        """Execute query expecting single result."""
        df = sql_with_logging(self.spark, query)
        df_safe = SchemaEvolvingDataFrame.schema_safe_as(df, PIPELINE_RUNS_SCHEMA)

        rows = df_safe.collect()
        if rows:
            pipeline_run = self._row_to_pipeline_runs(rows[0])
            return self.check_expired_row(uid, pipeline_run)
        else:
            self.on_fail(uid)

    def get_by_ids(self, uids: List[str], filters: Filters) -> List[PipelineRuns]:
        """Get pipeline runs by multiple UIDs."""
        if not uids:
            return []

        uid_list = ", ".join([f"'{uid}'" for uid in uids])
        query = f"""
            SELECT * FROM {self.fully_qualified_table_name} 
            WHERE {UID} IN ({uid_list}) {Filters.partition_queries(filters)}
        """

        df = sql_with_logging(self.spark, query)
        df_safe = SchemaEvolvingDataFrame.schema_safe_as(df, PIPELINE_RUNS_SCHEMA)

        return [self._row_to_pipeline_runs(row) for row in df_safe.collect()]

    def get_by_id(
        self, id: str, filters: Filters, expired_runs: bool = False
    ) -> PipelineRuns:
        """Get pipeline run by ID."""
        query = f"""
            SELECT * FROM {self.fully_qualified_table_name} 
            WHERE {UID} = '{id}' AND {EXPIRED} = false 
            {Filters.partition_queries(filters)} 
            LIMIT 1
        """
        return self._execute_query(query, id)

    def get_by_pipeline_id(
        self, pipeline_uri: str, limit: int = 100, filters: Filters = None
    ) -> List[PipelineRuns]:
        """Get pipeline runs by pipeline ID with pagination support."""
        # Use larger limit for millisecond-level uniqueness
        query = f"""
            SELECT * FROM {self.fully_qualified_table_name} 
            WHERE {PIPELINE_URI} = '{pipeline_uri}' AND {EXPIRED} = false 
            {Filters.partition_queries(filters)} 
            ORDER BY {CREATED_AT} DESC, {UID} ASC 
            LIMIT 1000
        """

        df = sql_with_logging(self.spark, query)
        df_safe = SchemaEvolvingDataFrame.schema_safe_as(df, PIPELINE_RUNS_SCHEMA)

        # Convert to list
        results = [self._row_to_pipeline_runs(row) for row in df_safe.toLocalIterator()]

        # Handle pagination with last_uid
        if filters and filters.last_uid:
            # Find index of last_uid
            found_index = -1
            for i, run in enumerate(results):
                if run.uid == filters.last_uid:
                    found_index = i
                    break

            if found_index >= 0:
                # Return results after last_uid
                results = results[found_index + 1 :]

        # Apply limit
        return results[:limit]

    def get_by_job_id(
        self, job_uri: str, limit: int = 100, filters: Filters = None
    ) -> List[PipelineRuns]:
        """Get pipeline runs by job ID."""
        query = f"""
            SELECT * FROM {self.fully_qualified_table_name} 
            WHERE {JOB_URI} = '{job_uri}' 
            {Filters.partition_queries(filters)} 
            ORDER BY {CREATED_AT} 
            LIMIT {limit}
        """

        df = sql_with_logging(self.spark, query)
        df_safe = SchemaEvolvingDataFrame.schema_safe_as(df, PIPELINE_RUNS_SCHEMA)

        return [self._row_to_pipeline_runs(row) for row in df_safe.collect()]

    def get_by_task_run_job_run_and_job_id_df(
        self,
        task_run_uid: str,
        job_run_uid: str,
        job_uri: Optional[str],
        filters: Filters,
    ) -> DataFrame:
        """Get pipeline runs DataFrame by task run, job run and optional job ID."""
        query = f"""
            SELECT * FROM {self.fully_qualified_table_name} 
            WHERE {TASK_RUN_UID} = '{task_run_uid}' 
            AND {JOB_RUN_UID} = '{job_run_uid}' 
            {Filters.partition_queries(filters)}
        """

        if job_uri:
            query += f" AND {JOB_URI} = '{job_uri}'"

        df = sql_with_logging(self.spark, query)
        return SchemaEvolvingDataFrame.schema_safe_as(df, PIPELINE_RUNS_SCHEMA)

    def get_by_task_run_job_run_and_job_id(
        self,
        task_run_uid: str,
        job_run_uid: str,
        job_uri: Optional[str],
        filters: Filters,
    ) -> PipelineRuns:
        """Get pipeline run by task run, job run and optional job ID."""
        df = self.get_by_task_run_job_run_and_job_id_df(
            task_run_uid, job_run_uid, job_uri, filters
        )

        rows = df.collect()
        if rows:
            return self._row_to_pipeline_runs(rows[0])
        else:
            self.error(
                f"Pipeline run with taskRunUID, jobRunUID and jobURI combination "
                f"({task_run_uid}, {job_run_uid}, {job_uri}) not found"
            )

    def expire(self, uid: str, filters: Filters) -> DataFrame:
        """Mark pipeline run as expired."""
        query = f"""
            UPDATE {self.fully_qualified_table_name} 
            SET {EXPIRED} = true 
            WHERE {UID} = '{uid}' 
            {Filters.partition_queries(filters)}
        """
        return sql_with_logging(self.spark, query)

    def historical_view(
        self, pipeline_uid: str, run_id: str, str_param: str, filters: Filters
    ) -> PipelineRuns:
        """Get historical view of pipeline run."""
        return self.get_by_id(run_id, filters)

    def add(self, pipeline_runs: PipelineRuns) -> PipelineRuns:
        """Add a new pipeline run."""
        # Create DataFrame from single pipeline run
        data_to_insert = self._create_dataframe([pipeline_runs], PIPELINE_RUNS_SCHEMA)

        # Write based on storage type
        if isinstance(self.storage_metadata, DeltaStorageMetadata):
            self.logger.info(
                f"Writing pipeline run {pipeline_runs.truncated_string()} to {self.fully_qualified_table_name}"
            )
            write_to_delta_with_logging(
                self.spark,
                self.fully_qualified_table_name,
                data_to_insert,
                partition_columns=self.partition_columns,
            )
        elif isinstance(self.storage_metadata, HiveStorageMetadata):
            if not self.storage_metadata.is_partitioning_disabled:
                self.logger.info(
                    f"Writing to Hive runs {pipeline_runs.truncated_string()} "
                    f"with partitioning to {self.fully_qualified_table_name}"
                )
                write_to_hive_with_logging(
                    self.spark,
                    self.fully_qualified_table_name,
                    data_to_insert,
                    partition_columns=self.partition_columns,
                )
            else:
                self.logger.info(
                    f"Writing to Hive runs {pipeline_runs.truncated_string()} "
                    f"without partitioning to {self.fully_qualified_table_name}"
                )
                write_to_hive_with_logging(
                    self.spark, self.fully_qualified_table_name, data_to_insert
                )

        self.logger.info(
            f"Successfully Added Pipeline Run {pipeline_runs.uid} "
            f"for pipeline {pipeline_runs.pipeline_uri}"
        )
        return pipeline_runs

    def refresh(self):
        """Refresh table metadata."""
        refresh_table_if_exists(self.spark, self.fully_qualified_table_name)

    def get_run_configs(
        self, run_id: str, updated_by: str, filters: Filters
    ) -> Optional[str]:
        """Get run configuration for a pipeline run."""
        filter_query = f"""
            SELECT {PIPELINE_CONFIG} FROM {self.fully_qualified_table_name} 
            WHERE {UID} = '{run_id}' 
            {Filters.partition_queries(filters)} 
            LIMIT 1
        """

        df = sql_with_logging(self.spark, filter_query)
        rows = df.collect()

        if rows and rows[0][0] is not None:
            # Parse config and extract run_config
            config = Config.from_js(rows[0][0])
            return config.run_config

        return None

    # Helper methods

    def _create_dataframe(
        self, data: List[PipelineRuns], schema: StructType
    ) -> DataFrame:
        """Create DataFrame from pipeline runs."""
        rows = []
        for pipeline_run in data:
            row_data = self._pipeline_runs_to_row(pipeline_run)
            rows.append(row_data)

        return self.spark.createDataFrame(rows, schema)

    def _row_to_pipeline_runs(self, row: Row) -> PipelineRuns:
        """Convert Row to PipelineRuns."""
        return PipelineRuns(
            uid=row[UID],
            pipeline_uri=row[PIPELINE_URI],
            job_uri=row[JOB_URI],
            job_run_uid=row[JOB_RUN_UID],
            task_run_uid=row[TASK_RUN_UID],
            status=row[STATUS],
            fabric_uid=row[FABRIC_UID],
            time_taken=row[TIME_TAKEN],
            rows_read=row[ROWS_READ],
            rows_written=row[ROWS_WRITTEN],
            created_at=row[CREATED_AT],
            created_by=row[CREATED_BY],
            run_type=row[RUN_TYPE_COLUMN],
            input_datasets=list(row[INPUT_DATASETS]) if row[INPUT_DATASETS] else None,
            output_datasets=(
                list(row[OUTPUT_DATASETS]) if row[OUTPUT_DATASETS] else None
            ),
            workflow_code=dict(row[WORKFLOW_CODE]) if row[WORKFLOW_CODE] else None,
            expired=row[EXPIRED],
            branch=row[BRANCH],
            pipeline_config=row[PIPELINE_CONFIG],
            user_config=row[USER_CONFIG],
            expected_interims=row[EXPECTED_INTERIMS],
            actual_interims=row[ACTUAL_INTERIMS],
            logs=row[LOGS],
        )

    def _pipeline_runs_to_row(self, pipeline_run: PipelineRuns) -> tuple:
        """Convert PipelineRuns to Row data."""
        return (
            pipeline_run.uid,
            pipeline_run.pipeline_uri,
            pipeline_run.job_uri,
            pipeline_run.job_run_uid,
            pipeline_run.task_run_uid,
            pipeline_run.status,
            pipeline_run.fabric_uid,
            pipeline_run.time_taken,
            pipeline_run.rows_read,
            pipeline_run.rows_written,
            pipeline_run.created_at,
            pipeline_run.created_by,
            pipeline_run.run_type,
            pipeline_run.input_datasets,
            pipeline_run.output_datasets,
            pipeline_run.workflow_code,
            pipeline_run.expired,
            pipeline_run.branch,
            pipeline_run.pipeline_config,
            pipeline_run.user_config,
            pipeline_run.expected_interims,
            pipeline_run.actual_interims,
            pipeline_run.logs,
        )
