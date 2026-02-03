"""
Execution metrics package for Apache Spark SQL operations.

This module handles data schema conversion from snake_case to camelCase,
execution tracking, and metrics storage for pipeline runs and components.
"""

import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from collections import defaultdict

# PySpark imports
from pyspark.sql import DataFrame
from pyspark.sql.functions import lit
from pyspark.sql.types import StructType

from prophecy.executionmetrics.schemas.em import (
    ComponentDetails,
    SerializableException,
    StoredGemEdge,
    StoredSerializableException,
    TimestampedOutput,
)
from prophecy.executionmetrics.schemas.external import LInterimContent
from prophecy.executionmetrics.utils.common import now_utc, timestamp_from_long
from prophecy.executionmetrics.utils.external import Filters

logger = logging.getLogger(__name__)


def datetime_to_posix_ts_millis(input: Optional[datetime]) -> Optional[int]:
    return int(input.timestamp() * 1000) if input else None


# Abstract base class for execution metrics entities
@dataclass
class ExecutionMetricsEntity(ABC):
    """Base class for all execution metrics entities."""

    pass


@dataclass
class PipelineRuns(ExecutionMetricsEntity):
    """Represents pipeline run execution metrics."""

    uid: str
    fabric_uid: str
    pipeline_uri: str
    created_by: str
    job_run_uid: str
    task_run_uid: str
    status: str
    run_type: str
    job_uri: Optional[str] = None
    time_taken: Optional[int] = None
    rows_read: Optional[int] = None
    rows_written: Optional[int] = None
    created_at: Optional[datetime] = None
    input_datasets: Optional[List[str]] = None
    output_datasets: Optional[List[str]] = None
    workflow_code: Optional[Dict[str, str]] = None
    expired: Optional[bool] = False
    branch: Optional[str] = None
    pipeline_config: Optional[str] = None
    user_config: Optional[str] = None
    expected_interims: Optional[int] = None
    actual_interims: Optional[int] = None
    logs: Optional[str] = None

    def truncated_string(self) -> str:
        """Get truncated string representation for logging."""
        truncated = self.__dict__.copy()
        # Truncate workflow code
        if self.workflow_code:
            truncated["workflow_code"] = {
                k: v[:100] for k, v in self.workflow_code.items()
            }
        # Truncate logs
        if self.logs:
            truncated["logs"] = self.logs[:100]
        return str(truncated)


@dataclass
class ComponentRuns(ExecutionMetricsEntity):
    """Represents component run execution metrics."""

    uid: str
    component_uri: str
    pipeline_uri: str
    pipeline_run_uid: str
    fabric_uid: str
    component_name: str
    interim_component_name: str
    component_type: str
    interim_subgraph_name: str
    interim_process_id: str
    interim_out_port: str
    created_by: str
    created_at: Optional[datetime] = None
    records: Optional[int] = None
    bytes: Optional[int] = None
    partitions: Optional[int] = None
    expired: Optional[bool] = False
    run_type: Optional[str] = None
    job_uri: Optional[str] = None
    branch: Optional[str] = None
    gem_name: Optional[str] = None
    process_id: Optional[str] = None
    gem_type: Optional[str] = None
    input_gems: Optional[List[StoredGemEdge]] = None
    output_gems: Optional[List[StoredGemEdge]] = None
    in_ports: Optional[List[str]] = None
    out_ports: Optional[List[str]] = None
    num_rows_output: Optional[int] = None
    stdout: Optional[List[TimestampedOutput]] = None
    stderr: Optional[List[TimestampedOutput]] = None
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    state: Optional[str] = None
    exception: Optional[StoredSerializableException] = None


