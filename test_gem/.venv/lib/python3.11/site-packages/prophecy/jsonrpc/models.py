"""
JSON-RPC message definitions and utilities for execution metrics system.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
import re
import logging
from typing import Dict, List, Optional, Any, Type
from uuid import uuid4

from prophecy.executionmetrics.package import (
    HistoricalViewCodeResponse,
    ResponsesAsList,
)
from prophecy.executionmetrics.utils.external import Filters

# Constants
REDACTED = "<redacted>"

# Global registry for JSON-RPC methods
_METHOD_REGISTRY: Dict[str, Type] = {}


# ========================================= Decorators =========================================


def json_rpc_method(method_name: str):
    """
    Decorator to mark a class as a JSON-RPC method.
    Similar to Scala's @JsonRpcMethod annotation.
    """

    def decorator(cls):
        # Register the method name to class mapping
        _METHOD_REGISTRY[method_name] = cls

        # Add the method name as a class attribute
        cls._rpc_method_name = method_name

        # Add a property to get the method name
        if not hasattr(cls, "method"):

            @property
            def method(self) -> str:
                return self._rpc_method_name

            cls.method = method

        return cls

    return decorator


def get_method_class(method_name: str) -> Type:
    """Get the class associated with a JSON-RPC method name."""
    if method_name not in _METHOD_REGISTRY:
        raise ValueError(f"Unknown JSON-RPC method: {method_name}")
    return _METHOD_REGISTRY[method_name]


# def get_method_name(cls: Type) -> Optional[str]:
#     """Get the JSON-RPC method name for a class."""
#     return getattr(cls, "_rpc_method_name", None)


# ========================================= Base Classes =========================================


class JsonRpcMessage(ABC):
    """Base class for all JSON-RPC messages."""

    pass


class BaseRpcMethod(JsonRpcMessage):

    @property
    def method(self) -> str:
        """Return the JSON-RPC method name."""
        # Get method name from class attribute set by decorator
        return getattr(self.__class__, "_rpc_method_name", "")

    def to_dict(self) -> Dict[str, Any]:
        """Convert the request to a dictionary."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class RequestMethod(BaseRpcMethod):
    """Base class for all request methods."""

    pass


class NotificationMethod(BaseRpcMethod):
    """Base class for all notification methods."""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self.__class__.__name__  # Play-JSON discriminator
        return d


class JsonRpcResult(ABC):
    """Base class for all JSON-RPC results."""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # d.pop("type", None)
        d["type"] = self.__class__.__name__
        return d


@dataclass
class EMRequest(RequestMethod):
    """Base class for execution metrics requests."""

    filters: Filters

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EMRequest":
        return cls(filters=Filters.from_dict(data.get("filters")))

    # @property
    # @abstractmethod
    # def filters(self) -> "Filters":
    #     """Return the filters for this request."""
    #     pass


class EMResponse(JsonRpcResult):
    """Base class for execution metrics responses."""

    pass


class EMListResponse(JsonRpcResult):
    """Base class for execution metrics list responses."""

    pass


# ========================================= Enums =========================================


class SecretsProvider(Enum):
    """Supported secrets providers."""

    HASHICORP_VAULT = "HashiCorpVault"
    AWS_SECRETS_MANAGER = "AWSSecretsManager"
    AZURE_KEY_VAULT = "AzureKeyVault"


class CrudOperation(Enum):
    """CRUD operations for secrets."""

    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LIST = "LIST"


