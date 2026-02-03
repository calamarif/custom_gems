# ----------------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------------
UID = "uid"
PIPELINE_URI = "pipeline_uri"
JOB_URI = "job_uri"
JOB_RUN_UID = "job_run_uid"
TASK_RUN_UID = "task_run_uid"
STATUS = "status"
FABRIC_UID = "fabric_uid"
TIME_TAKEN = "time_taken"
ROWS_READ = "rows_read"
ROWS_WRITTEN = "rows_written"
CREATED_AT = "created_at"
CREATED_BY = "created_by"
RUN_TYPE_COLUMN = "run_type"
INPUT_DATASETS = "input_datasets"
OUTPUT_DATASETS = "output_datasets"
WORKFLOW_CODE = "workflow_code"
PIPELINE_CONFIG = "pipeline_config"
USER_CONFIG = "user_config"
EXPECTED_INTERIMS = "expected_interims"
ACTUAL_INTERIMS = "actual_interims"
LOGS = "logs"
COMPONENT_URI = "component_uri"
PIPELINE_RUN_UID = "pipeline_run_uid"
COMPONENT_NAME = "component_name"
INTERIM_COMPONENT_NAME = "interim_component_name"
RECORDS = "records"
BYTES = "bytes"
PARTITIONS = "partitions"
COMPONENT_TYPE = "component_type"
INTERIM_OUT_PORT = "interim_out_port"
INTERIM_SUBGRAPH_NAME = "interim_subgraph_name"
INTERIM_PROCESS_ID = "interim_process_id"
INTERIM = "interim"
RUN_ID = "run_id"
EXPIRED = "expired"
BRANCH = "branch"
GEM_NAME = "gem_name"
PROCESS_ID = "process_id"
GEM_TYPE = "gem_type"
INPUT_GEMS = "input_gems"
OUTPUT_GEMS = "output_gems"
IN_PORTS = "in_ports"
OUT_PORTS = "out_ports"
NUM_ROWS_OUTPUT = "num_rows_output"
NUM_ROWS = "num_rows"
STDOUT = "stdout"
STDERR = "stderr"
START_TIME = "start_time"
END_TIME = "end_time"
STATE = "state"
EXCEPTION = "exception"
FROM_PORT = "from_port"
TO_PORT = "to_port"
EXCEPTION_TYPE = "exception_type"
MSG = "msg"
CAUSE_MSG = "cause_msg"
STACK_TRACE = "stack_trace"
TIME = "time"
CONTENT = "content"


from enum import IntFlag, auto


class OffloadFlags(IntFlag):
    NO_OP = 0
    PIPELINE_RUNS = auto()
    COMPONENT_RUNS = auto()
    INTERIMS = auto()
    ALL = PIPELINE_RUNS | COMPONENT_RUNS | INTERIMS

    def should_offload_pipeline_run(self) -> bool:
        return (self & OffloadFlags.PIPELINE_RUNS) != 0

    def should_offload_component_runs(self) -> bool:
        return (self & OffloadFlags.COMPONENT_RUNS) != 0

    def should_offload_interims(self) -> bool:
        return (self & OffloadFlags.INTERIMS) != 0
