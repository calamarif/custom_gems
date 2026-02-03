import asyncio
import json
import logging
import threading
import traceback
from types import MappingProxyType
from typing import Any, Awaitable, Callable
from uuid import uuid4

# from prophecy.utils.json_rpc_layer import *
from prophecy.executionmetrics.execution_metrics_handler import ExecutionMetricsHandler
from prophecy.jsonrpc.models import (
    DatasetRunsDetailedRequest,
    DatasetRunsRequest,
    DeleteDatasetRunRequest,
    DeletePipelineRunRequest,
    EMRequest,
    ErrorResponse,
    HistoricalGemProgressRequest,
    HistoricalViewRequest,
    InterimsRequest,
    JsonRpcError,
    JsonRpcResult,
    LoadLastPipelineRunInterimsRequest,
    PipelineRunsRequest,
    RequestMessage,
    RequestMethod,
    ResponseMessage,
    SuccessResponse,
)
from prophecy.utils.secrets import SecretCrudRequest, handle_secrets_crud


execution_metrics_handler = {}
try:
    from server_rest import SparkSessionProxy  # lazy import

    spark_proxy = SparkSessionProxy.get_instance()
    execution_metrics_handler = ExecutionMetricsHandler(spark_proxy)
except Exception as e:
    logging.info(f"Error creaating execution_metrics_handler: {e}")


_HANDLER_REGISTRY: MappingProxyType[
    type[RequestMethod], Callable[[Any], Awaitable[JsonRpcResult]]
] = MappingProxyType(
    {
        DatasetRunsRequest: execution_metrics_handler._handle_dataset_runs,
        DatasetRunsDetailedRequest: execution_metrics_handler._handle_dataset_runs_detailed,
        InterimsRequest: execution_metrics_handler.find_interim_response_for_pipeline,
        HistoricalGemProgressRequest: execution_metrics_handler.get_gem_progress_for_pipeline,
        HistoricalViewRequest: execution_metrics_handler._handle_historical_view,
        PipelineRunsRequest: execution_metrics_handler._handle_pipeline_runs,
        DeleteDatasetRunRequest: execution_metrics_handler._handle_delete_dataset_run,
        DeletePipelineRunRequest: execution_metrics_handler._handle_delete_pipeline_run,
        LoadLastPipelineRunInterimsRequest: execution_metrics_handler._handle_load_last_pipeline_run_interims,
        SecretCrudRequest: handle_secrets_crud,
        # add more: AnotherRequest: handle_another,
    }
)


# ----- 2.2  async dispatcher (runs inside a background event‑loop) ---------
async def dispatch_em_request_async(
    req_msg: RequestMessage,
) -> ResponseMessage:  # noqa: D401
    req = req_msg.method

    if isinstance(req, EMRequest):
        execution_metrics_handler.refresh_tables_with_filters(req.filters)

    handler = _HANDLER_REGISTRY.get(type(req))
    if handler is None:
        raise RuntimeError(f"No handler registered for {type(req).__name__}")
    try:
        result = await handler(req)  # type: ignore[arg-type]
        return SuccessResponse(id=req_msg.id, result=result)  # type: ignore[return-value]
    except Exception as exc:  # noqa: BLE001
        logging.info(f"Failed procesing request: {req}, error: {exc}, trace: {traceback.format_exc()}")
        err = JsonRpcError(message=str(exc), trace=traceback.format_exc().splitlines())
        return ErrorResponse(id=req_msg.id, error=err)  # type: ignore[return-value]


# ----- 2.3  background asyncio loop in daemon thread -----------------------
_EVENT_LOOP = asyncio.new_event_loop()
_thread = threading.Thread(target=_EVENT_LOOP.run_forever, daemon=True)
_thread.start()


def _schedule(coro: Awaitable[Any]):  # noqa: D401
    """Run *coro* in the background loop and return its result (blocking)."""
    return asyncio.run_coroutine_threadsafe(coro, _EVENT_LOOP).result()


###############################################################################
# 3.  WEBSOCKET‑CLIENT GLUE                                                 #
###############################################################################


def _process_request(payload_raw: str, ws) -> None:  # noqa: D401
    """Handle one frame coming from Scala, send back a response frame."""

    try:
        payload_str = (
            json.dumps(payload_raw) if isinstance(payload_raw, dict) else payload_raw
        )
        req_msg = RequestMessage.from_json(payload_str)

        resp_msg = _schedule(dispatch_em_request_async(req_msg))
        logging.info(f"Sending back success response : {resp_msg.to_json()}")
        from websocket_runner import send_message_via_ws

        send_message_via_ws(resp_msg.to_json())
    except Exception as exc:  # catch‑all: malformed frame
        logging.info(f"Error processing request {exc} -- {traceback.format_exc()}")
        err_resp = ErrorResponse(
            id=str(uuid4()),
            error=JsonRpcError.from_exception(exc),
        )
        from websocket_runner import send_message_via_ws

        send_message_via_ws(err_resp.to_json())