class ComponentRunsFactory:
    """Factory methods for creating ComponentRuns entities."""

    @staticmethod
    def create_entity(
        all_component_details: List["ComponentDetails"],
        pipeline_run: PipelineRuns,
        created_by: str,
    ) -> List[ComponentRuns]:
        """Create ComponentRuns entities from component details and pipeline run."""
        result = []

        for component_details in all_component_details:
            uid = str(uuid.uuid4())

            gem_progress = component_details.gem_progress

            component_run = ComponentRuns(
                uid=uid,
                component_uri=component_details.component_uri,
                pipeline_run_uid=pipeline_run.uid,
                pipeline_uri=pipeline_run.pipeline_uri,
                fabric_uid=pipeline_run.fabric_uid,
                component_name=component_details.component_name,
                interim_component_name=component_details.interim_component_name,
                component_type=component_details.component_type,
                interim_subgraph_name=component_details.interim_subgraph_name,
                interim_process_id=component_details.interim_process_id,
                interim_out_port=component_details.interim_out_port_id,
                created_by=created_by,
                created_at=now_utc(),
                run_type=pipeline_run.run_type,
                job_uri=pipeline_run.job_uri,
                branch=pipeline_run.branch,
                gem_name=gem_progress.gem_name if gem_progress else None,
                process_id=gem_progress.process_id if gem_progress else None,
                gem_type=gem_progress.gem_type if gem_progress else None,
                input_gems=(
                    [edge.to_stored_gem_edge() for edge in gem_progress.input_gems]
                    if gem_progress and gem_progress.input_gems
                    else None
                ),
                output_gems=(
                    [edge.to_stored_gem_edge() for edge in gem_progress.output_gems]
                    if gem_progress and gem_progress.output_gems
                    else None
                ),
                in_ports=gem_progress.in_ports if gem_progress else None,
                out_ports=gem_progress.out_ports if gem_progress else None,
                num_rows_output=gem_progress.num_rows_output if gem_progress else None,
                stdout=gem_progress.stdout if gem_progress else None,
                stderr=gem_progress.stderr if gem_progress else None,
                start_time=gem_progress.start_time if gem_progress else None,
                end_time=gem_progress.end_time if gem_progress else None,
                state=gem_progress.state if gem_progress else None,
                exception=(
                    gem_progress.exception.to_stored_serializable_exception()
                    if gem_progress and gem_progress.exception
                    else None
                ),
            )
            result.append(component_run)

        return result

    @staticmethod
    def create_entity_with_interims(
        component_runs: List[ComponentRuns], interims: List[LInterimContent]
    ) -> List[ComponentRuns]:
        """Create enhanced ComponentRuns entities with interim data."""
        # Group component runs by interim_out_port
        component_runs_metadata = defaultdict(list)
        for run in component_runs:
            component_runs_metadata[run.interim_out_port].append(run)

        final_entity = {run.uid: run for run in component_runs}

        # Group interims by port and reduce
        final_interims = {}
        interims_by_port = defaultdict(list)
        for interim in interims:
            interims_by_port[interim.port].append(interim)

        for port, interim_list in interims_by_port.items():
            # MOCK: Implementing interim reduction (+ operator)
            reduced_interim = interim_list[0]
            for interim in interim_list[1:]:
                reduced_interim = reduced_interim + interim
            final_interims[port] = reduced_interim

        # Enhance runs with interim data
        for interim in final_interims.values():
            enhanced_runs = component_runs_metadata.get(interim.port, [])
            for run in enhanced_runs:
                enhanced_run = ComponentRuns(
                    uid=run.uid,
                    component_uri=run.component_uri,
                    pipeline_uri=run.pipeline_uri,
                    pipeline_run_uid=run.pipeline_run_uid,
                    fabric_uid=run.fabric_uid,
                    component_name=run.component_name,
                    interim_component_name=run.interim_component_name,
                    component_type=run.component_type,
                    interim_subgraph_name=run.interim_subgraph_name,
                    interim_process_id=run.interim_process_id,
                    interim_out_port=run.interim_out_port,
                    created_by=run.created_by,
                    created_at=run.created_at,
                    records=interim.num_records,
                    bytes=interim.bytes_processed,
                    partitions=(
                        int(interim.num_partitions) if interim.num_partitions else None
                    ),
                    expired=run.expired,
                    run_type=run.run_type,
                    job_uri=run.job_uri,
                    branch=run.branch,
                    gem_name=run.gem_name,
                    process_id=run.process_id,
                    gem_type=run.gem_type,
                    input_gems=run.input_gems,
                    output_gems=run.output_gems,
                    in_ports=run.in_ports,
                    out_ports=run.out_ports,
                    num_rows_output=run.num_rows_output,
                    stdout=run.stdout,
                    stderr=run.stderr,
                    start_time=run.start_time,
                    end_time=run.end_time,
                    state=run.state,
                    exception=run.exception,
                )
                final_entity[run.uid] = enhanced_run

        return list(final_entity.values())


