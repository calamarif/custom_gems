"""
Component Run Service for execution metrics.

This module provides business logic layer for component run operations,
coordinating between DAOs and handling interim data management.
"""

import logging
from typing import List, Dict, Optional, Tuple

from pyspark.sql import SparkSession, DataFrame

from prophecy.executionmetrics.componentruns.component_runs_dao import (
    ComponentRunsDAO,
    ComponentRuns,
    ComponentRunsWithStatus,
    ComponentRunsWithRunDates,
    Filters,
)
from prophecy.executionmetrics.package import InterimResponse, PipelineRuns
from prophecy.executionmetrics.evolutions.metrics_storage_initializer import (
    StorageMetadata,
)
from prophecy.executionmetrics.interims.interims_table import (
    create_interims_table,
)
from prophecy.executionmetrics.schemas.external import (
    ComponentRunIdAndInterims,
    LInterimContent,
)
from prophecy.executionmetrics.utils.common import now_utc
from prophecy.executionmetrics.utils.constants import OffloadFlags

logger = logging.getLogger(__name__)


def component_iterators_and_interims(
    interims: List[LInterimContent], port_to_run_id_multi_map: Dict[str, List[str]]
) -> List[ComponentRunIdAndInterims]:
    """
    For each (port, run_id) pair, pick the LInterimContent with the highest num_records,
    then emit a ComponentRunIdAndInterims for every component_id associated with that port.
    """
    from dataclasses import asdict

    # 1. Group and pick the max interim per (port, run_id)
    best_interim: Dict[Tuple[str, Optional[str]], LInterimContent] = {}
    for interim in interims:
        key = (interim.port, interim.runId)
        existing = best_interim.get(key)
        # Use num_records (default 0) as the ordering metric
        curr_count = interim.numRecords or 0
        best_count = existing.numRecords or 0 if existing else -1
        if existing is None or curr_count > best_count:
            best_interim[key] = interim

    # 2. Build the list of ComponentRunIdAndInterims
    results: List[ComponentRunIdAndInterims] = []
    for (port, run_id), interim in best_interim.items():
        for comp_id in port_to_run_id_multi_map.get(port, []):
            # Serialize interim to JSON (fallback to __dict__ if to_dict is not implemented)
            try:
                data = interim.to_dict()
            except AttributeError:
                try:
                    data = asdict(interim)
                except:
                    ta = interim.__dict__
            import json

            interim_json = json.dumps(data, default=str)
            results.append(
                ComponentRunIdAndInterims(
                    uid=comp_id, run_id=run_id, interims=interim_json
                )
            )

    return results


