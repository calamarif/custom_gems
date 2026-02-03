import base64 as base64_std
import gzip
import json
import logging
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from typing import Optional, List

from prophecy.executionmetrics.schemas.em import (
    SerializableException,
    TimestampedOutput,
)
from prophecy.executionmetrics.utils.common import get_spark_property
from prophecy.jsonrpc.models import NotificationMessage, SparkEventNotification


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.hasHandlers():
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(handler)


# --- constants --------------------------------------------------------------

SPARK_CONF_PIPELINE_CODE_KEY = "spark.prophecy.metadata.pipeline.code"
RecursiveDirectoryContent = Dict[str, str]  # ⇐ Scala type alias


# --- tiny utility helpers ---------------------------------------------------


def get_session_appended_key(key: str, session: str) -> str:
    """Prophecy convention:  foo.bar.<session-id>"""
    return f"{key}.{session}"


def decompress(encoded: str) -> str:
    """
    Placeholder implementation: assumes each part is
    base64-encoded + gzipped bytes of UTF-8 JSON text.
    """
    raw: bytes = base64_std.b64decode(encoded)
    return gzip.decompress(raw).decode("utf-8")


def parse_json_fallback(raw: str) -> Dict[str, str]:
    """
    Second-chance JSON parser.  You can plug in ujson, rapidjson,
    or any schema-aware parser here.
    """
    return json.loads(raw)


# --- main translation -------------------------------------------------------


def get_session_hack(spark) -> str:
    for key in spark.conf._conf_override:
        assert isinstance(key, str)
        if key.startswith("spark.prophecy.metadata.pipeline.uuid"):
            return key.replace("spark.prophecy.metadata.pipeline.uuid.", "")


def get_running_code(spark, session: str) -> RecursiveDirectoryContent:
    """
    Re-assembles (and un-compresses) the pipeline code that Prophecy stores in
    Spark conf, handling both the single-value and the multi-part layout.
    """
    # 1️⃣  Multi-part branch ---------------------------------------------------

    logger.info(f"Got session: {session}")

    logger.info(f"Got spark_type: {type(spark)}")
    logger.info(f"Got spark.conf type: {type(spark.conf)}")

    session = get_session_hack(spark)

    logger.info(f"Our personal session id: {session}")

    parts_key = (
        f"{get_session_appended_key(SPARK_CONF_PIPELINE_CODE_KEY, session)}_parts"
    )
    logger.info(f"Got parts_key: {parts_key}")

    parts = get_spark_property(parts_key, spark)
    logger.info(f"Got parts: {parts}")

    if parts is not None:  # ⇐ Some(parts) in Scala
        logger.info("Got code split in %s parts", parts)

        # Gather every chunk into an in-memory list
        compressed_chunks: list[str] = []
        for part_id in range(int(parts)):
            part_key = f"{get_session_appended_key(SPARK_CONF_PIPELINE_CODE_KEY, session)}_{part_id}"
            chunk = get_spark_property(part_key, spark)
            if chunk is not None:  # ⇐ .map(...)
                compressed_chunks.append(chunk)

        decompressed_code = decompress("".join(compressed_chunks))

        # Parse JSON with two layers of defence (matches Try/Fallback logic)
        try:
            rdc: RecursiveDirectoryContent = json.loads(decompressed_code)
        except Exception as exc1:
            logger.error(
                "Failed to parse JSON with stdlib json; trying fallback", exc_info=exc1
            )
            try:
                rdc = parse_json_fallback(decompressed_code)
            except Exception as exc2:
                logger.error("Fallback JSON parser failed as well", exc_info=exc2)
                rdc = {}

        logger.info("Final code size = %d bytes", len(str(rdc).encode()))
        return rdc

    # 2️⃣  Single-value branch -------------------------------------------------
    single_key = get_session_appended_key(SPARK_CONF_PIPELINE_CODE_KEY, session)
    compressed_value = get_spark_property(single_key, spark)

    if compressed_value:
        return json.loads(decompress(compressed_value))

    # No code stored for this session
    return {}


def get_process_from_gem2(spark, gemName: str, userSession: str) -> str:
    rdc = get_running_code(spark, userSession)
    logger.info(f"RDC Keys - {rdc.keys()}")

    def find_process_id_by_slug(rdc, slug):
        wflow_file_json = rdc[".prophecy/workflow.latest.json"]
        wflow_file_json = json.loads(wflow_file_json)

        def search_processes(processes):
            for proc_id, proc_val in processes.items():
                if proc_val.get("metadata", {}).get("slug") == slug:
                    return proc_id
                # Recursively search nested processes
                nested = proc_val.get("processes")
                if isinstance(nested, dict):
                    found = search_processes(nested)
                    if found:
                        return found
            return None

        processes = wflow_file_json.get("processes", {})
        return search_processes(processes)

    return find_process_id_by_slug(rdc, gemName)


@dataclass
class ProphecyGemProgressEvent:
    session: str
    processId: Optional[str]
    taskState: str
    startTime: int
    endTime: Optional[int] = None
    stdout: Optional[List["TimestampedOutput"]] = None
    stderr: Optional[List["TimestampedOutput"]] = None
    exception: Optional["SerializableException"] = None
    # gemProgressEventJsonField: str = field(init=False, default="ProphecyGemProgressEvent")

    def to_dict(self):
        # Convert nested objects to dicts if needed
        def serialize_list(lst):
            if lst is None:
                return None
            return [
                item.to_dict() if hasattr(item, "to_dict") else item for item in lst
            ]

        return {
            "session": self.session,
            "processId": self.processId,
            "taskState": self.taskState,
            "startTime": self.startTime,
            "endTime": self.endTime,
            "stdout": serialize_list(self.stdout),
            "stderr": serialize_list(self.stderr),
            "exception": (
                self.exception.to_dict()
                if self.exception and hasattr(self.exception, "to_dict")
                else None
            ),
        }

    def to_json(self):
        return json.dumps(
            {
                "Event": "ProphecyGemProgressEvent",
                "ProphecyGemProgressEvent": self.to_dict(),
            }
        )


