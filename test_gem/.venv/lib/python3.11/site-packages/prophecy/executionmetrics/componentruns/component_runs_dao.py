"""
Component Runs DAO (Data Access Object) for execution metrics.

This module provides data access operations for component runs, including
CRUD operations and complex queries for component execution metrics.
"""

import logging
from typing import List, Optional, Tuple, Union
import time

from pyspark.sql import SparkSession, DataFrame, Row
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    LongType,
    BooleanType,
    TimestampType,
    ArrayType,
)
from pyspark.sql import functions as F

from prophecy.executionmetrics.evolutions.models import (
    DeltaStorageMetadata,
    HiveStorageMetadata,
)
from prophecy.executionmetrics.logging_spark_session import (
    refresh_table_if_exists,
    sql_with_logging,
    write_to_delta_with_logging,
    write_to_hive_with_logging,
)
from prophecy.executionmetrics.schemas.em import (
    StoredGemEdge,
    StoredSerializableException,
    TimestampedOutput,
)
from prophecy.executionmetrics.utils.external import Filters
from prophecy.executionmetrics.utils.constants import (
    UID,
    PIPELINE_URI,
    JOB_URI,
    STATUS,
    FABRIC_UID,
    CREATED_AT,
    CREATED_BY,
    RUN_TYPE_COLUMN,
    INTERIM,
    RUN_ID,
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
from prophecy.executionmetrics.schemas.external import DatasetType
from prophecy.executionmetrics.evolutions.metrics_storage_initializer import (
    StorageMetadata,
)
from prophecy.executionmetrics.package import (
    ComponentRuns,
    ComponentRunsWithRunDates,
    ComponentRunsWithStatus,
    ComponentRunsWithStatusAndInterims,
    InterimResponse,
    RunDates,
    SchemaEvolvingDataFrame,
)
from prophecy.executionmetrics.interims.interims_table import (
    InterimsTable,
    create_interims_table,
)

logger = logging.getLogger(__name__)

# Schema definitions
OUTPUT_STREAM_TYPE = StructType(
    [StructField(CONTENT, StringType()), StructField(TIME, LongType())]
)

GEM_EDGE_TYPE = StructType(
    [
        StructField(GEM_NAME, StringType()),
        StructField(FROM_PORT, StringType()),
        StructField(TO_PORT, StringType()),
        StructField(NUM_ROWS, LongType()),
    ]
)

SERIALIZABLE_EXCEPTION_TYPE = StructType(
    [
        StructField(EXCEPTION_TYPE, StringType(), nullable=False),
        StructField(MSG, StringType(), nullable=False),
        StructField(CAUSE_MSG, StringType(), nullable=False),
        StructField(STACK_TRACE, StringType(), nullable=False),
        StructField(TIME, LongType(), nullable=False),
    ]
)

COMPONENT_RUNS_SCHEMA = StructType(
    [
        StructField(UID, StringType(), nullable=False),
        StructField(COMPONENT_URI, StringType(), nullable=False),
        StructField(PIPELINE_URI, StringType(), nullable=False),
        StructField(PIPELINE_RUN_UID, StringType(), nullable=False),
        StructField(FABRIC_UID, StringType(), nullable=False),
        StructField(COMPONENT_NAME, StringType(), nullable=False),
        StructField(INTERIM_COMPONENT_NAME, StringType(), nullable=False),
        StructField(COMPONENT_TYPE, StringType(), nullable=False),
        StructField(INTERIM_SUBGRAPH_NAME, StringType(), nullable=False),
        StructField(INTERIM_PROCESS_ID, StringType(), nullable=False),
        StructField(INTERIM_OUT_PORT, StringType(), nullable=False),
        StructField(CREATED_AT, TimestampType(), nullable=False),
        StructField(CREATED_BY, StringType(), nullable=False),
        StructField(RECORDS, LongType()),
        StructField(BYTES, LongType()),
        StructField(PARTITIONS, LongType()),
        StructField(EXPIRED, BooleanType(), nullable=False),
        StructField(RUN_TYPE_COLUMN, StringType()),
        StructField(JOB_URI, StringType()),
        StructField(BRANCH, StringType()),
        StructField(GEM_NAME, StringType()),
        StructField(PROCESS_ID, StringType()),
        StructField(GEM_TYPE, StringType()),
        StructField(INPUT_GEMS, ArrayType(GEM_EDGE_TYPE)),
        StructField(OUTPUT_GEMS, ArrayType(GEM_EDGE_TYPE)),
        StructField(IN_PORTS, ArrayType(StringType())),
        StructField(OUT_PORTS, ArrayType(StringType())),
        StructField(NUM_ROWS_OUTPUT, LongType()),
        StructField(STDOUT, ArrayType(OUTPUT_STREAM_TYPE)),
        StructField(STDERR, ArrayType(OUTPUT_STREAM_TYPE)),
        StructField(START_TIME, LongType()),
        StructField(END_TIME, LongType()),
        StructField(STATE, StringType()),
        StructField(EXCEPTION, SERIALIZABLE_EXCEPTION_TYPE),
    ]
)


class ExecutionMetricsDAO:
    """Base class for execution metrics DAOs."""

    def check_expired_row(
        self, uid: str, row: Union[ComponentRuns, dict]
    ) -> Union[ComponentRuns, dict]:
        """Check if row is expired and raise error if so."""
        expired = row.expired if hasattr(row, "expired") else row.get("expired")
        if expired:
            raise RuntimeError(f"Component run with uid `{uid}` has expired")
        return row

    def on_fail(self, uid: str):
        """Raise error for missing component run."""
        raise RuntimeError(f"Component run with uid `{uid}` not found")


class ComponentRunsDAO(ExecutionMetricsDAO):
    """
    Data Access Object for component runs.

    Provides CRUD operations and complex queries for component execution metrics.
    """

    def __init__(
        self,
        spark: SparkSession,
        storage_metadata: StorageMetadata,
        interims_table_opt: Optional[InterimsTable] = None,
    ):
        """
        Initialize the DAO.

        Args:
            spark: SparkSession to use
            storage_metadata: Storage configuration
            interims_table_opt: Optional interims table for joins
        """
        self.spark = spark
        self.storage_metadata = storage_metadata
        self.interims_table_opt = interims_table_opt
        self.logger = logger

        # Table names
        self.fully_qualified_component_runs_table_name = (
            storage_metadata.metrics_storage_details.component_metrics_table.fully_qualified_name
        )
        self.fully_qualified_pipeline_runs_table_name = (
            storage_metadata.metrics_storage_details.pipeline_metrics_table.fully_qualified_name
        )
        self.fully_qualified_interims_table_name = (
            storage_metadata.metrics_storage_details.interims_table.fully_qualified_name
        )

        self.component_runs_table_name = (
            storage_metadata.metrics_storage_details.component_metrics_table.name
        )
        self.pipeline_runs_table_name = (
            storage_metadata.metrics_storage_details.pipeline_metrics_table.name
        )

        # Partition columns
        self.partition_columns = [FABRIC_UID, COMPONENT_URI, CREATED_BY]

    def _execute_query(
        self, query: str, uid: Optional[str] = None
    ) -> Union[ComponentRuns, List[ComponentRuns]]:
        """Execute query and return results."""
        df = sql_with_logging(self.spark, query)
        df_safe = SchemaEvolvingDataFrame.schema_safe_as(df, COMPONENT_RUNS_SCHEMA)

        if uid:
            # Single result expected
            rows = df_safe.collect()
            if rows:
                return self.check_expired_row(uid, self._row_to_component_runs(rows[0]))
            else:
                self.on_fail(uid)
        else:
            # Multiple results
            return [self._row_to_component_runs(row) for row in df_safe.collect()]

    def _execute_query_with_limit(self, query: str, limit: int) -> List[ComponentRuns]:
        """Execute query with limit."""
        df = sql_with_logging(self.spark, query)
        df_safe = SchemaEvolvingDataFrame.schema_safe_as(df, COMPONENT_RUNS_SCHEMA)

        # Use toLocalIterator for efficiency with large results
        results = []
        for row in df_safe.toLocalIterator():
            results.append(self._row_to_component_runs(row))
            if len(results) >= limit:
                break

        return results

    def get_by_ids(self, uids: List[str], filters: Filters) -> List[ComponentRuns]:
        """Get component runs by multiple UIDs."""
        if not uids:
            return []

        uid_list = ", ".join([f"'{uid}'" for uid in uids])
        query = f"""
            SELECT * FROM {self.fully_qualified_component_runs_table_name} 
            WHERE {UID} IN ({uid_list}) {Filters.partition_queries(filters)}
        """
        return self._execute_query(query)

    def get_by_id(
        self, uid: str, filters: Filters, get_expired_runs: bool = False
    ) -> ComponentRuns:
        """Get component run by ID."""
        query = f"""
            SELECT * FROM {self.fully_qualified_component_runs_table_name} 
            WHERE {UID} = '{uid}' AND {EXPIRED} = {str(get_expired_runs).lower()} 
            {Filters.partition_queries(filters)}
        """
        return self._execute_query(query, uid)

    def get_dataset_run_by_id(self, uid: str, filters: Filters) -> ComponentRuns:
        """Get dataset run by ID."""
        query = f"""
            SELECT * FROM {self.fully_qualified_component_runs_table_name} 
            WHERE {UID} = '{uid}' 
            AND {COMPONENT_TYPE} IN ({DatasetType.to_list_as_string()}) 
            AND {EXPIRED} = false 
            {Filters.partition_queries(filters)}
        """
        return self._execute_query(query, uid)

    def get_dataset_runs_by_dataset_id(
        self,
        dataset_uri: str,
        limit: int = 100,
        offset_uid_optional: Optional[int] = None,
        filters: Filters = None,
    ) -> List[ComponentRuns]:
        """Get dataset runs by dataset ID with pagination."""
        max_limit = limit + (offset_uid_optional or 0)
        query = f"""
            SELECT * FROM {self.fully_qualified_component_runs_table_name} 
            WHERE {COMPONENT_URI} = '{dataset_uri}' 
            AND {EXPIRED} = false 
            {Filters.partition_queries(filters)} 
            ORDER BY {CREATED_AT} DESC 
            LIMIT {max_limit}
        """

        results = self._execute_query_with_limit(query, max_limit)

        # Apply offset
        if offset_uid_optional:
            return results[offset_uid_optional : offset_uid_optional + limit]
        return results[:limit]

    def get_dataset_runs_by_dataset_and_fabric_id(
        self, dataset_uri: str, limit: int, filters: Filters
    ) -> List[ComponentRuns]:
        """Get dataset runs by dataset and fabric ID."""
        query = f"""
            SELECT * FROM {self.fully_qualified_component_runs_table_name} 
            WHERE {COMPONENT_URI} = '{dataset_uri}' 
            {Filters.partition_queries(filters)} 
            AND {EXPIRED} = false 
            ORDER BY {CREATED_AT} DESC 
            LIMIT {limit}
        """
        return self._execute_query_with_limit(query, limit)

    def get_by_pipeline_id(
        self, pipeline_uri: str, limit: int = 100, filters: Filters = None
    ) -> List[ComponentRuns]:
        """Get component runs by pipeline ID."""
        query = f"""
            SELECT * FROM {self.fully_qualified_component_runs_table_name} 
            WHERE {PIPELINE_URI} = '{pipeline_uri}' 
            AND {EXPIRED} = false 
            {Filters.partition_queries(filters)} 
            ORDER BY {CREATED_AT} DESC 
            LIMIT {limit}
        """
        return self._execute_query_with_limit(query, limit)

    def get_dataset_runs_by_pipeline_id(
        self, pipeline_uri: str, limit: int, filters: Filters
    ) -> List[ComponentRuns]:
        """Get dataset runs by pipeline ID."""
        query = f"""
            SELECT * FROM {self.fully_qualified_component_runs_table_name} 
            WHERE {PIPELINE_URI} = '{pipeline_uri}' 
            AND {EXPIRED} = false 
            AND {COMPONENT_TYPE} IN ({DatasetType.to_list_as_string()}) 
            {Filters.partition_queries(filters)} 
            ORDER BY {CREATED_AT} DESC 
            LIMIT {limit}
        """
        return self._execute_query_with_limit(query, limit)

    def get_by_pipeline_run_id(
        self, pipeline_run_id: str, get_expired_runs: bool, filters: Filters
    ) -> List[ComponentRuns]:
        """Get component runs by pipeline run ID."""
        query = f"""
            SELECT * FROM {self.fully_qualified_component_runs_table_name} 
            WHERE {PIPELINE_RUN_UID} = '{pipeline_run_id}' 
            AND {EXPIRED} = {str(get_expired_runs).lower()} 
            {Filters.partition_queries(filters)}
        """
        return self._execute_query(query)

    def get_ids_by_pipeline_run_id(
        self, pipeline_run_id: str, filters: Filters
    ) -> List[str]:
        """Get component run IDs by pipeline run ID."""
        query = f"""
            SELECT {UID} FROM {self.fully_qualified_component_runs_table_name} 
            WHERE {PIPELINE_RUN_UID} = '{pipeline_run_id}' 
            AND {EXPIRED} = false 
            {Filters.partition_queries(filters)}
        """
        df = sql_with_logging(self.spark, query)
        return [row[0] for row in df.collect()]

    def get_dataset_runs_by_pipeline_run_id(
        self, pipeline_run_id: str, limit: int = 100, filters: Filters = None
    ) -> List[ComponentRuns]:
        """Get dataset runs by pipeline run ID."""
        query = f"""
            SELECT * FROM {self.fully_qualified_component_runs_table_name} 
            WHERE {PIPELINE_RUN_UID} = '{pipeline_run_id}' 
            AND {EXPIRED} = false 
            AND {COMPONENT_TYPE} IN ({DatasetType.to_list_as_string()}) 
            {Filters.partition_queries(filters)} 
            ORDER BY {CREATED_AT} DESC 
            LIMIT {limit}
        """
        return self._execute_query(query)

    def get_by_pipeline_run_id_and_interim_component_port(
        self, pipeline_run_uid: str, port: str, filters: Filters
    ) -> List[ComponentRuns]:
        """Get component runs by pipeline run ID and interim port."""
        query = f"""
            SELECT * FROM {self.fully_qualified_component_runs_table_name} 
            WHERE {PIPELINE_RUN_UID} = '{pipeline_run_uid}' 
            AND {INTERIM_OUT_PORT} = '{port}' 
            {Filters.partition_queries(filters)} 
            ORDER BY {CREATED_BY}
        """
        return self._execute_query(query)

    def get_interims_for_pipeline_run_id(
        self, pipeline_run_id: str, updated_by: str, filters: Filters
    ) -> List[InterimResponse]:
        """Get interims for pipeline run ID."""
        # Check if RUN_ID column exists in interims table
        interims_tables_keys = []
        if (
            self.interims_table_opt
            and RUN_ID in self.interims_table_opt.check_record_status()
        ):
            interims_tables_keys = [f"interims.{INTERIM}", f"interims.{RUN_ID}"]
        else:
            interims_tables_keys = [f"interims.{INTERIM}", "NULL AS run_id"]

        # Build select list
        component_keys = [
            f"{self.component_runs_table_name}.{UID}",
            f"{self.component_runs_table_name}.{INTERIM_COMPONENT_NAME}",
            f"{self.component_runs_table_name}.{INTERIM_OUT_PORT}",
            f"{self.component_runs_table_name}.{INTERIM_PROCESS_ID}",
        ]

        select_keys = ", ".join(component_keys + interims_tables_keys)

        query = f"""
            SELECT {select_keys} 
            FROM {self.fully_qualified_component_runs_table_name} AS {self.component_runs_table_name}
            INNER JOIN {self.fully_qualified_interims_table_name} AS interims 
            WHERE {self.component_runs_table_name}.uid = interims.uid 
            AND {self.component_runs_table_name}.{PIPELINE_RUN_UID} = '{pipeline_run_id}' 
            ORDER BY {self.component_runs_table_name}.{CREATED_AT}
        """

        df = sql_with_logging(self.spark, query)
        return [self._row_to_interim_response(row) for row in df.collect()]

    def get_dataset_run_with_run_status(
        self, dataset_uri: str, limit: int, filters: Filters
    ) -> List[ComponentRunsWithStatus]:
        """Get dataset runs with pipeline status."""
        # Use large limit for timestamp-level uniqueness assumption
        query = f"""
            SELECT {self.component_runs_table_name}.*, {self.pipeline_runs_table_name}.{STATUS} 
            FROM {self.fully_qualified_component_runs_table_name} AS {self.component_runs_table_name}
            INNER JOIN {self.fully_qualified_pipeline_runs_table_name} AS {self.pipeline_runs_table_name} 
            WHERE {self.component_runs_table_name}.{PIPELINE_RUN_UID} = {self.pipeline_runs_table_name}.{UID} 
            AND {self.component_runs_table_name}.{COMPONENT_URI} = '{dataset_uri}' 
            {Filters.partition_queries(filters, self.component_runs_table_name)} 
            AND {self.component_runs_table_name}.{EXPIRED} = false 
            ORDER BY {self.component_runs_table_name}.{CREATED_AT} DESC 
            LIMIT 1000
        """

        df = sql_with_logging(self.spark, query)
        results = [self._row_to_component_runs_with_status(row) for row in df.collect()]

        # Handle pagination with last_uid
        if filters.last_uid:
            # Drop rows until we find last_uid
            found_index = -1
            for i, run in enumerate(results):
                if run.uid == filters.last_uid:
                    found_index = i
                    break

            if found_index >= 0:
                results = results[found_index + 1 :]

        return results[:limit]

    def get_detailed_dataset_runs(
        self, run_id: str, updated_by: str, filters: Filters
    ) -> ComponentRunsWithRunDates:
        """Get detailed dataset runs with interims and run dates."""
        query = f"""
            SELECT {self.component_runs_table_name}.*, {self.pipeline_runs_table_name}.{STATUS} 
            FROM {self.fully_qualified_component_runs_table_name} AS {self.component_runs_table_name}
            INNER JOIN {self.fully_qualified_pipeline_runs_table_name} AS {self.pipeline_runs_table_name} 
            WHERE {self.component_runs_table_name}.{PIPELINE_RUN_UID} = {self.pipeline_runs_table_name}.{UID} 
            AND {self.component_runs_table_name}.{UID} = '{run_id}' 
            {Filters.partition_queries(filters, self.component_runs_table_name)} 
            {Filters.partition_queries(filters, self.pipeline_runs_table_name)}
        """

        df = sql_with_logging(self.spark, query)
        component_runs = [
            self._row_to_component_runs_with_status(row) for row in df.collect()
        ]

        if not component_runs:
            return ComponentRunsWithRunDates()

        # Get interims and run dates
        first_run = component_runs[0]
        interims = self._find_interims_for_run_id(run_id, first_run.created_by, filters)
        run_dates = self._last_n_pipeline_runs_for_component_uri(
            first_run.component_uri, filters
        )

        # Convert to ComponentRunsWithStatusAndInterims
        runs_with_interims = [
            ComponentRunsWithStatusAndInterims.from_component_runs_with_status(
                run, interims
            )
            for run in component_runs
        ]

        return ComponentRunsWithRunDates(
            component_runs_with_status_and_interims=runs_with_interims,
            run_dates=run_dates,
        )

    def expire(self, uid: str, filters: Filters) -> DataFrame:
        """Mark component run as expired."""
        query = f"""
            UPDATE {self.fully_qualified_component_runs_table_name} 
            SET {EXPIRED} = true 
            WHERE {UID} = '{uid}' 
            {Filters.partition_queries(filters)}
        """
        return sql_with_logging(self.spark, query)

    def add_values(self, component_runs: List[ComponentRuns]) -> List[ComponentRuns]:
        """Add component runs to storage."""
        if not component_runs:
            self.logger.warning(
                "No component runs to add. Probably sampling is not enabled on the pipeline."
            )
            return []

        self.logger.info(f"Adding {len(component_runs)} component runs")

        # Convert to DataFrame
        data_to_insert = self._create_dataframe(component_runs, COMPONENT_RUNS_SCHEMA)

        # Write based on storage type
        if isinstance(self.storage_metadata, DeltaStorageMetadata):
            write_to_delta_with_logging(
                self.spark,
                self.fully_qualified_component_runs_table_name,
                data_to_insert,
                partition_columns=self.partition_columns,
            )
        elif isinstance(self.storage_metadata, HiveStorageMetadata):
            if not self.storage_metadata.is_partitioning_disabled:
                self.logger.info("Writing to hive table with partitioning")
                write_to_hive_with_logging(
                    self.spark,
                    self.fully_qualified_component_runs_table_name,
                    data_to_insert,
                    partition_columns=self.partition_columns,
                )
            else:
                self.logger.info("Writing to hive table without partitioning")
                write_to_hive_with_logging(
                    self.spark,
                    self.fully_qualified_component_runs_table_name,
                    data_to_insert,
                )

        return component_runs

    def refresh(self):
        """Refresh table metadata."""
        refresh_table_if_exists(
            self.spark, self.fully_qualified_component_runs_table_name
        )

    # Helper methods

    def _find_interims_for_run_id(
        self, run_id: str, updated_by: str, filters: Filters
    ) -> Optional[str]:
        """Find interims for a run ID."""
        if not self.interims_table_opt:
            return None

        # Create interims table for the user
        interims_table = create_interims_table(
            self.spark,
            updated_by,
            filters.get_storage_metadata(self.spark, updated_by, filters.metrics_store),
        )
        return interims_table.get(run_id, filters)

    def _last_n_pipeline_runs_for_component_uri(
        self, component_uri: str, filters: Filters, limit: int = 30
    ) -> List[RunDates]:
        """Get last N pipeline runs for a component URI."""
        query = f"""
            SELECT * FROM {self.fully_qualified_component_runs_table_name} AS {self.component_runs_table_name}
            WHERE {self.component_runs_table_name}.{COMPONENT_URI} = '{component_uri}'
            {Filters.partition_queries(filters, self.component_runs_table_name)}
            ORDER BY {self.component_runs_table_name}.{CREATED_AT} DESC
            LIMIT {limit}
        """

        df = sql_with_logging(self.spark, query)
        df_safe = SchemaEvolvingDataFrame.schema_safe_as(df, COMPONENT_RUNS_SCHEMA)

        run_dates = []
        for row in df_safe.collect():
            component_run = self._row_to_component_runs(row)
            run_dates.append(RunDates.from_component_runs(component_run))

        return run_dates

    # Row conversion methods

    def _create_dataframe(
        self, data: List[ComponentRuns], schema: StructType
    ) -> DataFrame:
        """Create DataFrame from component runs."""
        # Convert dataclass instances to rows
        rows = []
        for component_run in data:
            row_data = self._component_runs_to_row(component_run)
            rows.append(row_data)

        return self.spark.createDataFrame(rows, schema)

    def _row_to_component_runs(self, row: Row) -> ComponentRuns:
        """Convert Row to ComponentRuns."""
        return ComponentRuns(
            uid=row[UID],
            component_uri=row[COMPONENT_URI],
            pipeline_uri=row[PIPELINE_URI],
            pipeline_run_uid=row[PIPELINE_RUN_UID],
            fabric_uid=row[FABRIC_UID],
            component_name=row[COMPONENT_NAME],
            interim_component_name=row[INTERIM_COMPONENT_NAME],
            component_type=row[COMPONENT_TYPE],
            interim_subgraph_name=row[INTERIM_SUBGRAPH_NAME],
            interim_process_id=row[INTERIM_PROCESS_ID],
            interim_out_port=row[INTERIM_OUT_PORT],
            created_at=row[CREATED_AT],
            created_by=row[CREATED_BY],
            records=row[RECORDS],
            bytes=row[BYTES],
            partitions=row[PARTITIONS],
            expired=row[EXPIRED],
            run_type=row[RUN_TYPE_COLUMN],
            job_uri=row[JOB_URI],
            branch=row[BRANCH],
            gem_name=row[GEM_NAME],
            process_id=row[PROCESS_ID],
            gem_type=row[GEM_TYPE],
            input_gems=(
                self._convert_gem_edges(row[INPUT_GEMS]) if row[INPUT_GEMS] else None
            ),
            output_gems=(
                self._convert_gem_edges(row[OUTPUT_GEMS]) if row[OUTPUT_GEMS] else None
            ),
            in_ports=list(row[IN_PORTS]) if row[IN_PORTS] else None,
            out_ports=list(row[OUT_PORTS]) if row[OUT_PORTS] else None,
            num_rows_output=row[NUM_ROWS_OUTPUT],
            stdout=(
                self._convert_timestamped_output(row[STDOUT]) if row[STDOUT] else None
            ),
            stderr=(
                self._convert_timestamped_output(row[STDERR]) if row[STDERR] else None
            ),
            start_time=row[START_TIME],
            end_time=row[END_TIME],
            state=row[STATE],
            exception=(
                self._convert_exception(row[EXCEPTION]) if row[EXCEPTION] else None
            ),
        )

    def _row_to_component_runs_with_status(self, row: Row) -> ComponentRunsWithStatus:
        """Convert Row to ComponentRunsWithStatus."""
        base = self._row_to_component_runs(row)
        return ComponentRunsWithStatus.from_component_runs(
            base, row[STATUS] if STATUS in row else None
        )

    def _row_to_interim_response(self, row: Row) -> InterimResponse:
        """Convert Row to InterimResponse."""
        return InterimResponse(
            uid=row[0],
            interim_component_name=row[1],
            interim_out_port=row[2],
            interim_process_id=row[3],
            interim=row[4],
            run_id=row[5] if len(row) > 5 else None,
        )

    def _component_runs_to_row(self, component_run: ComponentRuns) -> tuple:
        """Convert ComponentRuns to Row data."""
        return (
            component_run.uid,
            component_run.component_uri,
            component_run.pipeline_uri,
            component_run.pipeline_run_uid,
            component_run.fabric_uid,
            component_run.component_name,
            component_run.interim_component_name,
            component_run.component_type,
            component_run.interim_subgraph_name,
            component_run.interim_process_id,
            component_run.interim_out_port,
            component_run.created_at,
            component_run.created_by,
            component_run.records,
            component_run.bytes,
            component_run.partitions,
            component_run.expired,
            component_run.run_type,
            component_run.job_uri,
            component_run.branch,
            component_run.gem_name,
            component_run.process_id,
            component_run.gem_type,
            (
                self._convert_gem_edges_to_rows(component_run.input_gems)
                if component_run.input_gems
                else None
            ),
            (
                self._convert_gem_edges_to_rows(component_run.output_gems)
                if component_run.output_gems
                else None
            ),
            component_run.in_ports,
            component_run.out_ports,
            component_run.num_rows_output,
            (
                self._convert_timestamped_output_to_rows(component_run.stdout)
                if component_run.stdout
                else None
            ),
            (
                self._convert_timestamped_output_to_rows(component_run.stderr)
                if component_run.stderr
                else None
            ),
            component_run.start_time,
            component_run.end_time,
            component_run.state,
            (
                self._convert_exception_to_row(component_run.exception)
                if component_run.exception
                else None
            ),
        )

    def _convert_gem_edges(self, edges: List[Row]) -> List[StoredGemEdge]:
        """Convert Row gem edges to StoredGemEdge objects."""
        result = []
        for edge in edges:
            result.append(
                StoredGemEdge(
                    gem_name=edge[GEM_NAME],
                    from_port=edge[FROM_PORT],
                    to_port=edge[TO_PORT],
                    num_rows=edge[NUM_ROWS],
                )
            )
        return result

    def _convert_gem_edges_to_rows(self, edges: List[StoredGemEdge]) -> List[Row]:
        """Convert StoredGemEdge objects to Rows."""
        result = []
        for edge in edges:
            result.append(
                Row(
                    gem_name=edge.gem_name,
                    from_port=edge.from_port,
                    to_port=edge.to_port,
                    num_rows=edge.num_rows,
                )
            )
        return result

    def _convert_timestamped_output(
        self, outputs: List[Row]
    ) -> List[TimestampedOutput]:
        """Convert Row timestamped outputs to TimestampedOutput objects."""
        result = []
        for output in outputs:
            result.append(TimestampedOutput(content=output[CONTENT], time=output[TIME]))
        return result

    def _convert_timestamped_output_to_rows(
        self, outputs: List[TimestampedOutput]
    ) -> List[Row]:
        """Convert TimestampedOutput objects to Rows."""
        result = []
        for output in outputs:
            result.append(Row(content=output.content, time=output.time))
        return result

    def _convert_exception(self, exception_row: Row) -> StoredSerializableException:
        """Convert Row exception to StoredSerializableException."""
        return StoredSerializableException(
            exception_type=exception_row[EXCEPTION_TYPE],
            message=exception_row[MSG],
            cause_message=exception_row[CAUSE_MSG],
            stack_trace=exception_row[STACK_TRACE],
            time=exception_row[TIME],
        )

    def _convert_exception_to_row(self, exception: StoredSerializableException) -> Row:
        """Convert StoredSerializableException to Row."""
        row_data = {
            EXCEPTION_TYPE: exception.exception_type,
            MSG: exception.message,
            CAUSE_MSG: exception.cause_message,
            STACK_TRACE: exception.stack_trace,
            TIME: exception.time,
        }

        return Row(**row_data)
