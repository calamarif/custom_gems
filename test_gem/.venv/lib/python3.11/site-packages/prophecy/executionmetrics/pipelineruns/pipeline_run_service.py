"""
Pipeline Runs Service for execution metrics.

This module provides business logic layer for pipeline run operations,
including graph parsing, component extraction, and metric collection.
"""

from collections import defaultdict
from dataclasses import replace
import logging
import json
import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import uuid

from pyspark.sql import DataFrame, SparkSession

from prophecy.executionmetrics.componentruns.component_run_service import (
    ComponentRunService,
)
from prophecy.executionmetrics.evolutions.models import StorageMetadata
from prophecy.executionmetrics.package import (
    ComponentRuns,
    FileContent,
    Filters,
    PipelineRuns,
    UnavailableWorkflowJsonException,
)
from prophecy.executionmetrics.pipelineruns.pipeline_runs_dao import PipelineRunsDAO
from prophecy.executionmetrics.schemas.em import ComponentDetails, GemProgress
from prophecy.executionmetrics.schemas.external import (
    DatasetType,
    LInterimContent,
)
from prophecy.executionmetrics.utils.common import get_spark_property
from prophecy.executionmetrics.utils.constants import OffloadFlags
from prophecy.executionmetrics.utils.external import (
    check_if_entities_are_same,
    parse_uri,
)
from prophecy.executionmetrics.workflow_parser import (
    HasProcessesConnectionsPorts,
    WorkflowEdge,
    WorkflowGroup,
    get_workflow_graph,
)
from prophecy.executionmetrics.zip_file import ZipFileExtractor

logger = logging.getLogger(__name__)

# Type aliases
RecursiveDirectoryContent = Dict[str, str]


def create_entity(
    component_details: List[ComponentDetails],
    pipeline_run: PipelineRuns,
    created_by: str,
    component_runs_uid_map: Dict[Tuple[str, str, str], str] = {},
) -> List[ComponentRuns]:
    """Create component run entities from component details."""
    component_runs = []

    for details in component_details:
        component_run = ComponentRuns(
            uid=component_runs_uid_map.get(
                (
                    details.component_uri,
                    details.interim_process_id,
                    details.interim_out_port_id,
                ),
                str(uuid.uuid4()),
            ),
            component_uri=details.component_uri,
            pipeline_uri=pipeline_run.pipeline_uri,
            pipeline_run_uid=pipeline_run.uid,
            fabric_uid=pipeline_run.fabric_uid,
            component_name=details.component_name,
            interim_component_name=details.interim_component_name,
            component_type=details.component_type,
            interim_subgraph_name=details.interim_subgraph_name,
            interim_process_id=details.interim_process_id,
            interim_out_port=details.interim_out_port_id,
            created_by=created_by,
            created_at=datetime.now(),
            run_type=pipeline_run.run_type,
            job_uri=pipeline_run.job_uri,
            branch=pipeline_run.branch,
            gem_name=details.gem_progress.gem_name if details.gem_progress else None,
            process_id=(
                details.gem_progress.process_id if details.gem_progress else None
            ),
            gem_type=details.gem_progress.gem_type if details.gem_progress else None,
            input_gems=(
                [g.to_stored_gem_edge() for g in details.gem_progress.input_gems]
                if details.gem_progress
                else None
            ),
            output_gems=(
                [g.to_stored_gem_edge() for g in details.gem_progress.output_gems]
                if details.gem_progress
                else None
            ),
            in_ports=details.gem_progress.in_ports if details.gem_progress else None,
            out_ports=details.gem_progress.out_ports if details.gem_progress else None,
            num_rows_output=(
                details.gem_progress.num_rows_output if details.gem_progress else None
            ),
            stdout=details.gem_progress.stdout if details.gem_progress else None,
            stderr=details.gem_progress.stderr if details.gem_progress else None,
            start_time=(
                details.gem_progress.start_time if details.gem_progress else None
            ),
            end_time=details.gem_progress.end_time if details.gem_progress else None,
            state=details.gem_progress.state if details.gem_progress else None,
            exception=(
                details.gem_progress.exception.to_stored_serializable_exception()
                if details.gem_progress and details.gem_progress.exception
                else None
            ),
        )
        component_runs.append(component_run)

    return component_runs


