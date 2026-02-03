from abc import ABC
from dataclasses import dataclass, field
import json
from typing import Any, Dict, List, Optional


class HasProcessesConnectionsPorts(ABC):
    """Interface for objects with processes, connections and ports."""

    processes: Dict[str, "WorkflowNode"]
    connections: List["WorkflowEdge"]
    ports: "NodePorts"


@dataclass
class NodePort:
    id: str
    slug: str


@dataclass
class NodePorts:
    inputs: List[NodePort] = field(default_factory=list)
    outputs: List[NodePort] = field(default_factory=list)

    @classmethod
    def parse_node_ports(cls, data: Any) -> "NodePorts":
        if not data:
            return NodePorts()

        inputs = []
        outputs = []
        for p in data.get("inputs", []):
            inputs.append(NodePort(id=p.get("id"), slug=p.get("slug")))
        for p in data.get("outputs", []):
            outputs.append(NodePort(id=p.get("id"), slug=p.get("slug")))

        return NodePorts(inputs, outputs)


@dataclass
class WorkflowNode:
    """Workflow node representation."""

    id: str
    component: str
    metadata: Dict[str, Any]
    ports: NodePorts
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowEdge:
    """Workflow edge representation."""

    source: str
    source_port: str
    target: str
    target_port: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowEdge":
        return WorkflowEdge(
            source=data["source"],
            source_port=data["sourcePort"],
            target=data["target"],
            target_port=data["targetPort"],
        )

    @classmethod
    def from_connections_list(cls, data: Any) -> List["WorkflowEdge"]:
        connections = []
        for conn_data in data:
            connections.append(WorkflowEdge.from_dict(conn_data))
        return connections


@dataclass
class WorkflowGroup(WorkflowNode, HasProcessesConnectionsPorts):
    """Workflow group node."""

    processes: Dict[str, "WorkflowNode"] = field(default_factory=dict)
    connections: List["WorkflowEdge"] = field(default_factory=list)


@dataclass
class WorkflowGraph(HasProcessesConnectionsPorts):
    """Workflow graph representation."""

    processes: Dict[str, WorkflowNode]
    connections: List[WorkflowEdge]
    ports: NodePorts


def extract_slug_to_process_mapping(
    processes: Dict[str, WorkflowNode],
) -> Dict[str, str]:
    """Extract mapping from slug to process ID."""
    slug_to_process = {}

    def extract_from_node(node: WorkflowNode, parent_slug: str = ""):
        """Recursively extract slug mappings."""
        current_slug = node.metadata.get("slug", "")
        if parent_slug:
            current_slug = f"{parent_slug}.{current_slug}"

        slug_to_process[current_slug] = node.id

        if isinstance(node, WorkflowGroup):
            for _, child_node in node.processes.items():
                extract_from_node(child_node, current_slug)

    for _, node in processes.items():
        extract_from_node(node)

    return slug_to_process


def get_workflow_graph(code: Optional[Dict[str, str]]) -> Optional[WorkflowGraph]:
    """Extract workflow graph from code dictionary."""
    if not code:
        return None

    workflow_content = None
    for path, content in code.items():
        if path.endswith(".prophecy/workflow.latest.json"):
            workflow_content = content
            break

    if workflow_content:
        data = json.loads(workflow_content)
        return _parse_workflow_graph(data)

    return None


def _parse_workflow_nodes(data: Dict[str, Any]) -> Dict[str, "WorkflowNode"]:
    processes = {}
    for proc_id, proc_data in data.get("processes", {}).items():
        if proc_data.get("component") == "Subgraph":
            node = WorkflowGroup(
                id=proc_id,
                component=proc_data.get("component"),
                metadata=proc_data.get("metadata", {}),
                ports=NodePorts.parse_node_ports(proc_data.get("ports", {})),
                properties=proc_data.get("properties", {}),
                processes=_parse_workflow_nodes(proc_data),
                connections=WorkflowEdge.from_connections_list(
                    proc_data.get("connections", [])
                ),
            )
        else:
            node = WorkflowNode(
                id=proc_id,
                component=proc_data.get("component"),
                metadata=proc_data.get("metadata", {}),
                ports=NodePorts.parse_node_ports(proc_data.get("ports", {})),
                properties=proc_data.get("properties", {}),
            )
        processes[proc_id] = node

    return processes


def _parse_workflow_graph(data: Dict[str, Any]) -> WorkflowGraph:
    """Parse workflow graph from dictionary."""
    processes = _parse_workflow_nodes(data)

    connections = WorkflowEdge.from_connections_list(data.get("connections", []))

    return WorkflowGraph(
        processes=processes,
        connections=connections,
        ports=NodePorts.parse_node_ports(data.get("ports", {})),
    )
