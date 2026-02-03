import json
import logging
from typing import List, Union
from concurrent.futures import ThreadPoolExecutor

from prophecy.executionmetrics.componentruns.component_run_service import (
    ComponentRunService,
)
from prophecy.executionmetrics.evolutions.models import (
    HiveStorageMetadata,
    StorageMetadata,
)
from prophecy.executionmetrics.interims.interims_table import (
    create_interims_table,
)
from prophecy.executionmetrics.package import (
    ComponentRuns,
    ComponentRunsWithRunDates,
    ComponentRunsWithStatus,
    DatasetRunsResponseCamelCase,
    GemProgressResponseCamelCase,
    HistoricalViewCodeResponse,
    InterimResponseCamelCase,
    PipelineRuns,
    PipelineRunsResponseCamelCase,
    ResponseWrapper,
)
from prophecy.executionmetrics.package import InterimResponse as InterimResRaw
from prophecy.executionmetrics.pipelineruns.pipeline_run_service import (
    PipelineRunsService,
)
from prophecy.executionmetrics.utils.external import Filters
from prophecy.jsonrpc.models import (
    DatasetDetailedResponse,
    DatasetRunsDetailedRequest,
    DatasetRunsRequest,
    DatasetRunsResponse,
    DeleteDatasetRunRequest,
    DeleteDatasetRunResponse,
    DeletePipelineRunRequest,
    DeletePipelineRunResponse,
    ErrorResponse,
    GemLevelProgressResponse,
    HistoricalGemProgressRequest,
    HistoricalViewRequest,
    HistoricalViewResponse,
    InterimResponse,
    InterimsRequest,
    LoadLastPipelineRunInterimsRequest,
    PipelineRunsRequest,
    PipelineRunsResponse,
    SuccessResponse,
)

# Setting up logger
logger = logging.getLogger(__name__)

from pyspark.sql import SparkSession


# Constants
SUCCESS = "SUCCESS"
INSTRUMENTATION_JOB_ID = (
    "instrumentation_job_id"  # MOCK: MetricsCollector.InstrumentationJobId
)