def update_entity_with_interims(
    component_runs: List[ComponentRuns], interims: List[LInterimContent]
) -> List[ComponentRuns]:
    """Update component runs with interim metrics."""
    # # Group interims by port
    # interim_by_port: Dict[str, List[LInterimContent]] = {}
    # for interim in interims:
    #     if interim.port not in interim_by_port:
    #         interim_by_port[interim.port] = []
    #     interim_by_port[interim.port].append(interim)

    # # Reduce interims by port (sum metrics)
    # final_interims: Dict[str, LInterimContent] = {}
    # for port, interim_list in interim_by_port.items():
    #     # Simple reduction - take the first one and sum metrics
    #     reduced = interim_list[0]
    #     for interim in interim_list[1:]:
    #         if interim.numRecords:
    #             reduced.numRecords = (reduced.numRecords or 0) + interim.numRecords
    #         if interim.bytesProcessed:
    #             reduced.bytesProcessed = (
    #                 reduced.bytesProcessed or 0
    #             ) + interim.bytesProcessed
    #     final_interims[port] = reduced

    # # Group component runs by port
    # runs_by_port = {}
    # for run in component_runs:
    #     if run.interim_out_port not in runs_by_port:
    #         runs_by_port[run.interim_out_port] = []
    #     runs_by_port[run.interim_out_port].append(run)

    # # Update component runs with interim metrics
    # updated_runs = []
    # for run in component_runs:
    #     if run.interim_out_port in final_interims:
    #         interim = final_interims[run.interim_out_port]
    #         run.records = interim.numRecords
    #         run.bytes = interim.bytesProcessed
    #         run.partitions = interim.numPartitions
    #     updated_runs.append(run)

    # return updated_runs
    # Group component runs by their interim_out_port
    component_runs_metadata: Dict[str, List[ComponentRuns]] = defaultdict(list)
    for run in component_runs:
        component_runs_metadata[run.interim_out_port].append(run)

    # Create a mutable map to store final entities
    final_entity: Dict[str, ComponentRuns] = {}
    for run in component_runs:
        final_entity[run.uid] = run

    # Group interims by port and reduce them
    # Components within meta-gems can process different bytes for every iteration/run
    interims_by_port: Dict[str, List[LInterimContent]] = defaultdict(list)
    for interim in interims:
        interims_by_port[interim.port].append(interim)

    # Reduce interims for each port (sum them up)
    final_interims: Dict[str, LInterimContent] = {}
    for port, interims_list in interims_by_port.items():
        if interims_list:
            # Reduce using the __add__ method
            reduced_interim = interims_list[0]
            for interim in interims_list[1:]:
                reduced_interim = reduced_interim.update(interim)
            final_interims[port] = reduced_interim

    # Update component runs with interim data
    for interim in final_interims.values():
        if interim.port in component_runs_metadata:
            enhanced_runs = []
            for run in component_runs_metadata[interim.port]:
                # Create a copy of the run with updated fields
                updated_run = replace(
                    run,
                    records=interim.numRecords,
                    bytes=interim.bytesProcessed,
                    partitions=(
                        int(interim.numPartitions)
                        if interim.numPartitions is not None
                        else None
                    ),
                )
                enhanced_runs.append(updated_run)

            # Update the final entity map
            for run in enhanced_runs:
                final_entity[run.uid] = run

    # Return all values as a list
    return list(final_entity.values())