class ComponentRunService:
    """
    Service layer for component run operations.

    This class provides business logic for managing component runs,
    including querying, adding, and managing interim data.
    """

    def __init__(
        self,
        dao: ComponentRunsDAO,
        spark: SparkSession,
        storage_metadata: StorageMetadata,
    ):
        """
        Initialize the service.

        Args:
            dao: Component runs DAO
            spark: SparkSession
            storage_metadata: Storage configuration
        """
        self.dao = dao
        self.spark = spark
        self.storage_metadata = storage_metadata
        self.logger = logger

    @classmethod
    def create(
        cls, spark: SparkSession, storage_metadata: StorageMetadata
    ) -> "ComponentRunService":
        """
        Factory method to create service without user context.

        Args:
            spark: SparkSession
            storage_metadata: Storage configuration

        Returns:
            ComponentRunService instance
        """
        dao = ComponentRunsDAO(spark, storage_metadata, None)
        return cls(dao, spark, storage_metadata)

    # @classmethod
    # def create_with_user(
    #     cls,
    #     spark: SparkSession,
    #     storage_metadata: StorageMetadata,
    #     user_id: str,
    # ) -> "ComponentRunService":
    #     """
    #     Factory method to create service with user context.

    #     Args:
    #         spark: SparkSession
    #         storage_metadata: Storage configuration
    #         user_id: User ID for interims table

    #     Returns:
    #         ComponentRunService instance
    #     """
    #     interims_table = create_interims_table(spark, user_id, storage_metadata)
    #     dao = ComponentRunsDAO(spark, storage_metadata, interims_table)
    #     return cls(dao, spark, storage_metadata)

    # Query methods - delegate to DAO

    def get_by_id(
        self, uid: str, filters: Filters, expired_runs: bool = False
    ) -> ComponentRuns:
        """Get component run by ID."""
        return self.dao.get_by_id(uid, filters, expired_runs)

    def get_dataset_runs_by_dataset_id(
        self,
        dataset_uri: str,
        limit: int = 100,
        offset_uid_optional: Optional[int] = None,
        filters: Filters = None,
    ) -> List[ComponentRuns]:
        """Get dataset runs by dataset ID."""
        return self.dao.get_dataset_runs_by_dataset_id(
            dataset_uri, limit, offset_uid_optional, filters
        )

    def get_dataset_runs_by_dataset_and_fabric_id(
        self, dataset_uri: str, limit: int = 100, filters: Filters = None
    ) -> List[ComponentRuns]:
        """Get dataset runs by dataset and fabric ID."""
        return self.dao.get_dataset_runs_by_dataset_and_fabric_id(
            dataset_uri, limit, filters
        )

    def get_by_pipeline_id(
        self, pipeline_uri: str, limit: int = 100, filters: Filters = None
    ) -> List[ComponentRuns]:
        """Get component runs by pipeline ID."""
        return self.dao.get_by_pipeline_id(pipeline_uri, limit, filters)

    def get_dataset_runs_by_pipeline_id(
        self, pipeline_uri: str, limit: int = 100, filters: Filters = None
    ) -> List[ComponentRuns]:
        """Get dataset runs by pipeline ID."""
        return self.dao.get_dataset_runs_by_pipeline_id(pipeline_uri, limit, filters)

    def get_by_pipeline_run_id(
        self,
        pipeline_run_id: str,
        get_expired_runs: bool = False,
        filters: Filters = None,
    ) -> List[ComponentRuns]:
        """Get component runs by pipeline run ID."""
        return self.dao.get_by_pipeline_run_id(
            pipeline_run_id, get_expired_runs, filters
        )

    def get_ids_by_pipeline_run_id(
        self, pipeline_run_id: str, filters: Filters
    ) -> List[str]:
        """Get component run IDs by pipeline run ID."""
        return self.dao.get_ids_by_pipeline_run_id(pipeline_run_id, filters)

    def get_dataset_runs_by_pipeline_run_id(
        self, pipeline_run_id: str, filters: Filters = None
    ) -> List[ComponentRuns]:
        """Get dataset runs by pipeline run ID."""
        return self.dao.get_dataset_runs_by_pipeline_run_id(
            pipeline_run_id, filters=filters
        )

    def add_values(
        self, component_runs_entity_list: List[ComponentRuns]
    ) -> List[ComponentRuns]:
        """Add component runs."""
        return self.dao.add_values(component_runs_entity_list)

    def add_recursive(
        self,
        pipeline_run: PipelineRuns,
        component_runs_entities: List[ComponentRuns],
        interims: List[LInterimContent],
        created_by: str,
        offload_flags: OffloadFlags,
    ) -> Tuple[List[ComponentRuns], List[str]]:
        """
        Add component runs and interims recursively.

        This method handles the complex process of:
        1. Creating interims table for the user
        2. Building port to run ID mapping
        3. Adding component runs to storage
        4. Adding interim data with proper associations

        Args:
            pipeline_run: Pipeline run entity
            component_runs_entities: List of component runs to add
            interims: List of interim content
            created_by: User who created the runs

        Returns:
            Tuple of (added component runs, interim IDs)
        """
        component_runs = component_runs_entities
        # Add component runs to storage
        if offload_flags.should_offload_component_runs():
            component_runs = self.dao.add_values(component_runs_entities)

        interims_data = []
        if offload_flags.should_offload_interims():
            # Create interims table for user
            interims_table = create_interims_table(
                spark_session=self.spark,
                user=created_by,
                storage_metadata=self.storage_metadata,
            )

            # Build port to run ID mapping
            port_to_run_id_map: Dict[str, List[str]] = {}
            for run in component_runs_entities:
                port = run.interim_out_port
                if port not in port_to_run_id_map:
                    port_to_run_id_map[port] = []
                port_to_run_id_map[port].append(run.uid)

            # Convert interims to component run ID and interims format
            component_run_id_and_interims = component_iterators_and_interims(
                interims, port_to_run_id_map
            )

            # Add interims to storage
            interims_data = interims_table.add_multi(
                component_run_id_and_interims,
                created_by,
                pipeline_run.fabric_uid,
                pipeline_run.created_at or now_utc(),
            )

        return component_runs, interims_data

    def get_interims_for_pipeline_run_id(
        self, pipeline_run_id: str, updated_by: str, filters: Filters
    ) -> List[InterimResponse]:
        """Get interims for pipeline run ID."""
        return self.dao.get_interims_for_pipeline_run_id(
            pipeline_run_id, updated_by, filters
        )

    def get_dataset_runs_with_status(
        self, dataset_uri: str, limit: int = 100, filters: Filters = None
    ) -> List[ComponentRunsWithStatus]:
        """Get dataset runs with pipeline status."""
        return self.dao.get_dataset_run_with_run_status(dataset_uri, limit, filters)

    def expire(self, uid: str, filters: Filters) -> DataFrame:
        """Expire a component run."""
        return self.dao.expire(uid, filters)

    def get_detailed_dataset(
        self, dataset_run_id: str, updated_by: str, filters: Filters
    ) -> ComponentRunsWithRunDates:
        """Get detailed dataset information including interims and run dates."""
        return self.dao.get_detailed_dataset_runs(
            run_id=dataset_run_id, updated_by=updated_by, filters=filters
        )

    def get_interims_for_pipeline_run_id_detailed(
        self, run_id: str, filters: Filters
    ) -> ComponentRunsWithRunDates:
        """Get detailed interims for pipeline run ID."""
        # Empty updated_by since it's not needed for this query
        return self.dao.get_detailed_dataset_runs(run_id, "", filters)

    def refresh(self):
        """Refresh underlying tables."""
        self.dao.refresh()
