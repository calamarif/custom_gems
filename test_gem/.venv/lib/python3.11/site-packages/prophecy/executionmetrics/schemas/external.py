from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union
import copy
import json

from pyspark.sql.types import StructType


@dataclass(frozen=True)
class InterimKey:
    """Key for interim storage."""

    subgraph: str
    component: str
    port: str
    runIdOpt: Optional[str] = None


# Helper functions for JSON-like behavior
def js_array_from_values(values: List[str]) -> List[str]:
    return values


def js_array_from_map(values: Dict[str, Any], schema: StructType) -> List[Any]:
    return [values.get(field.name, None) for field in schema.fields]


def map_values_to_strings(values: Dict[str, Any], schema: StructType) -> List[str]:
    result = []
    for field in schema.fields:
        value = values.get(field.name)
        if isinstance(value, str):
            result.append(value)
        elif value is not None:
            result.append(str(value))
        else:
            result.append("null")
    return result


def writes_to_strings(values: List[Any]) -> List[str]:
    return [value if isinstance(value, str) else str(value) for value in values]


@dataclass
class LInterimContent:
    """Interim content representation."""

    subgraph: str
    component: str
    port: str
    interimRows: List[Dict[str, Any]]
    schema: StructType
    runId: Optional[str] = None
    processId: Optional[str] = None
    numRecords: Optional[int] = None
    bytesProcessed: Optional[int] = None
    numPartitions: Optional[int] = None
    runConfig: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LInterimContent":
        return cls(
            subgraph=data["subgraph"],
            component=data["component"],
            port=data["port"],
            interimRows=data["data"],
            schema=StructType.fromJson(
                json.loads(data["schema"])
                if isinstance(data["schema"], str)
                else data["schema"]
            ),
            processId=data["processId"] if "processId" in data else None,
            numRecords=data["numRecords"] if "numRecords" in data else None,
            bytesProcessed=(
                data["bytesProcessed"] if "bytesProcessed" in data else None
            ),
            numPartitions=data["numPartitions"] if "numPartitions" in data else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        interims_data = [
            writes_to_strings(js_array_from_map(x, self.schema))
            for x in self.interimRows
        ]
        result = {
            "component": self.component,
            "port": self.port,
            "subgraph": self.subgraph,
            "schema": json.loads(self.schema.json()),
            "data": interims_data,
        }
        optional_fields = [
            ("numRecords", self.numRecords),
            ("numPartitions", self.numPartitions),
            ("processId", self.processId),
            ("bytesProcessed", self.bytesProcessed),
            ("runId", self.runId),
            ("runConfig", self.runConfig),
        ]
        for key, value in optional_fields:
            if value is not None:
                result[key] = value
        return result

    def update(self, right: "LInterimContent") -> "LInterimContent":
        obj = copy.deepcopy(self)
        obj.numRecords = (obj.numRecords or 0) + (right.numRecords or 0)
        obj.bytesProcessed = (obj.bytesProcessed or 0) + (right.bytesProcessed or 0)
        obj.numPartitions = (obj.numPartitions or 0) + (right.numPartitions or 0)
        return obj


class LInterimContentOrdering:
    """Ordering for LInterimContent based on num_records."""

    @staticmethod
    def compare(x: LInterimContent, y: LInterimContent) -> int:
        """Compare two interim contents by number of records."""
        x_records = x.numRecords or 0
        y_records = y.numRecords or 0
        return x_records - y_records

    @classmethod
    def sort(cls, interims: List[LInterimContent]) -> List[LInterimContent]:
        """Sort interims by number of records."""
        return sorted(interims, key=lambda x: x.numRecords or 0)


@dataclass
class ComponentRunIdAndInterims:
    """Component run ID with associated interims."""

    uid: str
    run_id: Optional[str]
    interims: str


@dataclass
class MetricsTableNames:
    """Names for metrics tables."""

    pipeline_metrics: Optional[str] = None
    component_metrics: Optional[str] = None
    interims: Optional[str] = None

    def is_empty(self) -> bool:
        """Check if all table names are empty."""
        return not any([self.pipeline_metrics, self.component_metrics, self.interims])

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetricsTableNames":
        return cls(
            pipeline_metrics=data.get("pipelineMetrics"),
            component_metrics=data.get("componentMetrics"),
            interims=data.get("interims"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipelineMetrics": self.pipeline_metrics,
            "componentMetrics": self.component_metrics,
            "interims": self.interims,
        }


@dataclass
class MetricsWriteDetails:
    """Names for metrics tables."""

    names: MetricsTableNames
    storage_format: Any
    is_partitioning_disabled: bool


class DatasetType:
    """Dataset type constants."""

    SOURCE = "Source"
    LOOKUP = "Lookup"
    TARGET = "Target"

    @classmethod
    def to_list_as_string(cls) -> str:
        """Get SQL-ready list of types."""
        return f"'{cls.SOURCE}', '{cls.LOOKUP}', '{cls.TARGET}'"
