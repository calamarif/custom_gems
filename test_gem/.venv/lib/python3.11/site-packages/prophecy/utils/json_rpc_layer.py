from __future__ import annotations

from prophecy.executionmetrics.utils.external import Filters

"""json_rpc_model.py – complete, single‑file bridge
===================================================

*   **Domain model** mirrors the Scala Json‑RPC hierarchy (sealed traits,
    decorators, request/response envelopes).
*   **Async processing**: every handler is `async`.  A daemon thread runs an
    `asyncio` loop so the `websocket‑client` callback thread never blocks.
*   **Transport**: uses `websocket-client` (≥ 1.5) to connect to the Scala
    reverse WebSocket, parse incoming `RequestMethod` frames, dispatch, and
    push `ResponseMessage` frames.

Run:
```bash
pip install websocket-client==1.*
python json_rpc_model.py ws://scala-host:8765/sandbox-reverse
```
Replace the stub `handle_*` coroutines with real I/O‑bound logic.
"""
###############################################################################
# 0.  Imports & stdlib                                                       #
###############################################################################
import asyncio
import json
import sys
import threading
import traceback
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type
from uuid import uuid4


###############################################################################
# 1.  DOMAIN MODEL (requests, results, envelopes)                            #
###############################################################################
# ---------------------------------------------------------------------------
# 1.1  "Sealed" mix‑in (best‑effort replica of Scala `sealed trait`)         #
# ---------------------------------------------------------------------------
class _Sealed(ABC):
    _sealed_module = __name__

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # if cls.__module__ != _Sealed._sealed_module:
        #     raise TypeError(
        #         f"{cls.__name__} may not be subclassed outside {_Sealed._sealed_module!r}"
        #     )


# ---------------------------------------------------------------------------
# 1.2  REQUEST SIDE                                                          #
# ---------------------------------------------------------------------------
_method_registry: Dict[str, Type["RequestMethod"]] = {}


def json_rpc_method(
    name: str,
) -> Callable[[Type["RequestMethod"]], Type["RequestMethod"]]:
    """Decorator equivalent to Scala `@JsonRpcMethod`."""

    def decorator(cls: Type["RequestMethod"]) -> Type["RequestMethod"]:
        cls._json_rpc_method = name  # type: ignore[attr-defined]
        _method_registry[name] = cls
        return cls

    return decorator


class RequestMethod(_Sealed, ABC):
    """Common parent for all request‑payload dataclasses."""

    @property
    def method(self) -> str:  # noqa: D401
        try:
            return self.__class__._json_rpc_method  # type: ignore[attr-defined]
        except AttributeError as exc:
            raise AttributeError(
                f"{self.__class__.__name__} missing @json_rpc_method decorator"
            ) from exc


# ----- EMRequest base -------------------------------------------------------
class EMRequest(RequestMethod, ABC):
    @property
    @abstractmethod
    def filters(self) -> Filters: ...


# ----- concrete request(s) --------------------------------------------------
@json_rpc_method("request/datasetRuns")
@dataclass  # (slots=True)
class DatasetRunsRequest(EMRequest):
    datasetUID: str
    limit: int
    filters: Filters


@json_rpc_method("request/pipelineRuns")
@dataclass  # (slots=True)
class PipelineRunsRequest(EMRequest):
    pipelineUid: str
    limit: int
    filters: Filters


# ----- Request envelope -----------------------------------------------------
@dataclass  # (slots=True)
class RequestMessage(_Sealed):
    id: str
    method: RequestMethod

    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "method": self.method.method,
                "params": asdict(self.method),
            }
        )

    @staticmethod
    def from_json(raw: str) -> "RequestMessage":
        obj = json.loads(raw)
        mcls = _method_registry.get(obj["method"])
        if mcls is None:
            raise ValueError(f"Unknown RPC method {obj['method']!r}")
        payload = mcls(**obj.get("params", {}))  # type: ignore[arg-type]
        return RequestMessage(id=obj["id"], method=payload)


# ---------------------------------------------------------------------------
# 1.3  RESULT / RESPONSE SIDE                                                #
# ---------------------------------------------------------------------------
_result_registry: Dict[str, Type["JsonRpcResult"]] = {}


def json_result_type(
    name: str,
) -> Callable[[Type["JsonRpcResult"]], Type["JsonRpcResult"]]:
    """Decorator adding a `type` discriminator and registering the class."""

    def decorator(cls: Type["JsonRpcResult"]) -> Type["JsonRpcResult"]:
        cls._result_type = name  # type: ignore[attr-defined]
        _result_registry[name] = cls
        return cls

    return decorator


class JsonRpcResult(_Sealed, ABC):
    _result_type: str = "<unknown>"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self._result_type
        return d

    @staticmethod
    def from_dict(raw: Dict[str, Any]) -> "JsonRpcResult":
        rtype = raw.get("type")
        cls = _result_registry.get(rtype)
        if cls is None:
            raise ValueError(f"Unknown JsonRpcResult type {rtype!r}")
        data = {k: v for k, v in raw.items() if k != "type"}
        return cls(**data)  # type: ignore[arg-type]


class EMResponse(JsonRpcResult, ABC): ...


class EMListResponse(JsonRpcResult, ABC): ...