class DeleteStatus(Enum):
    """Delete Status."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


# ========================================= Core Data Classes =========================================


@dataclass
class JsonRpcError:
    """Represents a JSON-RPC error."""

    message: str
    trace: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"message": self.message}
        if self.trace:
            d["trace"] = self.trace
        return d

    @classmethod
    def from_exception(cls, exception: Exception) -> "JsonRpcError":
        """Create JsonRpcError from an exception."""
        import traceback

        return cls(
            message=str(exception),
            trace=traceback.format_exception(
                type(exception), exception, exception.__traceback__
            ),
        )


@dataclass
class RequestMessage(JsonRpcMessage):
    """JSON-RPC request message."""

    id: str
    method: RequestMethod

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "method": self.method.method,
            "params": self.method.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RequestMessage":
        """Create RequestMessage from dictionary."""
        method_class = get_method_class(data["method"])
        params = data.get("params", {})
        # Add type field for compatibility
        # params["_type"] = method_class.__name__
        logging.info(f"RequestMessage {data} :: {method_class} :: {params}")
        if hasattr(method_class, "from_dict"):
            method = method_class.from_dict(params)
        else:
            method = method_class(**params)
        return cls(id=data["id"], method=method)

    @staticmethod
    def from_json(raw: str) -> "RequestMessage":
        obj = json.loads(raw)
        return RequestMessage.from_dict(obj)


@dataclass
class NotificationMessage(JsonRpcMessage):
    """JSON-RPC notification message."""

    method: NotificationMethod

    # send to wire
    def to_json(self) -> str:
        return json.dumps({"method": self.method.to_dict()})


class ResponseMessage(JsonRpcMessage):
    """Base class for response messages."""

    id: str

    # @property
    # @abstractmethod
    # def id(self) -> str:
    #     """Return the response ID."""
    #     pass


@dataclass
class SuccessResponse(ResponseMessage):
    """Successful response message."""

    id: str
    result: JsonRpcResult

    def to_json(self) -> str:
        return json.dumps({"id": self.id, "result": self.result.to_dict()})


@dataclass
class ErrorResponse(ResponseMessage):
    """Error response message."""

    id: str
    error: JsonRpcError

    def to_json(self) -> str:
        return json.dumps({"id": self.id, "error": self.error.to_dict()})


# ========================================= Notifications =========================================


@json_rpc_method("keepAlive")
@dataclass
class KeepAlive(NotificationMethod):
    """Keep-alive notification."""

    timestamp: int = field(
        default_factory=lambda: int(datetime.now().timestamp() * 1000)
    )


@json_rpc_method("response/sparkEvents")
@dataclass
class SparkEventNotification(NotificationMethod):
    """Spark event notification."""

    msg: str


# ========================================= Requests =========================================


@json_rpc_method("post/codeSnapshot")
@dataclass
class InteractiveCodeSnapshotRequest(RequestMethod):
    """Request for interactive code snapshot."""

    userId: str
    pipelineUri: str
    uuid: str
    code: Dict[str, Any]  # RecursiveDirectoryContent
    fabricId: str
    branch: str
    dbSuffix: str

    def __str__(self) -> str:
        return (
            f"InteractiveCodeSnapshotRequest({self.userId}, {self.pipelineUri}, "
            f"{self.uuid}, {REDACTED}, {self.fabricId}, {self.branch}, {self.dbSuffix})"
        )


@json_rpc_method("request/historicalView")
@dataclass
class HistoricalViewRequest(EMRequest):
    """Request for historical view."""

    pipelineId: str
    pipelineRunId: str
    updatedBy: str
    filters: Filters

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HistoricalViewRequest":
        return cls(
            pipelineId=data.get("pipelineId"),
            pipelineRunId=data.get("pipelineRunId"),
            updatedBy=data.get("updatedBy"),
            filters=Filters.from_dict(data.get("filters")),
        )


@json_rpc_method("request/historicalGemProgress")
@dataclass
class HistoricalGemProgressRequest(EMRequest):
    """Request for historical gem progress."""

    pipelineRunId: str
    updatedBy: str
    filters: Filters

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HistoricalGemProgressRequest":
        return cls(
            pipelineRunId=data.get("pipelineRunId"),
            updatedBy=data.get("updatedBy"),
            filters=Filters.from_dict(data.get("filters")),
        )


@json_rpc_method("request/pipelineRuns")
@dataclass
class PipelineRunsRequest(EMRequest):
    """Request for pipeline runs."""

    pipelineUid: str
    limit: int
    filters: Filters

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineRunsRequest":
        return cls(
            pipelineUid=data.get("pipelineUid"),
            limit=data.get("limit"),
            filters=Filters.from_dict(data.get("filters")),
        )


@json_rpc_method("request/datasetRuns")
@dataclass
class DatasetRunsRequest(EMRequest):
    """Request for dataset runs."""

    datasetUid: str
    limit: int
    filters: Filters

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DatasetRunsRequest":
        return cls(
            datasetUid=data.get("datasetUID"),
            limit=data.get("limit"),
            filters=Filters.from_dict(data.get("filters")),
        )


@json_rpc_method("request/datasetRunsDetailed")
@dataclass
class DatasetRunsDetailedRequest(EMRequest):
    """Request for detailed dataset runs."""

    datasetRunId: str
    user: str
    filters: Filters

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeleteDatasetRunRequest":
        return cls(
            datasetRunId=data.get("datasetRunID"),
            user=data.get("user"),
            filters=Filters.from_dict(data.get("filters")),
        )


@json_rpc_method("delete/DatasetRun")
@dataclass
class DeleteDatasetRunRequest(EMRequest):
    """Request to delete dataset run."""

    datasetRunId: str
    filters: Filters

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeleteDatasetRunRequest":
        return cls(
            datasetRunId=data.get("datasetRunID"),
            filters=Filters.from_dict(data.get("filters")),
        )


@json_rpc_method("delete/PipelineRun")
@dataclass
class DeletePipelineRunRequest(EMRequest):
    """Request to delete pipeline run."""

    pipelineRunId: str
    filters: Filters

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeletePipelineRunRequest":
        return cls(
            pipelineRunId=data.get("pipelineRunID"),
            filters=Filters.from_dict(data.get("filters")),
        )


@json_rpc_method("request/interims")
@dataclass
class InterimsRequest(EMRequest):
    """Request for interims."""

    runId: str
    updatedBy: str
    filters: Filters

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InterimsRequest":
        return cls(
            runId=data.get("runId"),
            updatedBy=data.get("updatedBy"),
            filters=Filters.from_dict(data.get("filters")),
        )


@json_rpc_method("request/lastPipelineRunInterims")
@dataclass
class LoadLastPipelineRunInterimsRequest(EMRequest):
    """Request to load last pipeline run interims."""

    pipelineUid: str
    updatedBy: str
    filters: Filters

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LoadLastPipelineRunInterimsRequest":
        return cls(
            pipelineUid=data.get("pipelineUid"),
            updatedBy=data.get("updatedBy"),
            filters=Filters.from_dict(data.get("filters")),
        )


@json_rpc_method("request/secretsCrud")
@dataclass
class SecretCrudRequest(RequestMethod):
    """Request for secret CRUD operations."""

    session: str
    fabricId: str
    userId: str
    providerId: str
    providerType: SecretsProvider
    operation: CrudOperation
    secretScope: Optional[str] = None
    secretKey: Optional[str] = None
    secretValue: Optional[str] = None
    providerConnectionDetails: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        return (
            f"SecretCrudRequest({self.session}, {self.fabricId}, {self.userId}, "
            f"{self.providerId}, {self.providerType}, {self.operation}, "
            f"{self.secretScope}, {self.secretKey}, {REDACTED}, "
            f"{self.providerConnectionDetails})"
        )


# ========================================= Responses =========================================


# class SecretsOperationResponse(ABC):
#     """Base class for secrets operation responses."""

#     pass


# @dataclass
# class HashiCorpHealthResponse(SecretsOperationResponse):
#     """HashiCorp Vault health response."""

#     isSealed: Optional[bool]
#     isOnStandby: Optional[bool]
#     isInitialized: Optional[bool]
#     canConnect: bool
#     message: Optional[str]

#     @classmethod
#     def from_rest_response(cls, health_response: Any) -> "HashiCorpHealthResponse":
#         """Create from Vault REST API response."""
#         isSealed = health_response.get("sealed", True)
#         isInitialized = health_response.get("initialized", False)
#         canConnect = not isSealed and isInitialized

#         message = None
#         if not isInitialized:
#             message = "Vault isn't initialized. Please contact your administrator"
#         elif isSealed:
#             message = "Vault is sealed. Please contact your administrator"

#         return cls(
#             isSealed=isSealed,
#             isOnStandby=health_response.get("standby"),
#             isInitialized=isInitialized,
#             canConnect=canConnect,
#             message=message,
#         )

#     def __str__(self) -> str:
#         return (
#             f"HashiCorpHealthResponse({self.isSealed}, {self.isOnStandby}, "
#             f"{self.isInitialized}, {self.canConnect}, {REDACTED})"
#         )


# @dataclass
# class CreateResponse(SecretsOperationResponse):
#     """Response for secret creation."""

#     secretScope: str
#     secretKey: str
#     data: Optional[Dict[str, str]] = None

#     def __str__(self) -> str:
#         return f"CreateResponse({self.secretScope}, {self.secretKey}, {REDACTED})"


# @dataclass
# class DeleteResponse(SecretsOperationResponse):
#     """Response for secret deletion."""

#     secretScope: str
#     secretKey: str
#     data: Optional[Dict[str, str]] = None

#     def __str__(self) -> str:
#         return f"DeleteResponse({self.secretScope}, {self.secretKey}, {REDACTED})"


# @dataclass
# class ReadResponse(SecretsOperationResponse):
#     """Response for secret read."""

#     secretScope: Optional[str]
#     secretKey: str
#     secretValue: Optional[str]
#     data: Optional[Dict[str, str]] = None

#     def __str__(self) -> str:
#         return f"ReadResponse({self.secretScope}, {self.secretKey}, {REDACTED}, {REDACTED})"


# @dataclass
# class ListResponse(SecretsOperationResponse):
#     """Response for secret list."""

#     secretScope: Optional[str]
#     secrets: Optional[Dict[str, List[str]]] = None
#     data: Optional[Dict[str, str]] = None

#     def __str__(self) -> str:
#         return f"ListResponse({self.secretScope}, {self.secrets}, {REDACTED})"


# @dataclass
# class LSecretsResponse(JsonRpcResult):
#     """Response for secrets operations."""

#     session: str
#     fabricId: str
#     userId: str
#     providerId: str
#     operation: CrudOperation
#     response: SecretsOperationResponse
#     success: bool
#     errorMsg: Optional[str] = None
#     trace: Optional[str] = None

#     @classmethod
#     def from_request(
#         cls,
#         request: SecretCrudRequest,
#         response: SecretsOperationResponse,
#         success: bool,
#         exception: Optional[Exception] = None,
#     ) -> "LSecretsResponse":
#         """Create response from request and operation result."""
#         import traceback

#         return cls(
#             session=request.session,
#             fabricId=request.fabricId,
#             userId=request.userId,
#             providerId=request.providerId,
#             operation=request.operation,
#             response=response,
#             success=success,
#             errorMsg=str(exception) if exception else None,
#             trace=(
#                 "\n".join(
#                     traceback.format_exception(
#                         type(exception), exception, exception.__traceback__
#                     )
#                 )
#                 if exception
#                 else None
#             ),
#         )


# # Response wrapper classes
# @dataclass
# class ResponsesAsList:
#     """Generic list response wrapper."""

#     rows: List[Any]
#     limit: int
#     next_filters: Optional[Dict[str, Any]] = None
#     message: Optional[str] = None


@dataclass
class PipelineRunsResponse(EMListResponse):
    """Response containing pipeline runs."""

    response: ResponsesAsList

    def __str__(self) -> str:
        return f"PipelineRunsResponse({REDACTED})"

    def to_dict(self) -> Dict[str, Any]:
        return {"response": self.response.to_dict(), "type": self.__class__.__name__}


@dataclass
class InterimResponse(EMListResponse):
    """Response containing interims."""

    response: ResponsesAsList

    def __str__(self) -> str:
        return f"InterimResponse({REDACTED})"

    def to_dict(self) -> Dict[str, Any]:
        return {"response": self.response.to_dict(), "type": self.__class__.__name__}


@dataclass
class DatasetRunsResponse(EMListResponse):
    """Response containing dataset runs."""

    response: ResponsesAsList

    def __str__(self) -> str:
        return f"DatasetRunsResponse({REDACTED})"

    def to_dict(self) -> Dict[str, Any]:
        return {"response": self.response.to_dict(), "type": self.__class__.__name__}


@dataclass
class DatasetDetailedResponse(EMListResponse):
    """Response containing detailed dataset information."""

    response: ResponsesAsList

    def __str__(self) -> str:
        return f"DatasetDetailedResponse({REDACTED})"

    def to_dict(self) -> Dict[str, Any]:
        return {"response": self.response.to_dict(), "type": self.__class__.__name__}


@dataclass
class GemLevelProgressResponse(EMListResponse):
    """Response containing gem-level progress."""

    response: ResponsesAsList

    def __str__(self) -> str:
        return f"GemLevelProgressResponse({REDACTED})"

    def to_dict(self) -> Dict[str, Any]:
        return {"response": self.response.to_dict(), "type": self.__class__.__name__}


@dataclass
class HistoricalViewResponse(EMResponse):
    """Response containing historical view."""

    response: HistoricalViewCodeResponse

    def __str__(self) -> str:
        return f"HistoricalViewResponse({REDACTED})"

    def to_dict(self) -> Dict[str, Any]:
        return {"response": self.response.to_dict(), "type": self.__class__.__name__}


@dataclass
class DeletePipelineRunResponse(EMResponse):
    """Response for pipeline run deletion."""

    pipelineRunId: str
    status: DeleteStatus
    msg: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipelineRunId": self.pipelineRunId,
            "status": self.status,
            "msg": self.msg,
            "type": self.__class__.__name__,
        }


@dataclass
class DeleteDatasetRunResponse(EMResponse):
    """Response for dataset run deletion."""

    datasetRunId: str
    status: DeleteStatus
    msg: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "datasetRunId": self.datasetRunId,
            "status": self.status,
            "msg": self.msg,
            "type": self.__class__.__name__,
        }


# ========================================= JSON Serialization =========================================


def serialize_message(message: JsonRpcMessage) -> str:
    """Serialize a JSON-RPC message to JSON string."""
    if isinstance(message, RequestMessage):
        return json.dumps(message.to_dict())
    elif isinstance(message, (SuccessResponse, ErrorResponse)):
        data = {"id": message.id}
        if isinstance(message, SuccessResponse):
            data["result"] = {
                "type": message.result.__class__.__name__,
                **message.result.__dict__,
            }
        else:
            data["error"] = message.error.__dict__
        return json.dumps(data)
    elif isinstance(message, NotificationMessage):
        return json.dumps(
            {"method": message.method.method, "params": message.method.__dict__}
        )
    else:
        # Handle other message types
        return json.dumps(message.__dict__)


def deserialize_message(payload_raw: str) -> JsonRpcMessage:
    """Deserialize a JSON string to a JSON-RPC message."""
    try:
        payload = (
            payload_raw if isinstance(payload_raw, dict) else json.loads(payload_raw)
        )
        return RequestMessage.from_dict(payload)
    except Exception as e:
        logging.info(e)
        return ErrorResponse(id=str(uuid4()), error=JsonRpcError.from_exception(e))