@dataclass
class ComponentRunsWithStatus(ExecutionMetricsEntity):
    """Component runs with status information."""

    uid: str
    component_uri: str
    pipeline_run_uid: str
    pipeline_uri: str
    fabric_uid: str
    component_name: str
    interim_component_name: str
    created_by: str
    component_type: str
    interim_out_port: str
    interim_subgraph_name: str
    interim_process_id: str
    records: Optional[int] = None
    bytes: Optional[int] = None
    partitions: Optional[int] = None
    created_at: Optional[datetime] = None
    expired: Optional[bool] = False
    status: Optional[str] = None
    job_uri: Optional[str] = None
    run_type: Optional[str] = None
    branch: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "uid": self.uid,
            "component_uri": self.component_uri,
            "pipeline_run_uid": self.pipeline_run_uid,
            "pipeline_uri": self.pipeline_uri,
            "fabric_uid": self.fabric_uid,
            "component_name": self.component_name,
            "interim_component_name": self.interim_component_name,
            "records": self.records,
            "bytes": self.bytes,
            "partitions": self.partitions,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
            "component_type": self.component_type,
            "interim_out_port": self.interim_out_port,
            "interim_subgraph_name": self.interim_subgraph_name,
            "interim_process_id": self.interim_process_id,
            "expired": self.expired,
            "status": self.status,
            "job_uri": self.job_uri,
            "run_type": self.run_type,
            "branch": self.branch,
        }

    @classmethod
    def from_component_runs(
        cls, component_run: ComponentRuns, status: Optional[str]
    ) -> "ComponentRunsWithStatus":
        return ComponentRunsWithStatus(
            uid=component_run.uid,
            component_uri=component_run.component_uri,
            pipeline_run_uid=component_run.pipeline_run_uid,
            pipeline_uri=component_run.pipeline_uri,
            fabric_uid=component_run.fabric_uid,
            component_name=component_run.component_name,
            interim_component_name=component_run.interim_component_name,
            component_type=component_run.component_type,
            interim_out_port=component_run.interim_out_port,
            interim_subgraph_name=component_run.interim_subgraph_name,
            interim_process_id=component_run.interim_process_id,
            created_by=component_run.created_by,
            records=component_run.records,
            bytes=component_run.bytes,
            partitions=component_run.partitions,
            created_at=component_run.created_at,
            expired=component_run.expired,
            status=status,  # This will be set separately
            job_uri=component_run.job_uri,
            run_type=component_run.run_type,
            branch=component_run.branch,
        )


@dataclass
class ComponentRunsWithStatusAndInterims(ExecutionMetricsEntity):
    """Component runs with status and interim information."""

    uid: str
    component_uri: str
    pipeline_run_uid: str
    pipeline_uri: str
    fabric_uid: str
    component_name: str
    interim_component_name: str
    created_by: str
    component_type: str
    interim_out_port: str
    interim_subgraph_name: str
    interim_process_id: str
    records: Optional[int] = None
    bytes: Optional[int] = None
    partitions: Optional[int] = None
    created_at: Optional[datetime] = None
    expired: Optional[bool] = False
    status: Optional[str] = None
    interim: Optional[str] = None
    job_uri: Optional[str] = None
    run_type: Optional[str] = None

    @classmethod
    def from_component_runs_with_status(
        cls, run: ComponentRunsWithStatus, interims: Optional[str] = None
    ) -> "ComponentRunsWithStatusAndInterims":
        """Create from ComponentRunsWithStatus."""
        return cls(
            uid=run.uid,
            component_uri=run.component_uri,
            pipeline_run_uid=run.pipeline_run_uid,
            pipeline_uri=run.pipeline_uri,
            fabric_uid=run.fabric_uid,
            component_name=run.component_name,
            interim_component_name=run.interim_component_name,
            records=run.records,
            bytes=run.bytes,
            partitions=run.partitions,
            created_at=run.created_at,
            created_by=run.created_by,
            component_type=run.component_type,
            interim_out_port=run.interim_out_port,
            interim_subgraph_name=run.interim_subgraph_name,
            interim_process_id=run.interim_process_id,
            expired=run.expired,
            status=run.status,
            interim=interims,
            run_type=run.run_type,
            job_uri=run.job_uri,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "uid": self.uid,
            "component_uri": self.component_uri,
            "pipeline_run_uid": self.pipeline_run_uid,
            "pipeline_uri": self.pipeline_uri,
            "fabric_uid": self.fabric_uid,
            "component_name": self.component_name,
            "interim_component_name": self.interim_component_name,
            "records": self.records,
            "bytes": self.bytes,
            "partitions": self.partitions,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
            "component_type": self.component_type,
            "interim_out_port": self.interim_out_port,
            "interim_subgraph_name": self.interim_subgraph_name,
            "interim_process_id": self.interim_process_id,
            "expired": self.expired,
            "status": self.status,
            "interim": self.interim,
            "job_uri": self.job_uri,
            "run_type": self.run_type,
        }