# ----- concrete results -----------------------------------------------------
@json_result_type("HistoricalViewResponse")
@dataclass  # (slots=True)
class HistoricalViewResponse(EMResponse):
    response: Dict[str, Any]

    def __repr__(self):
        return "HistoricalViewResponse(<redacted>)"


@json_result_type("DatasetRunsResponse")
@dataclass  # (slots=True)
class DatasetRunsResponse(EMListResponse):
    response: Dict[str, Any]

    def __repr__(self):  # noqa: D401
        return "DatasetRunsResponse(<redacted>)"


# ----- error object ---------------------------------------------------------
@dataclass  # (slots=True)
class JsonRpcError:
    message: str
    trace: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"message": self.message}
        if self.trace:
            d["trace"] = self.trace
        return d

    @staticmethod
    def from_dict(raw: Dict[str, Any]) -> "JsonRpcError":
        return JsonRpcError(message=raw["message"], trace=raw.get("trace"))


# ----- Response envelope ----------------------------------------------------
class ResponseMessage(_Sealed, ABC):
    id: str

    @staticmethod
    def from_json(raw: str) -> "ResponseMessage":
        obj = json.loads(raw)
        if "result" in obj and "error" not in obj:
            return ResponseMessage.Success(
                id=obj["id"], result=JsonRpcResult.from_dict(obj["result"])
            )
        if "error" in obj and "result" not in obj:
            return ResponseMessage.Error(
                id=obj["id"], error=JsonRpcError.from_dict(obj["error"])
            )
        raise ValueError("Invalid ResponseMessage JSON: must contain result XOR error")

    # -- subclasses ---------------------------------------------------------
    @dataclass  # (slots=True)
    class Success(_Sealed):
        id: str
        result: JsonRpcResult

        def to_json(self) -> str:
            return json.dumps({"id": self.id, "result": self.result.to_dict()})

    @dataclass  # (slots=True)
    class Error(_Sealed):
        id: str
        error: JsonRpcError

        def to_json(self) -> str:
            return json.dumps({"id": self.id, "error": self.error.to_dict()})


# ---------------------------------------------------------------------------
# 1.X  NOTIFICATION SIDE  (mirrors Scala `NotificationMethod`)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Notification subsystem (drop this into json_rpc_model.py)
# ---------------------------------------------------------------------------
_notification_registry: Dict[str, Type["NotificationMethod"]] = {}


# decorator --------------------------------------------------------------
def json_notification_method(rpc_name: str):
    """Register a *notification* payload class and stamp metadata on it."""

    def decorator(cls: Type["NotificationMethod"]) -> Type["NotificationMethod"]:
        cls._json_notification_method = rpc_name  # wire-level method
        cls._notif_type = cls.__name__  # discriminator value
        _notification_registry[cls._notif_type] = cls  # register for parsing
        return cls

    return decorator


# base class -------------------------------------------------------------
class NotificationMethod(_Sealed, ABC):
    _notif_type: str = "<unknown>"

    @property
    def method(self) -> str:  # scala lazy-val “method”
        return self.__class__._json_notification_method  # type: ignore[attr-defined]

    # ── (de)serialisation helpers ───────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self._notif_type  # Play-JSON discriminator
        return d

    @staticmethod
    def from_dict(raw: Dict[str, Any]) -> "NotificationMethod":
        ntype = raw.get("type")
        if ntype is None:
            raise ValueError("NotificationMethod JSON lacks 'type'")
        cls = _notification_registry.get(ntype)
        if cls is None:
            raise ValueError(f"Unknown NotificationMethod type: {ntype!r}")
        return cls(**{k: v for k, v in raw.items() if k != "type"})  # type: ignore[arg-type]


# concrete notification --------------------------------------------------
@json_notification_method("response/sparkEvents")
@dataclass  # (slots=True)
class SparkEventNotification(NotificationMethod):
    msg: str


# envelope ---------------------------------------------------------------
@dataclass  # (slots=True)
class NotificationMessage(_Sealed):
    method: NotificationMethod

    # send to wire
    def to_json(self) -> str:
        return json.dumps({"method": self.method.to_dict()})

    # parse from wire
    @staticmethod
    def from_json(raw: str) -> "NotificationMessage":
        obj = json.loads(raw)
        return NotificationMessage(method=NotificationMethod.from_dict(obj["method"]))


###############################################################################
# 2.  ASYNC PROCESSING                                                       #
###############################################################################
# ──────────────────────────────────────────────────────────────────────────
# 1.  Helper: refresh tables (stub – replace with real implementation)
# ──────────────────────────────────────────────────────────────────────────
async def refresh_tables(filters: "Filters") -> None:
    """
    Mirrors the Scala `refreshTables(request.filters)`.
    Non-blocking stub; swap in real logic that refreshes Δ tables or cache.
    """
    await asyncio.sleep(0)  # yield to the event-loop


# ----- 2.1  async handlers --------------------------------------------------
async def handle_dataset_runs(req: DatasetRunsRequest) -> DatasetRunsResponse:
    """Example async handler – replace with real I/O‑bound logic."""

    await asyncio.sleep(0.05)  # simulate I/O latency
    fake_rows = [{"runId": f"run-{i}", "state": "SUCCESS"} for i in range(req.limit)]
    return DatasetRunsResponse(response={"items": fake_rows})
