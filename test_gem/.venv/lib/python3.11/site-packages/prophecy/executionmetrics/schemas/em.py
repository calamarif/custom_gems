from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from prophecy.executionmetrics.utils.common import now_millis
from prophecy.executionmetrics.utils.external import (
    add_project_id_to_prophecy_uri,
    parse_repository_path,
    parse_uri,
)


@dataclass(frozen=True)
class TimestampedOutput:
    """Represents output with timestamp."""

    content: str
    time: int

    @classmethod
    def from_content(cls, content: str) -> "TimestampedOutput":
        """Create a new timestamped output with current time."""
        return cls(content=content, time=now_millis())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {"content": self.content, "time": self.time}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimestampedOutput":
        """Create from dictionary representation."""
        return cls(content=data.get("content", ""), time=data.get("time", 0))


@dataclass
class StoredGemEdge:
    """Represents a stored gem edge with connection information."""

    gem_name: Optional[str] = None
    from_port: Optional[str] = None
    to_port: Optional[str] = None
    num_rows: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "gem_name": self.gem_name,
            "from_port": self.from_port,
            "to_port": self.to_port,
            "num_rows": self.num_rows,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoredGemEdge":
        """Create from dictionary."""
        return cls(
            gem_name=data.get("gem_name"),
            from_port=data.get("from_port"),
            to_port=data.get("to_port"),
            num_rows=data.get("num_rows"),
        )