# Response classes for camelCase conversion
@dataclass
class ResponseCamelCase(ABC):
    """Abstract base class for camelCase responses."""

    # submission_time: Optional[datetime]

    @abstractmethod
    def get_uid(self) -> str:
        """Get unique identifier."""
        pass


class ResponseOrder:
    """Ordering utility for ResponseCamelCase objects."""

    @staticmethod
    def compare(x: ResponseCamelCase, y: ResponseCamelCase) -> int:
        """Compare two ResponseCamelCase objects by submission time."""
        x_time = x.submission_time
        y_time = y.submission_time

        if x_time is not None and y_time is not None:
            if x_time < y_time:
                return -1
            elif x_time > y_time:
                return 1
            else:
                return 0
        elif x_time is not None and y_time is None:
            return -1
        elif x_time is None and y_time is not None:
            return 1
        else:
            return 0


@dataclass
class NextFilters:
    """Pagination filters for responses."""

    last_submission_time_in_ms: datetime
    last_uid: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "last_submission_time_in_ms": self.last_submission_time_in_ms.isoformat(),
            "last_uid": self.last_uid,
        }


@dataclass
class ResponsesAsList:
    """Generic paginated response container."""

    rows: List[ResponseCamelCase]
    limit: int
    next_filters: Optional[NextFilters] = None
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rows": [
                row.to_dict() if hasattr(row, "to_dict") else str(row)
                for row in self.rows
            ],
            "limit": self.limit,
            "next_filters": self.next_filters.to_dict() if self.next_filters else None,
            "message": self.message,
        }


class ResponseWrapper:
    """Wrapper utility for creating paginated responses."""

    @staticmethod
    def wrapEmpty(limit: Optional[int] = None) -> ResponsesAsList:
        return ResponsesAsList(rows=[], limit=limit)

    @staticmethod
    def wrap(
        response: List[ResponseCamelCase], limit: Optional[int] = None
    ) -> ResponsesAsList:
        """Wrap response list with pagination information."""
        response_size = len(response)
        next_filters = None

        if response:
            if limit is not None and response_size >= limit:
                # Find minimum element by submission time
                min_element = min(response, key=ResponseOrder.compare)
                next_filters = NextFilters(
                    last_submission_time_in_ms=min_element.submission_time or now_utc(),
                    last_uid=min_element.get_uid(),
                )

        return ResponsesAsList(
            rows=response, limit=response_size, next_filters=next_filters
        )


@dataclass
class InterimResponse:
    """Response for interim data."""

    uid: str
    interim_component_name: str
    interim_out_port: str
    interim_process_id: str
    interim: str
    run_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "uid": self.uid,
            "interim_component_name": self.interim_component_name,
            "interim_out_port": self.interim_out_port,
            "interim_process_id": self.interim_process_id,
            "interim": self.interim,
            "run_id": self.run_id,
        }