# gemProgressEventJsonField: str = field(init=False, default="ProphecyGemProgressEvent")


@dataclass
class ProphecyPipelineProgressEvent:
    session: str
    pipelineId: str
    state: str
    submissionTime: Optional[int]
    startTime: int
    endTime: Optional[int] = None
    exception: Optional[SerializableException] = None
    # pipelineProgressEventJsonField: str = field(init=False, default="ProphecyPipelineProgressEvent")

    # ── public API ─────────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "session": self.session,
            "pipelineId": self.pipelineId,
            "state": self.state,
            "submissionTime": self.submissionTime,
            "startTime": self.startTime,
            "endTime": self.endTime,
            "exception": (
                self.exception.to_dict()
                if self.exception and hasattr(self.exception, "to_dict")
                else None
            ),
        }

    def to_json(self) -> str:
        wrapper = {
            "Event": "ProphecyPipelineProgressEvent",
            "ProphecyPipelineProgressEvent": self.to_dict(),
        }
        return json.dumps(wrapper)


def sendGemProgressEvent3(
    spark,
    userSession,
    process_id,
    state,
    startTime,
    endTime,
    stdout,
    stderr,
    exception_type,
    msg,
    cause_msg,
    stack_trace,
):

    import time as time_module

    current_time = int(time_module.time() * 1000)
    serializableException = SerializableException(
        exception_type, msg, cause_msg, stack_trace, current_time
    )
    sendGemProgressEvent2(
        spark,
        userSession,
        process_id,
        state,
        startTime,
        endTime,
        stdout,
        stderr,
        serializableException,
    )


def sendGemProgressEvent2(
    spark, userSession, process_id, state, startTime, endTime, stdout, stderr, exception
):
    endTime = int(endTime) if endTime else None
    startTime = int(startTime) if startTime else None

    def parse_output(output):
        import json

        if output is None:
            return None
        try:
            # Try to parse as JSON list of dicts
            parsed = json.loads(output)
            if isinstance(parsed, list):
                return [TimestampedOutput.from_dict(item).to_dict() for item in parsed]
            elif isinstance(parsed, dict):
                # Single dict
                return [TimestampedOutput.from_dict(parsed).to_dict()]
            else:
                # Fallback: treat as string
                return [TimestampedOutput.from_content(str(output)).to_dict()]
        except Exception:
            # Not JSON, treat as plain string
            return [TimestampedOutput.from_content(str(output)).to_dict()]

    _stdout = parse_output(stdout)
    _stderr = parse_output(stderr)

    serializable_exception = None
    if exception is not None:
        if isinstance(exception, SerializableException):
            serializable_exception = exception
        else:
            serializable_exception = SerializableException.from_exception(exception)

    gem_event = ProphecyGemProgressEvent(
        session=get_session_hack(spark),
        processId=process_id,
        taskState=state,
        startTime=startTime,
        endTime=endTime,
        stdout=_stdout,
        stderr=_stderr,
        exception=serializable_exception,
    )

    send_ws_message(gem_event.to_json())


# ---------------------- PipelineProgressEvent ------------------------------------
#
#
# ---------------------------------------------------------------------------------


def sendPipelineProgressEvent3(
    spark,
    userSession: str,
    pipelineId: str,
    state: str,
    startTime: str,
    endTime: str,
    exception_type,
    msg,
    cause_msg,
    stack_trace,
):
    import time as time_module

    current_time = int(time_module.time() * 1000)
    serializableException = SerializableException(
        exception_type, msg, cause_msg, stack_trace, current_time
    )
    sendPipelineProgressEvent2(
        spark, userSession, pipelineId, state, startTime, endTime, serializableException
    )


def sendPipelineProgressEvent2(
    spark,
    userSession: str,
    pipelineId: str,
    state: str,
    startTime: str,
    endTime: str = "",
    exception: Optional[Any] = None,
):

    submission_time = spark.conf.get(
        f"spark.prophecy.pipeline.submission-time.{userSession}"
    )

    submission_time_int = int(submission_time) if submission_time else None

    endTime = int(endTime) if endTime else None
    startTime = int(startTime) if startTime else None

    pipeline_progress_event = ProphecyPipelineProgressEvent(
        session=userSession,
        pipelineId=pipelineId,
        state=state,
        submissionTime=submission_time_int,
        startTime=startTime,
        endTime=endTime,
        exception=exception,
    )

    send_ws_message(pipeline_progress_event.to_json())


def send_ws_message(json_msg: str):
    try:
        from websocket_runner import send_message_via_ws

        final_notification = NotificationMessage(SparkEventNotification(json_msg))
        final_message = final_notification.to_json()
        logger.info(f"SENDING pipeline_monitoring_ws_message: {final_message}")
        send_message_via_ws(final_message)
    except Exception as e:
        logger.info(f"Exception while SENDING pipeline_monitoring_ws_message: {e}")