class ExecutionMetricsHandler:
    """Handles execution metrics requests and operations."""

    def __init__(self, spark: SparkSession):
        self.spark = spark
        self.executor = ThreadPoolExecutor(max_workers=10)

    async def find_interim_response_for_pipeline(
        self, request: InterimsRequest
    ) -> "InterimResponse":
        """Find interim response data for a pipeline run."""

        run_id = request.runId
        updated_by = request.updatedBy
        filters = request.filters

        storage_metadata = filters.get_storage_metadata(
            self.spark, updated_by, filters.metrics_store
        )

        # Run both operations concurrently
        run_configs_opt: str = PipelineRunsService.create(
            self.spark, storage_metadata
        ).get_run_configs(run_id, updated_by, filters)

        runs: List[InterimResRaw] = ComponentRunService.create(
            self.spark, storage_metadata
        ).get_interims_for_pipeline_run_id(run_id, updated_by, filters)

        # Process results
        run_configs = {}
        if run_configs_opt:
            run_configs = json.loads(
                run_configs_opt
            )  # Assuming RunConfigMap can be parsed as JSON

        interim_responses = []
        for run in runs:
            interim_responses.append(
                InterimResponseCamelCase.from_interim_response(run, run_configs)
            )

        wrapped_responses = ResponseWrapper.wrap(interim_responses)
        return InterimResponse(wrapped_responses)

    async def get_gem_progress_for_pipeline(
        self, request: HistoricalGemProgressRequest
    ) -> "GemLevelProgressResponse":
        """Get gem-level progress information for a pipeline run."""

        run_id = request.pipelineRunId
        updated_by = request.updatedBy
        filters = request.filters

        storage_metadata = filters.get_storage_metadata(
            self.spark, updated_by, filters.metrics_store
        )

        runs: List[ComponentRuns] = ComponentRunService.create(
            self.spark, storage_metadata
        ).get_by_pipeline_run_id(run_id, get_expired_runs=False, filters=filters)

        gem_progress_list = []
        for run in runs:
            gem_progress_list.append(
                GemProgressResponseCamelCase.from_component_run(run)
            )

        wrapped_responses = ResponseWrapper.wrap(gem_progress_list)
        return GemLevelProgressResponse(wrapped_responses)

    def refresh_tables(
        self, spark: SparkSession, storage_metadata: StorageMetadata, user_id: str
    ) -> None:
        """Refresh all tables for the given storage metadata."""
        PipelineRunsService.create(spark, storage_metadata).refresh()
        ComponentRunService.create(spark, storage_metadata).refresh()
        create_interims_table(spark, user_id, storage_metadata).refresh()

    def refresh_tables_with_filters(self, filters: Filters) -> None:
        """Refresh tables based on filters and storage type."""
        created_by = filters.created_by or "0"
        storage_metadata = filters.get_storage_metadata(
            self.spark, created_by, filters.metrics_store
        )

        # Only refresh for Hive tables
        if isinstance(storage_metadata, HiveStorageMetadata):
            self.refresh_tables(self.spark, storage_metadata, created_by)
        # For other storage types (like Delta), do nothing to avoid regression issues

    # async def process_em_requests(self, uid: str, request: EMRequest) -> None:
    #     """Process various execution metrics requests."""
    #     try:
    #         response = await self._handle_request(uid, request)
    #         # Publish success response
    #         self._publish_record(SuccessResponse(uid, response))
    #     except Exception as e:
    #         logger.error(
    #             f"Error fetching execution metrics data for request {uid}",
    #             exc_info=True,
    #         )
    #         # Publish error response
    #         self._publish_record(ErrorResponse(uid, JsonRpcError(e)))

    # async def _handle_request(self, uid: str, request: EMRequest) -> Any:
    #     """Handle different types of EM requests."""
    #     if isinstance(request, DatasetRunsDetailedRequest):
    #         return await self._handle_dataset_runs_detailed(request)

    #     elif isinstance(request, DatasetRunsRequest):
    #         return await self._handle_dataset_runs(request)

    #     elif isinstance(request, InterimsRequest):
    #         return await self.find_interim_response_for_pipeline(
    #             request.runId, request.updatedBy, request.filters
    #         )

    #     elif isinstance(request, HistoricalGemProgressRequest):
    #         return await self.get_gem_progress_for_pipeline(
    #             request.pipelineRunId, request.updatedBy, request.filters
    #         )

    #     elif isinstance(request, HistoricalViewRequest):
    #         return await self._handle_historical_view(request)

    #     elif isinstance(request, PipelineRunsRequest):
    #         return await self._handle_pipeline_runs(request)

    #     elif isinstance(request, DeleteDatasetRunRequest):
    #         return await self._handle_delete_dataset_run(request)

    #     elif isinstance(request, DeletePipelineRunRequest):
    #         return await self._handle_delete_pipeline_run(request)

    #     elif isinstance(request, LoadLastPipelineRunInterimsRequest):
    #         return await self._handle_load_last_pipeline_run_interims(request, uid)

    #     else:
    #         raise ValueError(f"Unknown request type: {type(request)}")

    async def _handle_dataset_runs_detailed(
        self, request: DatasetRunsDetailedRequest
    ) -> DatasetDetailedResponse:
        """Handle detailed dataset runs request."""
        storage_metadata = request.filters.get_storage_metadata(
            self.spark, request.user, request.filters.metrics_store
        )

        runs: ComponentRunsWithRunDates = ComponentRunService.create(
            self.spark, storage_metadata
        ).get_detailed_dataset(
            dataset_run_id=request.datasetRunId,
            updated_by=request.user,
            filters=request.filters,
        )

        dataset_runs = []
        if runs.component_runs_with_status_and_interims:
            for run in runs.component_runs_with_status_and_interims:
                dataset_runs.append(
                    DatasetRunsResponseCamelCase.from_component_runs_with_status_and_interims(
                        run, runs.run_dates
                    )
                )

        wrapped_responses = ResponseWrapper.wrap(dataset_runs)
        return DatasetDetailedResponse(wrapped_responses)

    async def _handle_dataset_runs(
        self, request: DatasetRunsRequest
    ) -> DatasetRunsResponse:
        """Handle dataset runs request."""
        storage_metadata = request.filters.get_storage_metadata(
            self.spark, "-1", request.filters.metrics_store
        )

        try:
            value: List[ComponentRunsWithStatus] = ComponentRunService.create(
                self.spark, storage_metadata
            ).get_dataset_runs_with_status(
                dataset_uri=request.datasetUid,
                limit=request.limit,
                filters=request.filters,
            )

            dataset_runs = [
                DatasetRunsResponseCamelCase.from_component_runs_with_status(run)
                for run in value
            ]
            wrapped_responses = ResponseWrapper.wrap(dataset_runs, limit=request.limit)
            return DatasetRunsResponse(wrapped_responses)

        except Exception as e:
            if self._is_table_or_view_not_found_exception(e):
                logger.error("TableOrViewNotFound exception, gulping it", exc_info=True)
                empty_response = ResponseWrapper.wrapEmpty(limit=request.limit)
                return DatasetRunsResponse(empty_response)
            raise

    async def _handle_historical_view(
        self, request: HistoricalViewRequest
    ) -> HistoricalViewResponse:
        """Handle historical view request."""
        storage_metadata = request.filters.get_storage_metadata(
            self.spark, request.updatedBy, request.filters.metrics_store
        )

        runs: PipelineRuns = PipelineRunsService.create(
            self.spark, storage_metadata
        ).historical_view(request.pipelineId, request.pipelineRunId, request.filters)

        response_data = HistoricalViewCodeResponse(
            request.pipelineId,
            PipelineRunsResponseCamelCase.from_pipeline_runs_with_code(runs),
        )
        return HistoricalViewResponse(response_data)

    async def _handle_pipeline_runs(
        self, request: PipelineRunsRequest
    ) -> PipelineRunsResponse:
        """Handle pipeline runs request."""
        storage_metadata = request.filters.get_storage_metadata(
            self.spark, "-1", request.filters.metrics_store
        )

        try:
            value: List[PipelineRuns] = PipelineRunsService.create(
                self.spark, storage_metadata
            ).get_by_pipeline_id(
                pipeline_uri=request.pipelineUid,
                limit=request.limit,
                filters=request.filters,
            )

            pipeline_runs = [
                PipelineRunsResponseCamelCase.from_pipeline_runs(run) for run in value
            ]
            wrapped_responses = ResponseWrapper.wrap(pipeline_runs, limit=request.limit)
            return PipelineRunsResponse(wrapped_responses)

        except Exception as e:
            if self._is_table_or_view_not_found_exception(e):
                logger.error("TableOrViewNotFound exception, gulping it", exc_info=True)
                empty_response = ResponseWrapper.wrapEmpty(request.limit)
                return PipelineRunsResponse(empty_response)
            raise

    async def _handle_delete_dataset_run(
        self, request: DeleteDatasetRunRequest
    ) -> DeleteDatasetRunResponse:
        """Handle delete dataset run request."""
        storage_metadata = request.filters.get_storage_metadata(
            self.spark, "-1", request.filters.metrics_store
        )

        ComponentRunService.create(self.spark, storage_metadata).expire(
            request.datasetRunId, request.filters
        )

        return DeleteDatasetRunResponse(request.datasetRunId, SUCCESS)

    async def _handle_delete_pipeline_run(
        self, request: DeletePipelineRunRequest
    ) -> DeletePipelineRunResponse:
        """Handle delete pipeline run request."""
        storage_metadata = request.filters.get_storage_metadata(
            self.spark, "-1", request.filters.metrics_store
        )

        PipelineRunsService.create(self.spark, storage_metadata).expire(
            request.pipelineRunId, request.filters
        )

        return DeletePipelineRunResponse(request.pipelineRunId, SUCCESS)

    async def _handle_load_last_pipeline_run_interims(
        self, request: LoadLastPipelineRunInterimsRequest, uid: str
    ) -> InterimResponse:
        """Handle load last pipeline run interims request."""
        try:
            # MOCK: with_prophecy_job and with_job_description context managers
            # In real implementation, these would be actual Spark context managers
            storage_metadata = request.filters.get_storage_metadata(
                self.spark, request.updatedBy, request.filters.metrics_store
            )

            pipeline_runs: List[PipelineRuns] = PipelineRunsService.create(
                self.spark, storage_metadata
            ).get_by_pipeline_id(request.pipelineUid, 1, request.filters)

            if pipeline_runs:
                return await self.find_interim_response_for_pipeline(
                    pipeline_runs[0].uid, request.updatedBy, request.filters
                )
            else:
                empty_response = ResponseWrapper.wrapEmpty()
                return InterimResponse(empty_response)

        except Exception as e:
            logger.error(
                f"Error with uid {uid} for lastPipelineInterims.", exc_info=True
            )
            empty_response = ResponseWrapper.wrapEmpty()
            return InterimResponse(empty_response)

    # async def _run_async(self, func):
    #     """Run a synchronous function asynchronously using thread pool."""
    #     loop = asyncio.get_event_loop()
    #     return await loop.run_in_executor(self.executor, func)

    def _is_table_or_view_not_found_exception(self, exception: Exception) -> bool:
        """Check if the exception is a table or view not found exception."""
        # MOCK: This would check specific exception types in real implementation
        error_message = str(exception).lower()
        return "table" in error_message and "not found" in error_message

    def _publish_record(self, message: Union[SuccessResponse, ErrorResponse]) -> None:
        """Publish response message to appropriate channel."""
        # MOCK: In real implementation, this would publish to a message queue or event bus
        if isinstance(message, SuccessResponse):
            logger.info(f"Publishing success response for uid: {message.uid}")
        else:
            logger.error(f"Publishing error response for uid: {message.uid}")