@dataclass
class InterimResponseCamelCase(ResponseCamelCase):
    """CamelCase version of interim response."""

    uid: str
    interim_component_name: str
    interim_out_port: str
    interim_process_id: str
    interim: str
    submission_time: Optional[datetime] = None
    run_id: Optional[str] = None
    run_config: Optional[str] = None

    def get_uid(self) -> str:
        """Get unique identifier."""
        return self.uid

    def __str__(self) -> str:
        """String representation with redacted sensitive data."""
        return (
            f"InterimResponseCamelCase({self.uid}, {self.interim_component_name}, "
            f"{self.interim_out_port}, {self.interim_process_id}, [REDACTED], "
            f"{self.run_id}, [REDACTED])"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "uid": self.uid,
            "interimComponentName": self.interim_component_name,
            "interimOutPort": self.interim_out_port,
            "interimProcessId": self.interim_process_id,
            "interim": self.interim,
            "submissionTime": datetime_to_posix_ts_millis(self.submission_time),
            "runId": self.run_id,
            "runConfig": self.run_config,
        }

    @classmethod
    def from_interim_response(
        cls, runs: InterimResponse, run_configs: Dict[str, Dict[str, str]]
    ) -> "InterimResponseCamelCase":
        """Create from InterimResponse and run configurations."""
        run_config = None
        if runs.run_id:
            port_configs = run_configs.get(runs.interim_out_port, {})
            run_config = port_configs.get(runs.run_id)

        return cls(
            uid=runs.uid,
            interim_component_name=runs.interim_component_name,
            interim_out_port=runs.interim_out_port,
            interim_process_id=runs.interim_process_id,
            interim=runs.interim,
            run_id=runs.run_id,
            run_config=run_config,
        )


@dataclass
class GemProgressResponseCamelCase(ResponseCamelCase):
    """CamelCase response for gem progress."""

    uid: str
    session: str
    process_id: Optional[str] = None
    task_state: Optional[str] = None
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    stdout: Optional[List[TimestampedOutput]] = None
    stderr: Optional[List[TimestampedOutput]] = None
    exception: Optional[SerializableException] = None
    submission_time: Optional[datetime] = None

    def get_uid(self) -> str:
        """Get unique identifier."""
        return self.uid

    def __str__(self) -> str:
        """String representation with redacted sensitive data."""
        return (
            f"GemProgressResponseCamelCase({self.uid}, {self.session}, {self.process_id}, "
            f"{self.task_state}, {self.start_time}, {self.end_time}, [REDACTED], "
            f"[REDACTED], {self.exception}, {self.submission_time})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "uid": self.uid,
            "session": self.session,
            "processId": self.process_id,
            "taskState": self.task_state,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "stdout": (
                [output.to_dict() for output in self.stdout] if self.stdout else None
            ),
            "stderr": (
                [output.to_dict() for output in self.stderr] if self.stderr else None
            ),
            "exception": self.exception.to_dict() if self.exception else None,
            "submissionTime": datetime_to_posix_ts_millis(self.submission_time),
        }

    @classmethod
    def from_component_run(cls, run: ComponentRuns) -> "GemProgressResponseCamelCase":
        """Create from ComponentRuns."""
        exception = None
        if run.exception:
            exception = run.exception.to_serializable_exception()

        return cls(
            uid=run.uid,
            session="historical",
            process_id=run.process_id,
            task_state=run.state,
            start_time=run.start_time,
            end_time=run.end_time,
            stdout=run.stdout,
            stderr=run.stderr,
            exception=exception,
            submission_time=None,
        )


@dataclass
class Fabric:
    """Represents a fabric entity."""

    uid: str
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {"uid": self.uid, "name": self.name}


@dataclass
class PipelineRun:
    """Represents a pipeline run reference."""

    uid: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {"uid": self.uid}


@dataclass
class RunDates:
    """Represents run dates information."""

    uid: str
    run_id: str
    submission_time: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "uid": self.uid,
            "runId": self.run_id,
            "submissionTime": datetime_to_posix_ts_millis(self.submission_time),
        }

    @classmethod
    def from_component_runs(cls, runs: ComponentRuns) -> "RunDates":
        """Create from ComponentRuns."""
        return cls(
            uid=runs.uid,
            run_id=runs.pipeline_run_uid,
            submission_time=runs.created_at or now_utc(),
        )