class PipelineRunsService:
    """
    Service layer for pipeline run operations.

    Handles complex business logic including workflow parsing,
    component extraction, and metric aggregation.
    """

    SUBGRAPH_LITERAL = "Subgraph"

    def __init__(
        self,
        component_service: ComponentRunService,
        dao: PipelineRunsDAO,
        spark: SparkSession,
    ):
        """
        Initialize the service.

        Args:
            component_service: Component run service
            dao: Pipeline runs DAO
            spark: SparkSession
        """
        self.component_service = component_service
        self.dao = dao
        self.spark = spark
        self.logger = logger

    @classmethod
    def create(
        cls, spark_session: SparkSession, storage_metadata: StorageMetadata
    ) -> "PipelineRunsService":
        """
        Factory method to create service without user context.

        Args:
            spark_session: SparkSession
            storage_metadata: Storage configuration

        Returns:
            PipelineRunsService instance
        """
        component_srv = ComponentRunService.create(spark_session, storage_metadata)
        dao = PipelineRunsDAO(spark_session, storage_metadata)
        return cls(component_srv, dao, spark_session)

    def get_by_id(
        self, uid: str, filters: Filters, get_expired_runs: bool = False
    ) -> PipelineRuns:
        """Get pipeline run by ID."""
        return self.dao.get_by_id(uid, filters=filters, expired_runs=get_expired_runs)

    def get_by_pipeline_id(
        self, pipeline_uri: str, limit: int = 100, filters: Filters = None
    ) -> List[PipelineRuns]:
        """Get pipeline runs by pipeline ID."""
        return self.dao.get_by_pipeline_id(pipeline_uri, limit, filters)

    def get_by_job_id(
        self, job_uri: str, limit: int = 100, filters: Filters = None
    ) -> List[PipelineRuns]:
        """Get pipeline runs by job ID."""
        return self.dao.get_by_job_id(job_uri, limit, filters)

    def get_by_task_run_job_run_and_job_id(
        self,
        task_run_uid: str,
        job_run_uid: str,
        job_uri: Optional[str],
        filters: Filters,
    ) -> PipelineRuns:
        """Get pipeline run by composite key."""
        return self.dao.get_by_task_run_job_run_and_job_id(
            task_run_uid, job_run_uid, job_uri, filters
        )

    def init_runs(
        self,
        uid: Optional[str],
        pipeline_uri: str,
        job_uri: Optional[str],
        job_run_uid: str,
        task_run_uid: str,
        status: str,
        submission_time: Optional[int],
        fabric_uid: str,
        time_taken: Optional[int] = None,
        rows_read: Optional[int] = None,
        rows_written: Optional[int] = None,
        run_type: Optional[str] = None,
        created_by: Optional[str] = None,
        code: Optional[RecursiveDirectoryContent] = None,
        interims: List[LInterimContent] = [],
        branch: Optional[str] = None,
        expected_interims: int = 0,
        actual_interims: int = 0,
        logs: str = "",
        pipeline_config_opt: Optional[str] = None,
        gem_progress_map: Optional[Dict[str, GemProgress]] = None,
        component_runs_uid_map: Dict[Tuple[str, str, str], str] = {},
    ) -> Tuple[PipelineRuns, List[ComponentRuns]]:
        """
        Add pipeline run with all associated component runs and interims.

        This is the main method that orchestrates the entire process of:
        1. Fetching/parsing workflow code
        2. Extracting component details
        3. Creating pipeline run
        4. Creating component runs
        5. Storing interim data

        Returns:
            Tuple of (component runs, interim IDs)
        """
        if interims is None:
            interims = []

        # Get pipeline code
        pipeline_code = code if code else self._fetch_code_for_pipeline(pipeline_uri)

        # Parse project ID from URI
        optional_project_id = None
        uri_parts = parse_uri(pipeline_uri)
        if uri_parts:
            optional_project_id = uri_parts[0]

        # Parse graph and extract component details
        all_component_details = self._parse_graph(pipeline_code, gem_progress_map)
        all_component_details = [
            cd.add_project_id_to_component_uri(optional_project_id)
            for cd in all_component_details
        ]

        # Extract input/output datasets
        input_datasets = [
            cd.component_uri
            for cd in all_component_details
            if cd.component_type == DatasetType.SOURCE
        ]

        output_datasets = [
            cd.component_uri
            for cd in all_component_details
            if cd.component_type == DatasetType.TARGET
        ]

        # Create pipeline run
        pipeline_run = PipelineRuns(
            uid=uid or str(uuid.uuid4()),
            pipeline_uri=pipeline_uri,
            job_uri=job_uri,
            job_run_uid=job_run_uid,
            task_run_uid=task_run_uid,
            status=status,
            fabric_uid=fabric_uid,
            time_taken=time_taken,
            rows_read=rows_read,
            rows_written=rows_written,
            created_at=(
                datetime.fromtimestamp(submission_time / 1000)
                if submission_time
                else datetime.now()
            ),
            created_by=created_by,
            run_type=run_type,
            input_datasets=input_datasets,
            output_datasets=output_datasets,
            workflow_code=pipeline_code,
            expired=False,
            branch=branch,
            pipeline_config=self._get_all_configs(pipeline_config_opt),
            expected_interims=expected_interims,
            actual_interims=actual_interims,
            logs=logs,
        )

        # Create component runs
        runs0 = create_entity(
            all_component_details, pipeline_run, created_by, component_runs_uid_map
        )
        runs = update_entity_with_interims(runs0, interims)
        return pipeline_run, runs

    def add_recursive(
        self,
        uid: Optional[str],
        pipeline_uri: str,
        job_uri: Optional[str],
        job_run_uid: str,
        task_run_uid: str,
        status: str,
        submission_time: Optional[int],
        fabric_uid: str,
        time_taken: Optional[int] = None,
        rows_read: Optional[int] = None,
        rows_written: Optional[int] = None,
        run_type: Optional[str] = None,
        created_by: Optional[str] = None,
        code: Optional[RecursiveDirectoryContent] = None,
        interims: List[LInterimContent] = [],
        branch: Optional[str] = None,
        expected_interims: int = 0,
        actual_interims: int = 0,
        logs: str = "",
        pipeline_config_opt: Optional[str] = None,
        gem_progress_map: Optional[Dict[str, GemProgress]] = None,
        offload_flags: OffloadFlags = OffloadFlags.ALL,
        component_runs_uid_map: Dict[Tuple[str, str, str], str] = {},
    ) -> Tuple[List[ComponentRuns], List[str]]:
        """
        Add pipeline run with all associated component runs and interims.

        This is the main method that orchestrates the entire process of:
        1. Fetching/parsing workflow code
        2. Extracting component details
        3. Creating pipeline run
        4. Creating component runs
        5. Storing interim data

        Returns:
            Tuple of (component runs, interim IDs)
        """
        pipeline_run, runs = self.init_runs(
            uid=uid,
            pipeline_uri=pipeline_uri,
            job_uri=job_uri,
            job_run_uid=job_run_uid,
            task_run_uid=task_run_uid,
            status=status,
            submission_time=submission_time,
            fabric_uid=fabric_uid,
            time_taken=time_taken,
            rows_read=rows_read,
            rows_written=rows_written,
            run_type=run_type,
            created_by=created_by,
            code=code,
            interims=interims,
            branch=branch,
            expected_interims=expected_interims,
            actual_interims=actual_interims,
            logs=logs,
            pipeline_config_opt=pipeline_config_opt,
            gem_progress_map=gem_progress_map,
            component_runs_uid_map=component_runs_uid_map,
        )

        # Calculate metrics based on interims
        interim_based_rows_read = self._calculate_rows_read(runs, rows_read)
        interim_based_rows_written = self._calculate_rows_written(
            interims, gem_progress_map, runs, rows_written
        )

        pipeline_dict = pipeline_run.__dict__.copy()
        pipeline_dict.pop("rows_read", None)  # Remove if exists, None prevents KeyError
        pipeline_dict.pop("rows_written", None)

        # Update pipeline run with calculated metrics
        stats_enriched_pipeline_run = PipelineRuns(
            **pipeline_dict,
            rows_read=interim_based_rows_read,
            rows_written=interim_based_rows_written,
        )

        # Add to storage
        if offload_flags.should_offload_pipeline_run():
            self.dao.add(stats_enriched_pipeline_run)

        # Add component runs and interims
        return self._add_component_runs(
            runs, stats_enriched_pipeline_run, interims, created_by, offload_flags
        )

    def expire(self, uid: str, filters: Filters) -> DataFrame:
        """Expire a pipeline run."""
        return self.dao.expire(uid, filters)

    def historical_view(
        self, pipeline_uid: str, run_id: str, filters: Filters
    ) -> PipelineRuns:
        """Get historical view of pipeline run."""
        return self.dao.historical_view(pipeline_uid, run_id, "", filters)

    def refresh(self):
        """Refresh underlying tables."""
        self.dao.refresh()

    def get_run_configs(
        self, run_id: str, updated_by: str, filters: Filters
    ) -> Optional[str]:
        """Get run configuration for a pipeline run."""
        return self.dao.get_run_configs(run_id, updated_by, filters)

    # Private helper methods

    def _get_all_configs(self, pipeline_config_opt: Optional[str]) -> Optional[str]:
        """Combine pipeline and run configurations."""
        # MOCK: RunConfigStore would be imported
        run_configs_opt = None  # Would get from RunConfigStore

        config = {"pipelineConfig": pipeline_config_opt, "runConfig": run_configs_opt}

        return json.dumps(config)

    def _add_component_runs(
        self,
        component_runs: List[ComponentRuns],
        pipeline_run: PipelineRuns,
        interims: List[LInterimContent],
        created_by: str,
        offload_flags: OffloadFlags,
    ) -> Tuple[List[ComponentRuns], List[str]]:
        """Add component runs and associated interims."""
        return self.component_service.add_recursive(
            pipeline_run, component_runs, interims, created_by, offload_flags
        )

    def _fetch_code_for_pipeline(self, pipeline_uri: str) -> RecursiveDirectoryContent:
        """Fetch workflow code for a pipeline."""
        self.logger.warning(
            f"Trying to fetch code for pipeline {pipeline_uri}. "
            f"There was some error in getting it from class path"
        )

        # Try to get from Spark configuration
        packages_path = get_spark_property("spark.prophecy.packages.path", self.spark)
        if packages_path:
            # Parse packages path JSON
            try:
                packages = json.loads(packages_path)
                for name, file_path in packages.items():
                    if check_if_entities_are_same(name, pipeline_uri):
                        return self._extract_package(file_path)
            except Exception as e:
                self.logger.error(f"Failed to parse packages path: {e}")

        # Try other Spark properties
        jars = get_spark_property("spark.jars", self.spark) or ""
        py_files = get_spark_property("spark.submit.pyFiles", self.spark) or ""
        yarn_py_files = get_spark_property("spark.yarn.dist.pyFiles", self.spark) or ""
        prophecy_packages = (
            get_spark_property("spark.prophecy.packages", self.spark) or ""
        )

        all_files = []
        for files_str in [jars, py_files, yarn_py_files, prophecy_packages]:
            if files_str:
                all_files.extend(files_str.split(","))

        # Try to find matching package
        for file_path in all_files:
            if file_path:
                try:
                    files = self._extract_package(file_path)
                    if self._does_package_match_pipeline_uri(files, pipeline_uri):
                        return files
                except Exception as e:
                    self.logger.error(f"Failed to extract {file_path}: {e}")

        raise UnavailableWorkflowJsonException(
            f"No workflow json found for pipeline {pipeline_uri}"
        )

    def _extract_package(self, file_path: str) -> RecursiveDirectoryContent:
        """Extract package contents."""
        if file_path.endswith((".zip", ".jar", ".whl")):
            files = ZipFileExtractor.extract(file_path)
            return {f.path: f.content for f in files}
        else:
            # Assume it's a directory
            result = {}
            for root, dirs, files in os.walk(file_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, file_path)
                    with open(full_path, "r") as f:
                        result[rel_path] = f.read()
            return result

    def _does_package_match_pipeline_uri(
        self, files: RecursiveDirectoryContent, pipeline_uri: str
    ) -> bool:
        """Check if package contains workflow for given pipeline URI."""
        for path, content in files.items():
            if FileContent.is_workflow_config(path):
                try:
                    workflow_json = json.loads(content)
                    if (
                        "metainfo" in workflow_json
                        and "uri" in workflow_json["metainfo"]
                    ):
                        return check_if_entities_are_same(
                            workflow_json["metainfo"]["uri"], pipeline_uri
                        )
                except Exception:
                    pass
        return False

    def _parse_graph(
        self,
        code: RecursiveDirectoryContent,
        gem_progress_map: Optional[Dict[str, GemProgress]],
    ) -> List[ComponentDetails]:
        """Parse workflow graph and extract component details."""
        # Parse workflow
        pipeline_graph = get_workflow_graph(code)
        if not pipeline_graph:
            raise RuntimeError("No workflow json in paths")

        return self._get_component_details(pipeline_graph, "graph", gem_progress_map)

    def _get_component_details(
        self,
        p_graph: HasProcessesConnectionsPorts,
        subgraph_name: str,
        gem_progress_map: Optional[Dict[str, GemProgress]],
    ) -> List[ComponentDetails]:
        """Extract component details from workflow graph."""
        # Build target port connection map
        target_port_connection_map: Dict[str, WorkflowEdge] = {}
        for connection in p_graph.connections:
            target_port_connection_map[connection.target_port] = connection

        component_details = []

        for process_id, node in p_graph.processes.items():
            if isinstance(node, WorkflowGroup):  # node.component == "Subgraph":
                # Handle subgraph
                node_subgraph_name = node.metadata.get("slug", "")
                component_name = node_subgraph_name
                component_type = node.component
                component_uri = f"1/components/{component_name}"
                interim_ports = [p.id for p in node.ports.outputs]
                gem_progress = (
                    gem_progress_map.get(process_id) if gem_progress_map else None
                )

                # Create component details for each port
                if not interim_ports:
                    component_details.append(
                        ComponentDetails(
                            component_uri=component_uri,
                            component_type=component_type,
                            process_id=process_id,
                            component_name=component_name,
                            interim_process_id=process_id,
                            interim_component_name=component_name,
                            interim_subgraph_name=subgraph_name,
                            interim_out_port_id="",
                            gem_progress=gem_progress,
                        )
                    )
                else:
                    for port in interim_ports:
                        component_details.append(
                            ComponentDetails(
                                component_uri=component_uri,
                                component_type=component_type,
                                process_id=process_id,
                                component_name=component_name,
                                interim_process_id=process_id,
                                interim_component_name=component_name,
                                interim_subgraph_name=subgraph_name,
                                interim_out_port_id=port,
                                gem_progress=gem_progress,
                            )
                        )

                # Recursively process subgraph
                component_details.extend(
                    self._get_component_details(
                        node, node_subgraph_name, gem_progress_map
                    )
                )

            else:
                # Handle regular process
                component_name = node.metadata.get("slug", "")
                component_type = node.component

                # Extract component URI
                properties = node.properties  # .get("value", {})
                component_uri = properties.get(
                    "datasetId", f"1/components/{component_name}"
                )

                # Default interim details
                interim_subgraph_name = subgraph_name
                interim_node = node
                interim_ports = [p.id for p in node.ports.outputs]

                # Special handling for Target components
                if component_type == "Target" and node.ports.inputs:
                    first_input_port = node.ports.inputs[0].id
                    connection, graph, target_subgraph_name = (
                        self._fetch_target_component_source_port(
                            target_port_connection_map,
                            p_graph,
                            subgraph_name,
                            first_input_port,
                        )
                    )

                    if connection:
                        interim_node = graph.processes.get(connection.source)
                        interim_subgraph_name = target_subgraph_name
                        interim_ports = [connection.source_port]

                interim_process_id = interim_node.id
                interim_component_name = interim_node.metadata.get("slug", "")
                gem_progress = (
                    gem_progress_map.get(process_id) if gem_progress_map else None
                )

                # Create component details
                if not interim_ports:
                    component_details.append(
                        ComponentDetails(
                            component_uri=component_uri,
                            component_type=component_type,
                            process_id=process_id,
                            component_name=component_name,
                            interim_process_id=interim_process_id,
                            interim_component_name=interim_component_name,
                            interim_subgraph_name=interim_subgraph_name,
                            interim_out_port_id="",
                            gem_progress=gem_progress,
                        )
                    )
                else:
                    for port in interim_ports:
                        component_details.append(
                            ComponentDetails(
                                component_uri=component_uri,
                                component_type=component_type,
                                process_id=process_id,
                                component_name=component_name,
                                interim_process_id=interim_process_id,
                                interim_component_name=interim_component_name,
                                interim_subgraph_name=interim_subgraph_name,
                                interim_out_port_id=port,
                                gem_progress=gem_progress,
                            )
                        )

        return component_details

    def _fetch_target_component_source_port(
        self,
        target_port_connection_map: Dict[str, WorkflowEdge],
        p_graph: HasProcessesConnectionsPorts,
        subgraph_name: str,
        port: str,
    ) -> Tuple[Optional[WorkflowEdge], HasProcessesConnectionsPorts, str]:
        """Recursively fetch source port for target component."""
        connection = target_port_connection_map.get(port)
        if not connection:
            return None, p_graph, subgraph_name

        source_node = p_graph.processes.get(connection.source)
        if not source_node:
            return connection, p_graph, subgraph_name

        if isinstance(source_node, WorkflowGroup):
            # Recurse into subgraph
            source_node_subgraph_name = source_node.metadata.get("slug", "")
            subgraph_target_port_map = {}
            for conn in source_node.connections:
                subgraph_target_port_map[conn.target_port] = conn

            return self._fetch_target_component_source_port(
                subgraph_target_port_map,
                source_node,
                source_node_subgraph_name,
                connection.source_port,
            )
        else:
            return connection, p_graph, subgraph_name

    def _calculate_rows_read(
        self, runs: List[ComponentRuns], rows_read: Optional[int]
    ) -> Optional[int]:
        """Calculate rows read from component runs."""
        source_runs = [
            r
            for r in runs
            if r.component_type == DatasetType.SOURCE and r.records is not None
        ]

        if not source_runs:
            return rows_read

        # Sum records from source runs or num_rows_output
        total = sum(
            r.num_rows_output if r.num_rows_output is not None else r.records
            for r in source_runs
        )

        return total

    def _calculate_rows_written(
        self,
        interims: List[LInterimContent],
        gem_progress_map: Optional[Dict[str, GemProgress]],
        runs: List[ComponentRuns],
        rows_written: Optional[int],
    ) -> Optional[int]:
        """Calculate rows written from various sources."""
        # Try to calculate from gem progress map
        if interims and gem_progress_map:
            target_gems = [
                gp
                for gp in gem_progress_map.values()
                if gp.gem_type == DatasetType.TARGET
            ]

            if target_gems:
                total = 0
                for gem in target_gems:
                    if gem.input_gems:
                        for input_gem in gem.input_gems:
                            if hasattr(input_gem, "num_rows") and input_gem.num_rows:
                                total += input_gem.num_rows

                if total > 0:
                    return total

        # Fallback to target runs
        target_runs = [
            r
            for r in runs
            if r.component_type == DatasetType.TARGET and r.records is not None
        ]

        if not target_runs:
            return rows_written

        return sum(r.records for r in target_runs)