@dataclass(frozen=True)
class GemEdge:
    """Represents an edge in the gem graph."""

    gem_name: Optional[str] = None
    from_port: Optional[str] = None
    to_port: Optional[str] = None
    num_rows: Optional[int] = None

    def to_stored_gem_edge(self) -> "StoredGemEdge":
        """Convert to stored gem edge format."""
        return StoredGemEdge(
            gem_name=self.gem_name,
            from_port=self.from_port,
            to_port=self.to_port,
            num_rows=self.num_rows,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "gemName": self.gem_name,
            "fromPort": self.from_port,
            "toPort": self.to_port,
            "numRows": self.num_rows,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GemEdge":
        """Create from dictionary representation."""
        return cls(
            gem_name=data.get("gemName"),
            from_port=data.get("fromPort"),
            to_port=data.get("toPort"),
            num_rows=data.get("numRows"),
        )


@dataclass(frozen=True)
class GemProgress:
    """Tracks progress of a gem execution."""

    gem_name: str
    process_id: str
    gem_type: str
    input_gems: List[GemEdge] = field(default_factory=list)
    output_gems: List[GemEdge] = field(default_factory=list)
    in_ports: List[str] = field(default_factory=list)
    out_ports: List[str] = field(default_factory=list)
    num_rows_output: Optional[int] = None
    stdout: Optional[List[TimestampedOutput]] = None
    stderr: Optional[List[TimestampedOutput]] = None
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    state: Optional[str] = None
    exception: Optional["SerializableException"] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "gemName": self.gem_name,
            "processId": self.process_id,
            "gemType": self.gem_type,
            "inputGems": [g.to_dict() for g in self.input_gems],
            "outputGems": [g.to_dict() for g in self.output_gems],
            "inPorts": self.in_ports,
            "outPorts": self.out_ports,
            "numRowsOutput": self.num_rows_output,
            "stdout": [s.to_dict() for s in self.stdout] if self.stdout else None,
            "stderr": [s.to_dict() for s in self.stderr] if self.stderr else None,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "state": self.state,
            "exception": self.exception.to_dict() if self.exception else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GemProgress":
        """Create from dictionary representation."""
        return cls(
            gem_name=data["gemName"],
            process_id=data["processId"],
            gem_type=data["gemType"],
            input_gems=[GemEdge.from_dict(g) for g in data.get("inputGems", [])],
            output_gems=[GemEdge.from_dict(g) for g in data.get("outputGems", [])],
            in_ports=data.get("inPorts", []),
            out_ports=data.get("outPorts", []),
            num_rows_output=data.get("numRowsOutput"),
            stdout=(
                [TimestampedOutput.from_dict(s) for s in data["stdout"]]
                if data.get("stdout")
                else None
            ),
            stderr=(
                [TimestampedOutput.from_dict(s) for s in data["stderr"]]
                if data.get("stderr")
                else None
            ),
            start_time=data.get("startTime"),
            end_time=data.get("endTime"),
            state=data.get("state"),
            exception=(
                SerializableException.from_dict(data["exception"])
                if data.get("exception")
                else None
            ),
        )

    def update_progress(
        self,
        start_time: int,
        end_time: Optional[int],
        stdout: Optional[List[TimestampedOutput]],
        stderr: Optional[List[TimestampedOutput]],
        state: str,
        exception: Optional["SerializableException"],
    ):
        data = self.to_dict()
        data.update(
            {
                "startTime": start_time,
                "endTime": end_time,
                "stdout": [s.to_dict() for s in stdout] if stdout else None,
                "stderr": [s.to_dict() for s in stderr] if stderr else None,
                "state": state,
                "exception": exception.to_dict() if exception else None,
            }
        )
        return GemProgress.from_dict(data)


@dataclass(frozen=True)
class ComponentDetails:
    """Component details for execution tracking."""

    component_uri: str
    component_type: str
    process_id: str
    component_name: str
    interim_process_id: str
    interim_component_name: str
    interim_subgraph_name: str
    interim_out_port_id: str
    gem_progress: Optional[GemProgress] = None

    def add_project_id_to_component_uri(
        self, project_id_opt: Optional[str]
    ) -> "ComponentDetails":
        """Add project ID to component URI."""
        updated_uri = add_project_id_to_prophecy_uri(self.component_uri, project_id_opt)

        return ComponentDetails(
            component_uri=updated_uri,
            component_type=self.component_type,
            process_id=self.process_id,
            component_name=self.component_name,
            interim_process_id=self.interim_process_id,
            interim_component_name=self.interim_component_name,
            interim_subgraph_name=self.interim_subgraph_name,
            interim_out_port_id=self.interim_out_port_id,
            gem_progress=self.gem_progress,
        )


@dataclass(frozen=True)
class SerializableException:
    """Serializable exception representation."""

    exception_type: str
    msg: str
    cause_msg: str
    stack_trace: str
    time: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exceptionType": self.exception_type,
            "msg": self.msg,
            "causeMsg": self.cause_msg,
            "stackTrace": self.stack_trace,
            "time": self.time,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SerializableException":
        return cls(
            exception_type=data["exceptionType"],
            msg=data["msg"],
            cause_msg=data["causeMsg"],
            stack_trace=data["stackTrace"],
            time=data["time"],
        )

    def to_stored_serializable_exception(self) -> "StoredSerializableException":
        """Convert to stored version."""
        return StoredSerializableException(
            exception_type=self.exception_type,
            message=self.msg,
            cause_message=self.cause_msg,
            stack_trace=self.stack_trace,
            time=self.time,
        )

    @classmethod
    def from_exception(cls, exc: Exception):
        import traceback

        exceptionType = exc.__class__.__name__
        msg = str(exc) if exc.args else ""
        cause = exc.__cause__ or getattr(exc, "__context__", None)
        causeMsg = str(cause) if cause else ""
        stackTrace = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        current_time = now_millis()
        return cls(exceptionType, msg, causeMsg, stackTrace, current_time)


@dataclass
class StoredSerializableException:
    """Stored version of serializable exception."""

    exception_type: str
    message: str
    cause_message: str
    stack_trace: str
    time: int

    def to_serializable_exception(self) -> SerializableException:
        """Convert to regular serializable exception."""
        return SerializableException(
            exception_type=self.exception_type,
            msg=self.message,
            cause_msg=self.cause_message,
            stack_trace=self.stack_trace,
            time=self.time,
        )