@dataclass
class PipelineRunsResponseCamelCase(ResponseCamelCase):
    """CamelCase response for pipeline runs."""

    pipeline_run_id: str
    pipeline_uid: str
    submission_time: Optional[datetime]
    status: str
    run_type: str
    job_uid: Optional[str] = None
    job_name: Optional[str] = None
    fabric: Optional[Fabric] = None
    fabric_id: Optional[int] = None
    time_taken: Optional[int] = None
    rows_read: Optional[int] = None
    rows_written: Optional[int] = None
    code: Optional[Dict[str, str]] = None
    branch: Optional[str] = None
    pipeline_config: Optional[str] = None
    created_by: Optional[str] = None

    def get_uid(self) -> str:
        """Get unique identifier."""
        return self.pipeline_run_id

    def __str__(self) -> str:
        """String representation with redacted sensitive data."""
        return (
            f"PipelineRunsResponseCamelCase({self.pipeline_run_id}, {self.pipeline_uid}, "
            f"{self.job_uid}, {self.job_name}, {self.fabric}, {self.fabric_id}, "
            f"{self.submission_time}, {self.status}, {self.time_taken}, {self.rows_read}, "
            f"{self.rows_written}, {self.run_type}, [REDACTED], {self.branch}, "
            f"[REDACTED], {self.created_by})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pipelineRunId": self.pipeline_run_id,
            "pipelineUID": self.pipeline_uid,
            "jobUID": self.job_uid,
            "jobName": self.job_name,
            "fabric": self.fabric.to_dict() if self.fabric else None,
            "fabricId": self.fabric_id,
            "submissionTime": datetime_to_posix_ts_millis(self.submission_time),
            "status": self.status,
            "timeTaken": self.time_taken,
            "rowsRead": self.rows_read,
            "rowsWritten": self.rows_written,
            "runType": self.run_type,
            "code": self.code,
            "branch": self.branch,
            "pipelineConfig": self.pipeline_config,
            "createdBy": self.created_by,
        }

    @classmethod
    def from_pipeline_runs(cls, runs: PipelineRuns) -> "PipelineRunsResponseCamelCase":
        """Create from PipelineRuns."""
        return cls(
            pipeline_run_id=runs.uid,
            pipeline_uid=runs.pipeline_uri,
            job_uid=runs.job_uri,
            fabric=Fabric(uid=runs.fabric_uid),
            submission_time=runs.created_at,
            status=runs.status,
            time_taken=runs.time_taken,
            rows_read=runs.rows_read,
            rows_written=runs.rows_written,
            run_type=runs.run_type,
            branch=runs.branch,
            created_by=runs.created_by,
        )

    @classmethod
    def from_pipeline_runs_with_code(
        cls, runs: PipelineRuns
    ) -> "PipelineRunsResponseCamelCase":
        """Create from PipelineRuns with code information."""
        pipeline_config = None
        if runs.pipeline_config:
            config = Config.from_js(runs.pipeline_config)
            pipeline_config = config.pipeline_config

        return cls(
            pipeline_run_id=runs.uid,
            pipeline_uid=runs.pipeline_uri,
            job_uid=runs.job_uri,
            fabric_id=int(runs.fabric_uid) if runs.fabric_uid.isdigit() else None,
            submission_time=runs.created_at,
            status=runs.status,
            time_taken=runs.time_taken,
            rows_read=runs.rows_read,
            rows_written=runs.rows_written,
            run_type=runs.run_type,
            code=runs.workflow_code,
            branch=runs.branch,
            pipeline_config=pipeline_config,
            created_by=runs.created_by,
        )


@dataclass
class HistoricalViewCodeResponse:
    """Response for historical view code."""

    pipeline_id: str
    pipeline_run: PipelineRunsResponseCamelCase

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pipelineId": self.pipeline_id,
            "pipelineRun": self.pipeline_run.to_dict(),
        }


@dataclass
class DatasetRunsResponseCamelCase(ResponseCamelCase):
    """CamelCase response for dataset runs."""

    uid: str
    dataset_uid: str
    pipeline_uid: str
    pipeline_run: PipelineRun
    component_name: str
    component_type: str
    submission_time: Optional[datetime] = None
    dataset_name: Optional[str] = None
    pipeline_name: Optional[str] = None
    fabric: Optional[Fabric] = None
    records_processed: Optional[int] = None
    status: Optional[str] = None
    interims: Optional[str] = None
    run_dates: Optional[List[RunDates]] = None
    run_type: Optional[str] = None
    job_uid: Optional[str] = None
    job_name: Optional[str] = None
    bytes: Optional[int] = None
    partition: Optional[int] = None
    branch: Optional[str] = None

    def get_uid(self) -> str:
        """Get unique identifier."""
        return self.uid

    def __str__(self) -> str:
        """String representation with redacted sensitive data."""
        return (
            f"DatasetRunsResponseCamelCase({self.uid}, {self.dataset_uid}, {self.pipeline_uid}, "
            f"{self.pipeline_run}, {self.fabric}, {self.submission_time}, {self.component_name}, "
            f"{self.component_type}, {self.records_processed}, {self.status}, [REDACTED], "
            f"{self.run_dates}, {self.run_type}, {self.job_uid}, {self.bytes}, "
            f"{self.partition}, {self.branch})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "uid": self.uid,
            "datasetUID": self.dataset_uid,
            "datasetName": self.dataset_name,
            "pipelineUID": self.pipeline_uid,
            "pipelineName": self.pipeline_name,
            "fabric": self.fabric.to_dict() if self.fabric else None,
            "submissionTime": datetime_to_posix_ts_millis(self.submission_time),
            "pipelineRun": self.pipeline_run.to_dict(),
            "componentName": self.component_name,
            "componentType": self.component_type,
            "recordsProcessed": self.records_processed,
            "status": self.status,
            "interims": self.interims,
            "runDates": (
                [rd.to_dict() for rd in self.run_dates] if self.run_dates else None
            ),
            "runType": self.run_type,
            "jobUID": self.job_uid,
            "jobName": self.job_name,
            "bytes": self.bytes,
            "partition": self.partition,
            "branch": self.branch,
        }

    @classmethod
    def from_component_runs_with_status(
        cls, runs: ComponentRunsWithStatus
    ) -> "DatasetRunsResponseCamelCase":
        """Create from ComponentRunsWithStatus."""
        return cls(
            uid=runs.uid,
            dataset_uid=runs.component_uri,
            pipeline_uid=runs.pipeline_uri,
            pipeline_run=PipelineRun(runs.pipeline_run_uid),
            fabric=Fabric(uid=runs.fabric_uid),
            submission_time=runs.created_at,
            component_name=runs.component_name,
            component_type=runs.component_type,
            records_processed=runs.records,
            status=runs.status,
            run_type=runs.run_type,
            job_uid=runs.job_uri,
            bytes=runs.bytes,
            partition=runs.partitions,
            branch=runs.branch,
        )

    @classmethod
    def from_component_runs_with_status_and_interims(
        cls,
        runs: ComponentRunsWithStatusAndInterims,
        run_dates: Optional[List[RunDates]] = None,
    ) -> "DatasetRunsResponseCamelCase":
        """Create from ComponentRunsWithStatusAndInterims."""
        return cls(
            uid=runs.uid,
            dataset_uid=runs.component_uri,
            pipeline_uid=runs.pipeline_uri,
            pipeline_run=PipelineRun(runs.pipeline_run_uid),
            fabric=Fabric(uid=runs.fabric_uid),
            submission_time=runs.created_at,
            component_name=runs.component_name,
            component_type=runs.component_type,
            records_processed=runs.records,
            status=runs.status,
            interims=runs.interim,
            run_dates=run_dates,
            run_type=runs.run_type,
            job_uid=runs.job_uri,
            bytes=runs.bytes,
            partition=runs.partitions,
        )


@dataclass
class ComponentRunsWithRunDates:
    """Component runs with associated run dates."""

    component_runs_with_status_and_interims: Optional[
        List[ComponentRunsWithStatusAndInterims]
    ] = None
    run_dates: Optional[List[RunDates]] = None


# Exception classes
class UnavailableWorkflowJsonException(Exception):
    """Exception for unavailable workflow JSON."""

    def __init__(self, msg: str, cause: Optional[Exception] = None):
        super().__init__(msg)
        self.cause = cause


def error(msg: str, cause: Optional[Exception] = None) -> None:
    """Raise a runtime error with optional cause."""
    if cause:
        raise RuntimeError(msg) from cause
    else:
        raise RuntimeError(msg)


def check_expired_row(
    uid: str,
) -> Callable[[ExecutionMetricsEntity], ExecutionMetricsEntity]:
    """Check if a row is expired and raise error if so."""

    def check_func(row: ExecutionMetricsEntity) -> ExecutionMetricsEntity:
        if row.expired:
            error(f"Component run with uid `{uid}` has expired")
        return row

    return check_func


def on_fail(uid: str) -> None:
    """Handle failure case when component run is not found."""
    error(f"Component run with uid `{uid}` not found")


@dataclass
class FileContent:
    """Represents file content with path and content."""

    path: str
    content: str

    @property
    def is_scala(self) -> bool:
        """Check if file is a Scala file."""
        return FileContent.is_scala_file(self.path)

    @property
    def is_python(self) -> bool:
        """Check if file is a Python file."""
        return FileContent.is_python_file(self.path)

    @property
    def is_config_json(self) -> bool:
        """Check if file is a config JSON file."""
        return FileContent.is_config_file(self.path)

    @property
    def is_code_file(self) -> bool:
        """Check if file is a code file."""
        return self.is_scala or self.is_python

    @property
    def is_code_or_config(self) -> bool:
        """Check if file is code or config."""
        return self.is_code_file or self.is_config_json

    @staticmethod
    def is_scala_file(path: str) -> bool:
        """Check if path represents a Scala file."""
        return path.endswith(".scala")

    @staticmethod
    def is_python_file(path: str) -> bool:
        """Check if path represents a Python file."""
        return path.endswith(".py")

    @staticmethod
    def is_config_file(path: str) -> bool:
        """Check if path represents a config file."""
        return path.endswith(".json")

    @staticmethod
    def is_code_or_config(path: str) -> bool:
        """Check if path represents code or config file."""
        return (
            FileContent.is_scala_file(path)
            or FileContent.is_python_file(path)
            or FileContent.is_config_file(path)
        )

    @staticmethod
    def is_workflow_config(path: str) -> bool:
        """Check if path represents workflow config."""
        return (
            ".prophecy/workflow.latest.json" in path
            or ".prophecy/pipeline.json" in path
        )


# Abstract DAO interface
class ExecutionMetricsDAO(ABC):
    """Abstract base class for execution metrics data access."""

    @abstractmethod
    def get_by_id(
        self, id: str, filters: Filters, expired_runs: bool = False
    ) -> ExecutionMetricsEntity:
        """Get entity by ID with filters."""
        pass

    @abstractmethod
    def get_by_ids(
        self, uids: List[str], filters: Filters
    ) -> List[ExecutionMetricsEntity]:
        """Get entities by list of IDs with filters."""
        pass

    @abstractmethod
    def expire(self, uid: str, filters: Filters) -> DataFrame:
        """Expire an entity by UID."""
        pass

    def timestamp_from_long(self, time: Optional[int]) -> datetime:
        """Convert long timestamp to datetime."""
        return timestamp_from_long(time)


# DataFrame extension for schema evolution
class SchemaEvolvingDataFrame:
    """Extension for DataFrame with schema evolution capabilities."""

    @classmethod
    def schema_safe_as(cls, df: DataFrame, schema: StructType) -> DataFrame:
        """Convert DataFrame to match target schema safely."""
        result_df = df

        for field in schema.fields:
            if field.name not in result_df.columns:
                result_df = result_df.withColumn(
                    field.name, lit(None).cast(field.dataType)
                )

        return result_df


@dataclass
class InterimPath:
    """Represents an interim path with subgraph, component, and port."""

    subgraph: str
    component: str
    port: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "subgraph": self.subgraph,
            "component": self.component,
            "port": self.port,
        }


@dataclass
class Config:
    """Configuration container for pipeline and run configs."""

    pipeline_config: Optional[str] = None
    run_config: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {"pipelineConfig": self.pipeline_config, "runConfig": self.run_config}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Create from dictionary."""
        if "pipelineConfig" in data or "runConfig" in data:
            return cls(
                pipeline_config=data.get("pipelineConfig"),
                run_config=data.get("runConfig"),
            )
        else:
            # Handle case where data is just a string
            config_str = data if isinstance(data, str) else json.dumps(data)
            return cls(pipeline_config=config_str)

    @classmethod
    def from_js(cls, js: str) -> "Config":
        """Create from JSON string."""
        try:
            data = json.loads(js)
            return cls.from_dict(data)
        except json.JSONDecodeError:
            return cls(pipeline_config=js)
