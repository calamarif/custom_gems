import inspect
import json
import os
import logging
from threading import Lock
import time
from datetime import datetime, date
from typing import Optional, Any, Dict
import traceback
from py4j.protocol import Py4JError, Py4JJavaError
import uuid
from pyspark.sql import SparkSession, DataFrame, SQLContext

from prophecy.executionmetrics.in_memory_store import InMemoryStore
from prophecy.executionmetrics.models import PipelineStatus, RunType
from prophecy.executionmetrics.schemas.em import (
    SerializableException,
    TimestampedOutput,
)
from prophecy.executionmetrics.schemas.external import (
    InterimKey,
    MetricsTableNames,
    MetricsWriteDetails,
)
from prophecy.executionmetrics.utils.common import (
    get_spark_property_with_logging,
    is_serverless_env,
    now_millis,
    get_spark_property,
)
from prophecy.executionmetrics.utils.external import add_project_id_to_prophecy_uri
from prophecy.utils.constants import ProphecySparkConstants

try:
    from pyspark.errors import PySparkAttributeError
except:
    # pyspark.errors was introduced in spark 3.4
    # PySparkAttributeError was introduced in spark 3.4.1.
    # Before that, we would see AttributeError being thrown
    PySparkAttributeError = AttributeError
    pass
from pyspark.sql import *

try:
    from pyspark.sql.connect.session import SparkSession as ConnectSparkSession
    SPARK_SESSION_TYPES = (SparkSession, ConnectSparkSession)
except ImportError:
    SPARK_SESSION_TYPES = (SparkSession,)

from prophecy.utils.monitoring_utils import (
    capture_streams,
    monkey_patch_print,
    revert_monkey_patching,
)

try:
    # For Spark versions before 3.4.0
    from pyspark.sql.utils import CapturedException
except ImportError:
    # For Spark version 3.4.0 and later
    from pyspark.errors.exceptions.captured import CapturedException

from prophecy.libs.utils import (
    createScalaList,
    createScalaColumnOption,
    createScalaMap,
    createScalaColumnMap,
    createScalaColumnList,
    createScalaOption,
    isBlank,
)

# DONT REMOVE THIS - It is imported in few places within Prophecy (e.g., Python schema analysis), which in turn loads all dependencies.
from prophecy.libs.utils import *
from prophecy.utils.pipeline_monitoring import (
    sendGemProgressEvent2,
    sendGemProgressEvent3,
    sendPipelineProgressEvent2,
    sendPipelineProgressEvent3,
    get_process_from_gem2,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.hasHandlers():
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(handler)


is_serverless = is_serverless_env()
logger.debug(f"is_serverless is {is_serverless}")


class TaskState:
    LAUNCHING = "LAUNCHING"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    FINISHED = "FINISHED"


def task_state_to_pipeline_status(state: str) -> str:
    if state == TaskState.LAUNCHING:
        return PipelineStatus.STARTED
    elif state == TaskState.RUNNING:
        return PipelineStatus.RUNNING
    elif state == TaskState.FINISHED:
        return PipelineStatus.SUCCEEDED
    elif state == TaskState.FAILED:
        return PipelineStatus.FAILED
    return PipelineStatus.CANCELLED


class ProphecyDataFrame:
    def __init__(self, df: DataFrame, spark: SparkSession):
        self.jvm = spark.sparkContext._jvm
        self.spark = spark
        self.sqlContext = SQLContext(spark.sparkContext, sparkSession=spark)

        if type(df) == DataFrame:
            try:  # for backward compatibility
                self.extended_dataframe = (
                    self.jvm.org.apache.spark.sql.ProphecyDataFrame.extendedDataFrame(
                        df._jdf
                    )
                )
            except TypeError:
                self.extended_dataframe = (
                    self.jvm.io.prophecy.libs.package.ExtendedDataFrameGlobal(df._jdf)
                )
            self.dataframe = df
        else:
            try:
                self.extended_dataframe = (
                    self.jvm.org.apache.spark.sql.ProphecyDataFrame.extendedDataFrame(
                        df._jdf
                    )
                )
            except TypeError:
                self.extended_dataframe = (
                    self.jvm.io.prophecy.libs.package.ExtendedDataFrameGlobal(df._jdf)
                )
            self.dataframe = DataFrame(df, self.sqlContext)

    def interim(
        self,
        subgraph,
        component,
        port,
        subPath,
        numRows,
        interimOutput,
        detailedStats=False,
        run_id: Optional[str] = None,
        config: Optional[str] = None,
    ) -> DataFrame:
        result = self.extended_dataframe.interim(
            subgraph,
            component,
            port,
            subPath,
            numRows,
            interimOutput,
            detailedStats,
            run_id,
            config,
        )
        return DataFrame(result, self.sqlContext)

    # Ab Initio extensions to Prophecy DataFrame
    def collectDataFrameColumnsToApplyFilter(
        self, columnList, filterSourceDataFrame
    ) -> DataFrame:
        result = self.extended_dataframe.collectDataFrameColumnsToApplyFilter(
            createScalaList(self.spark, columnList), filterSourceDataFrame._jdf
        )
        return DataFrame(result, self.sqlContext)

    def normalize(
        self,
        lengthExpression,
        finishedExpression,
        finishedCondition,
        alias,
        colsToSelect,
        tempWindowExpr,
        lengthRelatedGlobalExpressions={},
        normalizeRelatedGlobalExpressions={},
        sparkSession=None,
    ) -> DataFrame:
        result = self.extended_dataframe.normalize(
            createScalaColumnOption(self.spark, lengthExpression),
            createScalaColumnOption(self.spark, finishedExpression),
            createScalaColumnOption(self.spark, finishedCondition),
            alias,
            createScalaColumnList(self.spark, colsToSelect),
            createScalaColumnMap(self.spark, tempWindowExpr),
            createScalaColumnMap(self.spark, lengthRelatedGlobalExpressions),
            createScalaColumnMap(self.spark, normalizeRelatedGlobalExpressions),
            createScalaOption(self.spark, sparkSession),
        )
        return DataFrame(result, self.sqlContext)

    def denormalizeSorted(
        self,
        groupByColumns,
        orderByColumns,
        denormalizeRecordExpression,
        finalizeExpressionMap,
        inputFilter,
        outputFilter,
        denormColumnName,
        countColumnName="count",
    ) -> DataFrame:
        result = self.extended_dataframe.denormalizeSorted(
            self,
            createScalaColumnList(self.spark, groupByColumns),
            createScalaColumnList(self.spark, orderByColumns),
            denormalizeRecordExpression,
            createScalaColumnMap(self.spark, finalizeExpressionMap),
            createScalaColumnOption(self.spark, inputFilter),
            createScalaColumnOption(self.spark, outputFilter),
            denormColumnName,
            countColumnName,
        )
        return DataFrame(result, self.sqlContext)

    def readSeparatedValues(
        self, inputColumn, outputSchemaColumns, recordSeparator, fieldSeparator
    ) -> DataFrame:
        result = self.extended_dataframe.readSeparatedValues(
            inputColumn._jc,
            createScalaList(self.spark, outputSchemaColumns),
            recordSeparator,
            fieldSeparator,
        )
        return DataFrame(result, self.sqlContext)

    def fuzzyDedup(
        self, dedupColumnName, threshold, sparkSession, algorithm
    ) -> DataFrame:
        result = self.extended_dataframe.fuzzyDedup(
            dedupColumnName,
            threshold,
            sparkSession._jsparkSession,
            algorithm,
        )
        return DataFrame(result, self.sqlContext)

    def fuzzyPurgeMode(
        self, recordId, threshold, matchFields, includeSimilarityScore
    ) -> DataFrame:
        result = self.extended_dataframe.fuzzyPurgeMode(
            recordId,
            threshold,
            createScalaMap(self.spark, matchFields),
            includeSimilarityScore,
        )
        return DataFrame(result, self.sqlContext)

    def fuzzyMergeMode(
        self, recordId, sourceId, threshold, matchFields, includeSimilarityScore
    ) -> DataFrame:
        result = self.extended_dataframe.fuzzyMergeMode(
            recordId,
            sourceId,
            threshold,
            createScalaMap(self.spark, matchFields),
            includeSimilarityScore,
        )
        return DataFrame(result, self.sqlContext)

    def syncDataFrameColumnsWithSchema(self, columnNames) -> DataFrame:
        result = self.extended_dataframe.syncDataFrameColumnsWithSchema(
            createScalaList(self.spark, columnNames)
        )
        return DataFrame(result, self.sqlContext)

    def zipWithIndex(
        self, startValue, incrementBy, indexColName, sparkSession
    ) -> DataFrame:
        result = self.extended_dataframe.zipWithIndex(
            startValue, incrementBy, indexColName, sparkSession._jsparkSession
        )
        return DataFrame(result, self.sqlContext)

    def metaPivot(self, pivotColumns, nameField, valueField, sparkSession) -> DataFrame:
        result = self.extended_dataframe.metaPivot(
            createScalaList(self.spark, pivotColumns),
            nameField,
            valueField,
            sparkSession._jsparkSession,
        )
        return DataFrame(result, self.sqlContext)

    def dynamicReplace(
        self,
        rulesDf,
        rulesOrderBy,
        baseColName,
        replacementExpressionColumnName,
        replacementValueColumnName,
        sparkSession,
    ) -> DataFrame:
        result = self.extended_dataframe.dynamicReplace(
            rulesDf,
            rulesOrderBy,
            baseColName,
            replacementExpressionColumnName,
            replacementValueColumnName,
            sparkSession._jsparkSession,
        )
        return DataFrame(result, self.sqlContext)

    def dynamicReplaceExpr(
        self,
        rulesDf,
        rulesOrderBy,
        baseColName,
        replacementExpressionColumnName,
        replacementValueColumnName,
        sparkSession,
    ) -> DataFrame:
        result = self.extended_dataframe.dynamicReplaceExpr(
            rulesDf,
            rulesOrderBy,
            baseColName,
            replacementExpressionColumnName,
            replacementValueColumnName,
            sparkSession._jsparkSession,
        )
        return DataFrame(result, self.sqlContext)

    def evaluate_expression(
        self, userExpression, selectedColumnNames, sparkSession
    ) -> DataFrame:
        result = self.extended_dataframe.evaluate_expression(
            userExpression,
            createScalaList(self.spark, selectedColumnNames),
            sparkSession._jsparkSession,
        )
        return DataFrame(result, self.sqlContext)

    def compareRecords(
        self, otherDataFrame, componentName, limit, sparkSession
    ) -> DataFrame:
        result = self.extended_dataframe.compareRecords(
            otherDataFrame._jdf, componentName, limit, sparkSession._jsparkSession
        )
        return DataFrame(result, self.sqlContext)

    def generateSurrogateKeys(
        self,
        keyDF,
        naturalKeys,
        surrogateKey,
        overrideSurrogateKeys,
        computeOldPortOutput,
        spark,
    ) -> (DataFrame, DataFrame, DataFrame):
        result = self.extended_dataframe.generateSurrogateKeys(
            keyDF._jdf,
            createScalaList(self.spark, naturalKeys),
            surrogateKey,
            createScalaOption(self.spark, overrideSurrogateKeys),
            computeOldPortOutput,
            spark._jsparkSession,
        )
        result.toString()
        return (
            DataFrame(result._1(), self.sqlContext),
            DataFrame(result._2(), self.sqlContext),
            DataFrame(result._3(), self.sqlContext),
        )

    def generateLogOutput(
        self,
        componentName,
        subComponentName,
        perRowEventTypes,
        perRowEventTexts,
        inputRowCount,
        outputRowCount,
        finalLogEventType,
        finalLogEventText,
        finalEventExtraColumnMap,
        sparkSession,
    ) -> DataFrame:
        result = self.extended_dataframe.generateLogOutput(
            componentName,
            subComponentName,
            createScalaColumnOption(self.spark, perRowEventTypes),
            createScalaColumnOption(self.spark, perRowEventTexts),
            inputRowCount,
            createScalaOption(self.spark, outputRowCount),
            createScalaColumnOption(self.spark, finalLogEventType),
            createScalaColumnOption(self.spark, finalLogEventText),
            createScalaColumnMap(self.spark, finalEventExtraColumnMap),
            sparkSession._jsparkSession,
        )

        return DataFrame(result, self.sqlContext)

    def mergeMultipleFileContentInDataFrame(
        self,
        fileNameDF,
        spark,
        delimiter,
        readFormat,
        joinWithInputDataframe,
        outputSchema=None,
        ffSchema=None,
        abinitioSchema=None,
    ) -> DataFrame:
        if outputSchema is not None:
            result = self.extended_dataframe.mergeMultipleFileContentInDataFrame(
                fileNameDF._jdf,
                spark._jsparkSession,
                outputSchema.json(),
                delimiter,
                readFormat,
                joinWithInputDataframe,
                createScalaOption(self.spark, ffSchema),
            )
        else:
            result = self.extended_dataframe.mergeMultipleFileContentInDataFrame(
                fileNameDF._jdf,
                spark._jsparkSession,
                abinitioSchema,
                delimiter,
                readFormat,
                joinWithInputDataframe,
            )
        return DataFrame(result, self.sqlContext)

    def breakAndWriteDataFrameForOutputFile(
        self, outputColumns, fileColumnName, fmt, delimiter
    ):
        self.extended_dataframe.breakAndWriteDataFrameForOutputFile(
            createScalaList(self.spark, outputColumns),
            fileColumnName,
            fmt,
            createScalaOption(self.spark, delimiter),
            createScalaOption(self.spark, None),
            True,
        )

    def breakAndWriteDataFrameForOutputFileWithSchema(
        self, outputSchema, fileColumnName, fmt, delimiter=None
    ):
        self.extended_dataframe.breakAndWriteDataFrameForOutputFileWithSchema(
            outputSchema,
            fileColumnName,
            fmt,
            createScalaOption(self.spark, delimiter),
        )

    def writeToOutputFile(self, outputPath, ffSchema, formatType, delimiter):
        self.extended_dataframe.writeToOutputFile(
            outputPath, ffSchema, formatType, delimiter
        )

    def deduplicate(self, typeToKeep, groupByColumns, orderByColumns):
        result = self.extended_dataframe.deduplicate(
            typeToKeep,
            createScalaColumnList(self.spark, groupByColumns),
            createScalaColumnList(self.spark, orderByColumns),
        )
        return DataFrame(result, self.sqlContext)

    def __getattr__(self, item: str):
        if item == "interim":
            self.interim

        if hasattr(self.extended_dataframe, item):
            return getattr(self.extended_dataframe, item)
        else:
            return getattr(self.dataframe, item)


class InterimConfig:
    jvm_accessible = False  # unused right now, can use in future.

    def __init__(self):
        self.isInitialized = False
        self.interimOutput = None
        self.session = None

    def initialize(self, spark: SparkSession, sessionForInteractive: str = ""):
        from py4j.java_gateway import JavaPackage

        self.isInitialized = True
        self.session = sessionForInteractive
        # It's `JavaClass` when scala-libs are present, and `JavaPackage` when they are not present.
        try:
            if (
                type(spark.sparkContext._jvm.org.apache.spark.sql.InterimOutputHive2)
                == JavaPackage
            ):
                InterimConfig.jvm_accessible = True
                raise Exception(
                    "Scala Prophecy Libs jar was not found in the classpath. Please add Scala Prophecy Libs and retry the operation"
                )
            self.interimOutput = (
                spark.sparkContext._jvm.org.apache.spark.sql.InterimOutputHive2.apply(
                    sessionForInteractive
                )
            )
        except PySparkAttributeError as ae:  # spark >= 3.4.1
            InterimConfig.jvm_accessible = False

    def maybeInitialize(self, spark: SparkSession, sessionForInteractive: str = ""):
        if not self.isInitialized:
            self.initialize(spark, sessionForInteractive)

    def clear(self):
        self.isInitialized = False
        self.interimOutput = None


interimConfig = InterimConfig()


class ProphecyDebugger:
    @classmethod
    def is_prophecy_wheel(cls, path):
        import zipfile

        zip_file = zipfile.ZipFile(path)
        for name in zip_file.namelist():
            if "workflow.latest.json" in name:
                return True
        return False

    @classmethod
    def wheels_in_path(cls):
        import sys, pathlib

        l = []
        for p in sys.path:
            try:
                for child in pathlib.Path(p).rglob("*.whl"):
                    if ProphecyDebugger.is_prophecy_wheel(child):
                        l.append(str(child))
            except IOError as e:
                ProphecyDebugger.log(
                    None, f"Error when trying to read path {p}: {str(e)}"
                )
                pass
        ProphecyDebugger.log(None, f"Wheels in path {l}")
        return l

    @classmethod
    def wheels_in_site_packages(cls):
        import sys, os

        target_file = "direct_url.json"
        url_list = []
        # Get list of site-packages directories
        site_packages = [s for s in sys.path if "site-packages" in s]

        # Walk through each site-packages directory
        for site_package in site_packages:
            ProphecyDebugger.log(None, f"site-package: {site_packages}")
            for dirpath, dirnames, filenames in os.walk(site_package):
                ProphecyDebugger.log(None, filenames)
                if target_file in filenames:
                    # Construct full path to the target file
                    file_path = os.path.join(dirpath, target_file)
                    try:
                        # Open and read the target file
                        with open(file_path, "r") as file:
                            data = json.load(file)
                            if "url" in data:
                                url_list.append(data["url"].replace("file://", ""))
                    except Exception as e:
                        ProphecyDebugger.log(None, f"Error reading {file_path}: {e}")

        ProphecyDebugger.log(None, f"urls fetched from site packages: {url_list}")
        return url_list

    # Uses a different ijson library. Accurate, but adds another dependency to libs
    # @classmethod
    # def find_file_in_wheel(cls, filename, wheel_path, desired_value):
    #     try:
    #         with zipfile.ZipFile(wheel_path, 'r') as z:
    #             if filename in z.namelist():
    #                 with z.open(filename) as json_file:
    #                     parser = ijson.parse(json_file)
    #                     for prefix, event, value in parser:
    #                         if prefix == "a.b" and value == desired_value:
    #                             # Reset the file pointer to the beginning
    #                             json_file.seek(0)
    #                             # Read and return the entire content
    #                             return json_file.read().decode('utf-8')
    #     except zipfile.BadZipFile:
    #         print(f"Warning: Could not read {wheel_path}. Might be a corrupted wheel.")
    #     except PermissionError:
    #         print(f"Warning: Permission denied when trying to read {wheel_path}.")
    #     except IOError as e:
    #         print(f"Warning: IO Error ({e}) when trying to read {wheel_path}.")
    #     return None

    @classmethod
    def is_pipeline_wheel(
        cls, wheel_path, pipeline_uri, filename="workflow.latest.json"
    ):
        import zipfile

        key_pattern = f'"uri" : "{pipeline_uri}"'  # Basic pattern match to avoid using new dependencies
        try:
            with zipfile.ZipFile(wheel_path, "r") as z:
                if any(name.endswith(filename) for name in z.namelist()):
                    for file_to_read in z.namelist():
                        if file_to_read.endswith(filename):
                            with z.open(file_to_read) as json_file:
                                content = json_file.read().decode("utf-8")
                                if key_pattern in content:
                                    return True
        except zipfile.BadZipFile:
            ProphecyDebugger.log(
                None,
                f"Warning: Could not read {wheel_path}. Might be a corrupted wheel",
            )
        except PermissionError:
            ProphecyDebugger.log(
                None, f"Warning: Permission denied when trying to read {wheel_path}"
            )
        except IOError as e:
            ProphecyDebugger.log(
                None, f"Warning: IO Error {e} when trying to read {wheel_path}"
            )
        return False

    @classmethod
    def find_pipeline_wheel(cls, pipeline_uri):
        wheels = (
            ProphecyDebugger.wheels_in_path()
            + ProphecyDebugger.wheels_in_site_packages()
        )
        for wheel_path in wheels:
            if ProphecyDebugger.is_pipeline_wheel(wheel_path, pipeline_uri):
                return wheel_path
        ProphecyDebugger.log(
            None,
            f"Could not find pipeline code for pipeline {pipeline_uri} in wheels {wheels}",
        )
        return None

    @classmethod
    def log(cls, spark: SparkSession, s: str):
        import logging

        # log4jLogger = sc._jvm.org.apache.log4j
        # LOGGER = log4jLogger.LogManager.getLogger("ProphecyDebugger")
        # LOGGER.info(s)
        logger = logging.getLogger("py4j")
        logger.info(s)

    @classmethod
    def sparkSqlShow(cls, spark: SparkSession, query: str):
        spark.sparkContext._jvm.org.apache.spark.sql.ProphecyDebugger.sparkSqlShow(
            spark._jsparkSession, query
        )

    @classmethod
    def sparkSql(cls, spark: SparkSession, query: str):
        jdf = spark.sparkContext._jvm.org.apache.spark.sql.ProphecyDebugger.sparkSql(
            spark._jsparkSession, query
        )
        return DataFrame(jdf, spark)

    @classmethod
    def exception(cls, spark: SparkSession):
        spark.sparkContext._jvm.org.apache.spark.sql.ProphecyDebugger.exception(
            spark._jsparkSession
        )

    @classmethod
    def class_details(cls, spark: SparkSession, name: str):
        return (
            spark.sparkContext._jvm.org.apache.spark.sql.ProphecyDebugger.classDetails(
                spark._jsparkSession, name
            )
        )

    @classmethod
    def spark_conf(cls, spark: SparkSession):
        return spark.sparkContext._jvm.org.apache.spark.sql.ProphecyDebugger.sparkConf(
            spark._jsparkSession
        )

    @classmethod
    def runtime_conf(cls, spark: SparkSession):
        return (
            spark.sparkContext._jvm.org.apache.spark.sql.ProphecyDebugger.runtimeConf(
                spark._jsparkSession
            )
        )

    @classmethod
    def local_properties(cls, spark: SparkSession):
        return spark.sparkContext._jvm.org.apache.spark.sql.ProphecyDebugger.localProperties(
            spark._jsparkSession
        )

    @classmethod
    def local_property(cls, spark: SparkSession, key: str):
        return (
            spark.sparkContext._jvm.org.apache.spark.sql.ProphecyDebugger.localProperty(
                spark._jsparkSession, key
            )
        )

    @classmethod
    def local_property_async(cls, spark: SparkSession, key: str):
        return spark.sparkContext._jvm.org.apache.spark.sql.ProphecyDebugger.localPropertyAsync(
            spark._jsparkSession, key
        )

    @classmethod
    def get_scala_object(cls, spark: SparkSession, className: str):
        return spark.sparkContext._jvm.org.apache.spark.sql.ProphecyDebugger.getScalaObject(
            spark._jsparkSession, className
        )

    @classmethod
    def call_scala_object_method(
        cls, spark: SparkSession, className: str, methodName: str, args: list = []
    ):
        return spark.sparkContext._jvm.org.apache.spark.sql.ProphecyDebugger.callScalaObjectMethod(
            spark._jsparkSession, className, methodName, args
        )

    @classmethod
    def call_scala_object_method_async(
        cls, spark: SparkSession, className: str, methodName: str, args: list = []
    ):
        return spark.sparkContext._jvm.org.apache.spark.sql.ProphecyDebugger.callScalaObjectMethodAsync(
            spark._jsparkSession, className, methodName, args
        )

def process_captured_exception(captured_error: CapturedException) -> Optional[Py4JJavaError]:
    if (
        hasattr(captured_error, "getErrorClass")
        and captured_error.getErrorClass()
    ):
        return captured_error._origin

    if (
        hasattr(captured_error, "cause")
        and captured_error.cause
        and hasattr(captured_error.cause, "getErrorClass")
        and captured_error.cause.getErrorClass()
    ):
        return captured_error.cause._origin

    if captured_error._origin:
        return captured_error._origin
    
    if hasattr(captured_error, "cause") and captured_error.cause and captured_error.cause._origin:
        return captured_error.cause._origin
    
    return None


class MetricsCollector:

    jvm_accessible = False

    _lock = Lock()
    _spark_session_to_id_map: Dict[SparkSession, str] = {}  # Using object id as key
    _spark_session_id_to_spark_session: Dict[str, SparkSession] = {}
    _session_data_store: Dict[str, InMemoryStore] = {}

    DEFAULT_UNDEF = "undef"

    @classmethod
    def get_session_appended_key(cls, key: str, session: str) -> str:
        """Get session-appended key."""
        return f"{key}.{session}"

    @classmethod
    def get_unique_session_id(cls, spark: SparkSession) -> Optional[str]:
        """Get unique session ID."""
        with cls._lock:
            return cls._spark_session_to_id_map.get(spark)

    @classmethod
    def get_session(cls, session_for_interactive: str) -> str:
        """Get session ID."""
        return (
            str(uuid.uuid4())
            if not session_for_interactive
            else session_for_interactive
        )

    @classmethod
    def get_job_group(cls, spark: SparkSession) -> str:
        """Get job group from spark context."""
        # MOCK: Getting local property from SparkContext
        return (
            spark.sparkContext.getLocalProperty(ProphecySparkConstants.GROUP_ID_KEY)
            or ""
        )

    @classmethod
    def generate_job_group(cls) -> str:
        """Generate a job group ID."""
        import random

        def generate_random_digits(n: int) -> str:
            return "".join(str(random.randint(0, 9)) for _ in range(n))

        return f"{generate_random_digits(18)}_{generate_random_digits(19)}_job-{generate_random_digits(12)}-run-{generate_random_digits(8)}"

    @classmethod
    def get_task_id_from_group(cls, spark: SparkSession) -> str:
        """Extract task ID from job group."""
        job_group = cls.get_job_group(spark)
        logger.info(f"job group is {job_group}")

        parts = job_group.split("_")
        job_and_run = next((s for s in parts if "job" in s and "run" in s), None)

        if job_and_run:
            return job_and_run.split("-")[3]  # Extract task id
        return job_group

    @classmethod
    def configure_spark_session(cls, spark: SparkSession, session: str):
        """Configure spark session."""
        if (
            not is_serverless
            and spark.sparkContext.getLocalProperty(ProphecySparkConstants.GROUP_ID_KEY)
            is None
        ):
            spark.sparkContext.setJobGroup(
                cls.generate_job_group(), "Prophecy: Job Group"
            )

        # Check if storage format is Hive
        storage_format = (
            get_spark_property(
                cls.get_session_appended_key(
                    ProphecySparkConstants.SPARK_CONF_STORAGE_FORMAT, session
                ),
                spark,
            )
            or get_spark_property(
                ProphecySparkConstants.SPARK_CONF_STORAGE_FORMAT, spark
            )
            or "DeltaStore"
        )

        is_storage_format_hive = storage_format == "Hive"
        logger.info(f"isStorageFormatHive: {is_storage_format_hive}")

        if is_storage_format_hive:
            spark.conf.set("hive.exec.dynamic.partition", "true")
            spark.conf.set("hive.exec.dynamic.partition.mode", "nonstrict")

    @classmethod
    def _get_spark_execution_url(cls, spark: SparkSession) -> Optional[str]:
        """Get spark execution URL."""
        return get_spark_property(
            ProphecySparkConstants.SPARK_CONF_SERVICE_URL_KEY, spark
        )

    @classmethod
    def _decompress(cls, encoded: str) -> str:
        """
        Placeholder implementation: assumes each part is
        base64-encoded + gzipped bytes of UTF-8 JSON text.
        """
        import base64 as base64_std
        import gzip

        raw: bytes = base64_std.b64decode(encoded)
        return gzip.decompress(raw).decode("utf-8")

    @classmethod
    def _get_running_code(cls, spark: SparkSession, session: str) -> Dict[str, str]:
        """Get running code from spark config."""
        # Check if code is split into parts
        parts_key = f"{cls.get_session_appended_key(ProphecySparkConstants.SPARK_CONF_PIPELINE_CODE_KEY, session)}_parts"
        parts = get_spark_property(parts_key, spark)

        if parts:
            logger.info(f"Got code split in {parts} parts")

            compressed_code_parts = []
            for part_id in range(int(parts)):
                part_key = f"{cls.get_session_appended_key(ProphecySparkConstants.SPARK_CONF_PIPELINE_CODE_KEY, session)}_{part_id}"
                part_data = get_spark_property(part_key, spark)
                if part_data:
                    compressed_code_parts.append(part_data)

            compressed_code = "".join(compressed_code_parts)
            decompressed_code = cls._decompress(compressed_code)

            try:
                rdc = json.loads(decompressed_code)
            except json.JSONDecodeError as e:
                logger.error("Failed to parse json using json library", e)
                rdc = {}

            return rdc

        else:
            # Try to get non-split code
            compressed_code = get_spark_property(
                cls.get_session_appended_key(
                    ProphecySparkConstants.SPARK_CONF_PIPELINE_CODE_KEY, session
                ),
                spark,
            )
            if compressed_code:
                try:
                    decompressed = cls._decompress(compressed_code)
                    return json.loads(decompressed)
                except Exception as e:
                    logger.error("Failed to parse json using json library", e)

        return {}

    @classmethod
    def _should_offload_in_test_env(cls, spark: SparkSession) -> bool:
        """Check if we should offload in test environment."""
        return (
            get_spark_property(
                ProphecySparkConstants.SPARK_CONF_OFFLOAD_FOR_TEST_ENABLED, spark
            )
            == "true"
        )

    @classmethod
    def _handle_start_for_serverless(
        cls,
        spark: SparkSession,
        session_for_interactive: str = "",
        pipeline_id: str = "",
        pipeline_config_opt=None,
    ):
        if not is_serverless:
            # Extra check so that this does not run on non-serverless
            return

        try:
            cls._start_for_serverless(
                spark, session_for_interactive, pipeline_id, pipeline_config_opt
            )
        except Exception as e:
            logger.info(
                f"Failed to start for serverless: {e} -- {traceback.format_exc()}"
            )

    @classmethod
    def update_gem_progress(
        cls,
        spark: SparkSession,
        process_id: str,
        state: str,
        startTime: str,
        endTime: str,
        stdout: str,
        stderr: str,
        exception: Exception,
    ):
        try:
            uuid_str = cls._spark_session_to_id_map.get(spark)

            logger.info(f"update_gem_progress: spark {spark}, uuid: {uuid_str}")

            # Log in-memory state
            store = cls._session_data_store.get(uuid_str)
            if not store:
                logger.info("Couldn't find in memory state for updating gem progress")
                return

            store.update_gem_progress(
                process=process_id,
                start_time=startTime,
                end_time=endTime,
                stdout=(
                    [TimestampedOutput.from_content(stdout)]
                    if stdout and stdout != "[]"
                    else None
                ),
                stderr=(
                    [TimestampedOutput.from_content(stderr)]
                    if stderr and stdout != "[]"
                    else None
                ),
                state=state,
                exception=(
                    SerializableException.from_exception(exception)
                    if exception
                    else None
                ),
            )
        except Exception as e:
            logger.info(f"Error updating gem progress for {process_id}: {e}")

    @classmethod
    def _start_for_serverless(
        cls,
        spark: SparkSession,
        session_for_interactive: str = "",
        pipeline_id: str = "",
        pipeline_config_opt=None,
    ):
        if not is_serverless:
            # Extra check so that this does not run on non-serverless
            return

        session = cls.get_session(session_for_interactive)

        # Handle pipeline URI
        if not pipeline_id:
            pipeline_uri = get_spark_property(pipeline_id, spark) or pipeline_id
        else:
            project_id = get_spark_property(
                ProphecySparkConstants.SPARK_CONF_PROJECT_ID, spark
            )
            pipeline_uri = add_project_id_to_prophecy_uri(pipeline_id, project_id)

        logger.info(
            f"MetricsCollector.start method with spark {session} "
            f"pipelineId {pipeline_uri} and sessionForInteractive {session_for_interactive}"
        )

        # with self._lock:
        #     self._spark_session_id_to_spark_session[session] = spark

        #     logger.info(f"spark hashcode before putting in map: {id(spark)}")

        #     old_session = self._spark_session_to_id_map.get(id(spark))
        #     self._spark_session_to_id_map[id(spark)] = session

        #     if old_session:
        #         logger.info(
        #             f"Replaced uuid for spark session. old value: {old_session}, new value: {session}"
        #         )
        #     else:
        #         logger.info(f"Added uuid for spark session value: {session}")

        execution_url_option = cls._get_spark_execution_url(spark)

        cls.configure_spark_session(spark, session)

        # if not execution_url_option:
        #     return None

        is_job = not session_for_interactive

        logger.info(f"Execution ServiceURL: {execution_url_option}, is_job: {is_job}")

        time_started = now_millis()

        if is_job:
            cls._handle_job_start(
                spark, session, pipeline_uri, time_started, pipeline_config_opt
            )
        else:
            cls._handle_interactive_start(
                spark,
                session,
                pipeline_uri,
                pipeline_id,
                time_started,
                pipeline_config_opt,
            )

    @classmethod
    def _handle_job_start(
        cls,
        spark: SparkSession,
        session: str,
        pipeline_uri: str,
        time_started: int,
        pipeline_config_optional: Optional[str],
    ):
        """Handle job start."""
        job_uri = get_spark_property(
            ProphecySparkConstants.SPARK_CONF_JOB_URI_KEY, spark
        )
        fabric_id = get_spark_property(
            ProphecySparkConstants.SPARK_CONF_FABRIC_ID_KEY, spark
        )
        user_id = get_spark_property(
            ProphecySparkConstants.SPARK_CONF_USER_ID_KEY, spark
        )
        branch = get_spark_property(ProphecySparkConstants.SPARK_CONF_JOB_BRANCH, spark)
        prophecy_url = get_spark_property(ProphecySparkConstants.SPARK_CONF_URL, spark)

        expected_interims_str = get_spark_property(
            ProphecySparkConstants.SPARK_CONF_EXPECTED_INTERIMS, spark
        )
        expected_interims = []
        if expected_interims_str:
            try:
                expected_interims_data = json.loads(expected_interims_str)
                expected_interims = [
                    InterimKey(**item) for item in expected_interims_data
                ]
            except Exception as e:
                logger.error("Failed to parse expected interims", exc_info=True)

        task_run_id = cls.get_task_id_from_group(spark)
        uuid_str = str(uuid.uuid4())

        # job_metrics_metadata = JobMetricsMetadata(
        #     uuid=uuid_str,
        #     job_uri=job_uri or cls.DEFAULT_UNDEF,
        #     pipeline_uri=pipeline_uri,
        #     fabric_id=fabric_id or cls.DEFAULT_UNDEF,
        #     time_started=time_started,
        #     is_interactive=get_spark_property(
        #         ProphecySparkConstants.SPARK_CONF_RUN_TYPE_KEY, spark
        #     )
        #     == "true",
        #     task_run_id=task_run_id,
        #     user_id=user_id,
        #     branch=branch or cls.DEFAULT_UNDEF,
        #     prophecy_url=prophecy_url,
        #     expected_interims=expected_interims,
        #     pipeline_config=pipeline_config_optional,
        # )

        # logger.info(
        #     f"JobsMetricsEvent {job_metrics_metadata.truncated_string()} "
        #     f"spark {session} with pipelineUri {pipeline_uri}"
        # )

        # # Set spark conf for jar path if not already set
        # if not spark.conf.get(
        #     ProphecySparkConstants.SPARK_CONF_PIPELINE_PACKAGE_KEY, None
        # ):
        #     # MOCK: Getting pipeline jar path
        #     logger.info("Jar not found in classpath")

        metrics_write_details = cls._get_metrics_write_details(
            spark, session, is_job=True
        )
        run_type = (
            RunType.ADHOC
            if get_spark_property(ProphecySparkConstants.SPARK_CONF_RUN_TYPE_KEY, spark)
            == "true"
            else RunType.SCHEDULED
        )
        store = InMemoryStore(spark, uuid_str)
        store.init(
            pipeline_uri=pipeline_uri,
            job_uri=job_uri or cls.DEFAULT_UNDEF,
            fabric_uid=fabric_id or cls.DEFAULT_UNDEF,
            run_type=run_type,
            created_by=user_id or "0",
            code=None,
            branch=branch or "",
            db_suffix=prophecy_url or "",
            expected_interims=expected_interims,
            pipeline_config=pipeline_config_optional,
            metrics_write_details=metrics_write_details,
        )
        with cls._lock:
            cls._session_data_store[uuid_str] = store
            cls._spark_session_to_id_map[spark] = uuid_str

    @classmethod
    def _handle_interactive_start(
        cls,
        spark: SparkSession,
        session: str,
        pipeline_uri: str,
        pipeline_id: str,
        time_started: int,
        pipeline_config_optional: Optional[str],
    ):
        """Handle interactive start."""
        fabric_id = get_spark_property(
            cls.get_session_appended_key(
                ProphecySparkConstants.SPARK_CONF_FABRIC_ID_KEY, session
            ),
            spark,
        )
        user_id = get_spark_property(
            cls.get_session_appended_key(
                ProphecySparkConstants.SPARK_CONF_USER_ID_KEY, session
            ),
            spark,
        )
        branch = get_spark_property(
            cls.get_session_appended_key(
                ProphecySparkConstants.SPARK_CONF_JOB_BRANCH, session
            ),
            spark,
        )
        prophecy_url = get_spark_property(
            cls.get_session_appended_key(
                ProphecySparkConstants.SPARK_CONF_URL, session
            ),
            spark,
        )

        # # Get pipeline processes
        # pipeline_processes = {}
        # processes_str = get_spark_property(
        #     cls.get_session_appended_key(
        #         ProphecySparkConstants.SPARK_CONF_PIPELINE_PROCESSES_KEY, session
        #     ),
        #     spark,
        # )
        # if processes_str:
        #     try:
        #         # Try to decompress first
        #         decompressed = cls._decompress(processes_str)
        #         processes_data = json.loads(decompressed)
        #         pipeline_processes = {
        #             k: WorkflowProcessNodeInfo(**v) for k, v in processes_data.items()
        #         }
        #     except Exception:
        #         logger.error("Failed to parse pipeline processes", exc_info=True)

        code = cls._get_running_code(spark, session)
        logger.info(f"Code received contained following files -> {code.keys()}")

        # job_group_matcher = DatabricksJobGroupMatcher(command_id="")

        uuid_str = get_spark_property(
            cls.get_session_appended_key(
                ProphecySparkConstants.SPARK_CONF_PIPELINE_UUID_KEY, session
            ),
            spark,
        )
        if not uuid_str:
            raise RuntimeError(
                f"session key not found {cls.get_session_appended_key(ProphecySparkConstants.SPARK_CONF_PIPELINE_UUID_KEY, session)}"
            )

        # Get expected interims
        expected_interims = []
        expected_interims_str = get_spark_property(
            cls.get_session_appended_key(
                ProphecySparkConstants.SPARK_CONF_EXPECTED_INTERIMS, session
            ),
            spark,
        )
        if expected_interims_str:
            try:
                decompressed = cls._decompress(expected_interims_str)
                expected_interims_data = json.loads(decompressed)
                expected_interims = [
                    InterimKey(**item) for item in expected_interims_data
                ]
            except Exception:
                logger.error("Failed to parse expected interims", exc_info=True)

        # TODO - Not possible in serverless (find proper usage and set the value correctly)
        # task_run_id = cls.get_task_id_from_group(spark)
        task_run_id = uuid_str

        # execution_metrics_metadata = ExecutionMetricsMetadata(
        #     uuid=uuid_str,
        #     job_id="",
        #     pipeline_uid=pipeline_id,
        #     fabric_id=fabric_id or cls.DEFAULT_UNDEF,
        #     time_started=time_started,
        #     run_type=RunType.INTERACTIVE,
        #     job_run_id=task_run_id,
        #     task_run_id=task_run_id,
        #     user_id=user_id or "",
        #     branch=branch,
        #     expected_interims=expected_interims,
        #     code=code,
        #     prophecy_url=prophecy_url,
        #     pipeline_config=pipeline_config_optional,
        # )

        # job_group_status_track_request = JobGroupStatusTrackRequest(
        #     session=session,
        #     job_group=cls.get_job_group(spark),
        #     job_group_matcher=job_group_matcher,
        #     execution_metrics_metadata=execution_metrics_metadata,
        # )

        # logger.info(
        #     f"Interactive metrics collection beginning with metadata {cls._truncate(str(execution_metrics_metadata))}"
        # )

        metrics_write_details = cls._get_metrics_write_details(
            spark, session, is_job=False
        )

        # Create in-memory store
        store = InMemoryStore(spark, uuid_str)
        store.init(
            pipeline_uri=pipeline_uri,
            job_uri="",
            fabric_uid=fabric_id or cls.DEFAULT_UNDEF,
            run_type=RunType.INTERACTIVE,
            created_by=user_id or "",
            code=code,
            branch=branch or "",
            db_suffix=prophecy_url or "",
            expected_interims=expected_interims,
            pipeline_config=pipeline_config_optional,
            metrics_write_details=metrics_write_details,
        )
        with cls._lock:
            if uuid_str not in cls._session_data_store:
                cls._session_data_store[uuid_str] = store
            cls._spark_session_to_id_map[spark] = uuid_str
            cls._session_data_store[uuid_str].update_run_uid(task_run_id, task_run_id)

    @classmethod
    def _get_metrics_write_details(
        cls, spark: SparkSession, session: str, is_job: bool
    ) -> Optional[MetricsWriteDetails]:
        """Get metrics write details."""
        # Check if offload is disabled
        disable_key = (
            ProphecySparkConstants.SPARK_CONF_DISABLE_OFFLOAD
            if is_job
            else cls.get_session_appended_key(
                ProphecySparkConstants.SPARK_CONF_DISABLE_OFFLOAD, session
            )
        )

        if get_spark_property_with_logging(disable_key, spark, logger) == "true":
            logger.info(
                "Execution metrics are disabled. So not offloading to Metric-Sink"
            )
            return None

        # Check catalog implementation
        catalog_impl = spark.conf.get("spark.sql.catalogImplementation", "hive")
        if catalog_impl == "in-memory":
            logger.warning(
                "Execution metrics will not be stored because catalog implementation is in-memory"
            )
            return None

        logger.info(
            f"Execution metrics will be stored because catalog implementation is {catalog_impl}"
        )

        # Get table names
        if is_job:
            pipeline_table = get_spark_property_with_logging(
                ProphecySparkConstants.SPARK_CONF_PIPELINE_METRICS_TABLE, spark, logger
            )
            component_table = get_spark_property_with_logging(
                ProphecySparkConstants.SPARK_CONF_COMPONENT_METRICS_TABLE, spark, logger
            )
            interims_table = get_spark_property_with_logging(
                ProphecySparkConstants.SPARK_CONF_INTERIMS_TABLE, spark, logger
            )
            storage_format_key = ProphecySparkConstants.SPARK_CONF_STORAGE_FORMAT
            partitioning_key = (
                ProphecySparkConstants.SPARK_CONF_TABLE_PARTITIONING_DISABLED
            )
        else:
            pipeline_table = get_spark_property_with_logging(
                cls.get_session_appended_key(
                    ProphecySparkConstants.SPARK_CONF_PIPELINE_METRICS_TABLE, session
                ),
                spark,
                logger,
            )
            component_table = get_spark_property_with_logging(
                cls.get_session_appended_key(
                    ProphecySparkConstants.SPARK_CONF_COMPONENT_METRICS_TABLE, session
                ),
                spark,
                logger,
            )
            interims_table = get_spark_property_with_logging(
                cls.get_session_appended_key(
                    ProphecySparkConstants.SPARK_CONF_INTERIMS_TABLE, session
                ),
                spark,
                logger,
            )
            storage_format_key = cls.get_session_appended_key(
                ProphecySparkConstants.SPARK_CONF_STORAGE_FORMAT, session
            )
            partitioning_key = cls.get_session_appended_key(
                ProphecySparkConstants.SPARK_CONF_TABLE_PARTITIONING_DISABLED, session
            )

        table_names = MetricsTableNames(
            pipeline_metrics=pipeline_table,
            component_metrics=component_table,
            interims=interims_table,
        )

        # Get storage format
        storage_format = (
            get_spark_property_with_logging(storage_format_key, spark, logger)
            or "DeltaStore"
        )

        # Get partitioning disabled flag
        is_partitioning_disabled = (
            get_spark_property_with_logging(partitioning_key, spark, logger) == "true"
        )

        return MetricsWriteDetails(
            table_names, storage_format, is_partitioning_disabled
        )

    @classmethod
    def get_inmemory_store(cls, spark: SparkSession) -> InMemoryStore:
        with cls._lock:
            uuid_str = cls._spark_session_to_id_map.get(spark)
            if not uuid_str:
                logger.info(f"Unable to find InMemoryStore for key {spark}")

            return cls._session_data_store.get(uuid_str)

    @classmethod
    def _handle_end_for_serverless(
        cls, spark: SparkSession, pipeline_status: str, should_offload: bool
    ):
        if not is_serverless:
            # Extra check so that this does not run on non-serverless
            return

        # Added this flag to control offloading being called more than once
        # MetricsCollector.end is being explicitly called from other places as well
        if not should_offload:
            return

        try:
            uuid_str = cls._spark_session_to_id_map.get(spark)

            logger.info(f"_handle_end_for_serverless: spark {spark}, uuid: {uuid_str}")

            # Log in-memory state
            store = cls._session_data_store.get(uuid_str)
            if not store:
                logger.info(f"*Couldn't find in memory state for {uuid_str}*")

            # Offload metrics if not in test environment
            if not cls._should_offload_in_test_env(spark):
                if not store:
                    logger.info(f"sessionDataStore did not have entry for {uuid_str}")
                else:
                    logger.info(
                        f"Removed {uuid_str} from sessionDataStore. Offloading to storage: {store.has_storage_metadata}"
                    )
                    if store.has_storage_metadata:
                        store.offload(pipeline_status=pipeline_status)
        except Exception as e:
            logger.info(f"Exception in _end_for_serverless: {e}")
            raise e

    @classmethod
    def initializeMetrics(cls, spark: SparkSession):
        try:
            spark.sparkContext._jvm.org.apache.spark.sql.MetricsCollector.initializeMetrics(
                spark._jsparkSession
            )
            cls.jvm_accessible = True
        except:
            if is_serverless:
                # making it falsely true for serverless case
                cls.jvm_accessible = True
                logging.info(
                    f"Failed to initialize MetricsCollector, Spark context is not available, but still making cls.jvm_accessible = {cls.jvm_accessible}"
                )
            else:
                logging.info(
                    "Failed to initialize MetricsCollector. Spark context is not available"
                )

    # We don't have positional arguments in python code base, thereby moving directly to keyword based argument.
    @classmethod
    def start(
        cls,
        spark: SparkSession,
        sessionForInteractive: str = "",
        pipelineId: str = "",
        config=None,
        **kwargs,
    ):
        global interimConfig
        interimConfig.maybeInitialize(spark, sessionForInteractive)

        # Define a function to convert object to a dictionary
        def should_include(key, value):
            # remove any unwanted objects from the config:
            to_ignore = ["spark", "prophecy_spark", "jvm", "secret_manager", "prophecy_project_config"]
            return key not in to_ignore and not isinstance(value, SparkSession)

        def to_dict_trampoline(obj):
            from collections import deque

            stack = deque()
            processed = {}
            result = None

            # Start with the initial object
            stack.append((obj, None, None))

            while stack:
                current_obj, parent_obj, key_in_parent = stack.pop()
                obj_id = id(current_obj)

                if obj_id in processed:
                    value = processed[obj_id]
                    if parent_obj is not None:
                        if isinstance(parent_obj, dict):
                            parent_obj[key_in_parent] = value
                        elif isinstance(parent_obj, list):
                            parent_obj.append(value)  # Append to list
                    else:
                        result = value
                    continue

                if isinstance(current_obj, (list, tuple)):
                    # Process list or tuple
                    new_list = []
                    processed[obj_id] = new_list

                    if parent_obj is not None:
                        if isinstance(parent_obj, dict):
                            parent_obj[key_in_parent] = new_list
                        elif isinstance(parent_obj, list):
                            parent_obj.append(new_list)  # Append to list
                    else:
                        result = new_list

                    # Add items to the stack
                    for item in reversed(current_obj):
                        stack.append(
                            (item, new_list, None)
                        )  # Use None since we append to list
                elif isinstance(current_obj, dict):
                    # Process dict
                    new_dict = {}
                    processed[obj_id] = new_dict

                    if parent_obj is not None:
                        if isinstance(parent_obj, dict):
                            parent_obj[key_in_parent] = new_dict
                        elif isinstance(parent_obj, list):
                            parent_obj.append(new_dict)
                    else:
                        result = new_dict

                    for key, value in current_obj.items():
                        if should_include(key, value):
                            stack.append((value, new_dict, key))
                elif hasattr(current_obj, "__dict__"):
                    # Process object's __dict__
                    new_dict = {}
                    processed[obj_id] = new_dict

                    if parent_obj is not None:
                        if isinstance(parent_obj, dict):
                            parent_obj[key_in_parent] = new_dict
                        elif isinstance(parent_obj, list):
                            parent_obj.append(new_dict)
                    else:
                        result = new_dict

                    for key, value in current_obj.__dict__.items():
                        if should_include(key, value):
                            stack.append((value, new_dict, key))
                elif hasattr(current_obj, "__slots__"):
                    # Process object's __slots__
                    new_dict = {}
                    processed[obj_id] = new_dict

                    if parent_obj is not None:
                        if isinstance(parent_obj, dict):
                            parent_obj[key_in_parent] = new_dict
                        elif isinstance(parent_obj, list):
                            parent_obj.append(new_dict)
                    else:
                        result = new_dict

                    for slot in current_obj.__slots__:
                        value = getattr(current_obj, slot)
                        if should_include(slot, value):
                            stack.append((value, new_dict, slot))
                elif type(current_obj) is datetime:
                    # Convert datetime to string
                    if current_obj.tzinfo is None:
                        processed[obj_id] = current_obj.strftime("%d-%m-%YT%H:%M:%SZ")
                    else:
                        processed[obj_id] = current_obj.strftime("%d-%m-%YT%H:%M:%SZ%z")
                    if parent_obj is not None:
                        if isinstance(parent_obj, dict):
                            parent_obj[key_in_parent] = processed[obj_id]
                        elif isinstance(parent_obj, list):
                            parent_obj.append(processed[obj_id])
                    else:
                        result = processed[obj_id]
                elif type(current_obj) is date:
                    # Convert date to string
                    processed[obj_id] = current_obj.strftime("%d-%m-%Y")
                    if parent_obj is not None:
                        if isinstance(parent_obj, dict):
                            parent_obj[key_in_parent] = processed[obj_id]
                        elif isinstance(parent_obj, list):
                            parent_obj.append(processed[obj_id])
                    else:
                        result = processed[obj_id]
                else:
                    # Leaf node
                    processed[obj_id] = current_obj
                    if parent_obj is not None:
                        if isinstance(parent_obj, dict):
                            parent_obj[key_in_parent] = current_obj
                        elif isinstance(parent_obj, list):
                            parent_obj.append(current_obj)  # Append to list
                    else:
                        result = current_obj

            return result

        for key, value in kwargs.items():
            ProphecyDebugger.log(
                None, f"Unused argument passed -- key: {key}, value: {value}"
            )

        if isBlank(sessionForInteractive):
            pipeline_wheel_path = ProphecyDebugger.find_pipeline_wheel(
                pipeline_uri=pipelineId
            )
            if pipeline_wheel_path is not None:
                spark.conf.set("spark.prophecy.pipeline.package", pipeline_wheel_path)
        # if isBlank(sessionForInteractive):  # when running as job
        #     # if not set by the user, try to set it automatically
        #     if not spark.conf.get("spark.prophecy.packages", None):
        #         wheels = ProphecyDebugger.wheels_in_path()
        #         str1 = ",".join(wheels)
        #         spark.conf.set("spark.prophecy.packages", str1)
        #         ProphecyDebugger.log(spark, "wheels " + str1)

        pipeline_config = None
        if config is not None:
            pipeline_config = json.dumps(config, default=to_dict_trampoline, indent=4)

        if not is_serverless and cls.jvm_accessible:
            if config is not None:
                try:
                    spark.sparkContext._jvm.org.apache.spark.sql.MetricsCollector.start(
                        spark._jsparkSession,
                        pipelineId,
                        sessionForInteractive,
                        pipeline_config,
                    )
                except Exception as ex:
                    print("Exception while starting metrics collector: ", ex)
                    raise ex
            else:
                spark.sparkContext._jvm.org.apache.spark.sql.MetricsCollector.start(
                    spark._jsparkSession, pipelineId, sessionForInteractive
                )
        else:
            logging.info("Running pipeline without metrics")

        if is_serverless:
            cls._handle_start_for_serverless(
                spark, sessionForInteractive, pipelineId, pipeline_config
            )

    @classmethod
    def end(
        cls,
        spark: SparkSession,
        status: str = PipelineStatus.SUCCEEDED,
        should_offload: bool = False,
    ):
        if not is_serverless and cls.jvm_accessible:
            spark.sparkContext._jvm.org.apache.spark.sql.MetricsCollector.end(
                spark._jsparkSession
            )
        else:
            logging.info("Finished pipeline without metrics")
        cls._handle_end_for_serverless(spark, status, should_offload)
        global interimConfig
        interimConfig.clear()

    # Use this like MetricsCollector.instrument(args)(pipeline_func_which_takes_spark)
    # Another variation could be annotation based, but going with this right now.
    @classmethod
    def instrument(
        cls,
        spark: SparkSession,
        sessionForInteractive: str = "",
        pipelineId: str = "",
        config=None,
        **kwargs,
    ):
        cls.initializeMetrics(spark)

        def wrapper(f):

            if cls.jvm_accessible:

                state = TaskState.LAUNCHING
                startTime = currentTimeString()
                try:
                    MetricsCollector.start(
                        spark, sessionForInteractive, pipelineId, config, **kwargs
                    )
                    state = TaskState.RUNNING
                    sendPipelineProgressEvent(
                        spark, sessionForInteractive, pipelineId, state, startTime
                    )
                    try:
                        monkey_patch_print()
                        ret = f(spark)

                        # if there are active streams, wait for them to finish
                        if len(spark.streams.active) > 0:
                            spark.streams.resetTerminated()
                            spark.streams.awaitAnyTermination()

                        return ret
                    # Base exception covers all bases like keyboard interrupt, generator exit and system exit
                    # It is safe to capture it, since we raise it again anyway
                    except BaseException as e:
                        state = TaskState.FAILED
                        endTime = currentTimeString()
                        etype = type(e).__name__
                        emsg = str(e)
                        etrace = traceback.format_exc()

                        if isinstance(e, CapturedException):
                            py4j_error = process_captured_exception(e)
                            sendPipelineProgressEvent(
                                spark,
                                sessionForInteractive,
                                pipelineId,
                                state,
                                startTime,
                                endTime,
                                py4j_error,
                            )
                            if not is_serverless:
                                # Triggers job completion event at the end
                                spark.sparkContext._jvm.org.apache.spark.sql.MetricsCollector.setPythonFailedStatus(
                                    spark._jsparkSession,
                                    etype,
                                    emsg,
                                    etrace,
                                    py4j_error,
                                )
                        elif isinstance(e, Py4JJavaError):
                            sendPipelineProgressEvent(
                                spark,
                                sessionForInteractive,
                                pipelineId,
                                state,
                                startTime,
                                endTime,
                                e.java_exception,
                            )
                            if not is_serverless:
                                # Triggers job completion event at the end
                                spark.sparkContext._jvm.org.apache.spark.sql.MetricsCollector.setPythonFailedStatus(
                                    spark._jsparkSession,
                                    etype,
                                    emsg,
                                    etrace,
                                    e.java_exception,
                                )
                        else:
                            # Python exception. Need not be transferred to JVM
                            send_pipeline_progress_event_on_python_exception(
                                spark,
                                sessionForInteractive,
                                pipelineId,
                                state,
                                startTime,
                                endTime,
                                e,
                            )
                            if not is_serverless:
                                # Triggers job completion event at the end
                                spark.sparkContext._jvm.org.apache.spark.sql.MetricsCollector.setPythonFailedStatus(
                                    spark._jsparkSession, etype, emsg, etrace
                                )
                        raise
                finally:
                    try:
                        if state != TaskState.FAILED:
                            state = TaskState.FINISHED
                            endTime = currentTimeString()
                            sendPipelineProgressEvent(
                                spark,
                                sessionForInteractive,
                                pipelineId,
                                state,
                                startTime,
                                endTime,
                            )
                        revert_monkey_patching()
                        MetricsCollector.end(
                            spark, task_state_to_pipeline_status(state), True
                        )
                    except Exception as exc:
                        if (
                            "(org.apache.spark.SparkSQLException) [OPERATION_CANCELED]"
                            in str(exc)
                        ):
                            raise exc
                        else:
                            logging.error(f"Finally block threw exception: {exc}")

            else:
                ret = f(spark)

                # if there are active streams, wait for them to finish
                if len(spark.streams.active) > 0:
                    spark.streams.resetTerminated()
                    spark.streams.awaitAnyTermination()

                return ret

        return wrapper

    @classmethod
    def withSparkOptimisationsDisabled(cls, fn):
        def wrapper(spark):
            try:
                disabledOpt = spark.conf.get("spark.sql.optimizer.excludedRules")
            except:
                disabledOpt = None
            try:
                aqe = spark.conf.get("spark.sql.adaptive.enabled")
            except:
                aqe = None
            if not is_serverless:
                spark.conf.set(
                    "spark.sql.optimizer.excludedRules",
                    spark.sparkContext._jvm.org.apache.spark.sql.ProphecySparkSession.getAllExcludesRules(),
                )
            spark.conf.set("spark.sql.adaptive.enabled", "false")
            try:
                fn(spark)
            finally:
                if disabledOpt:
                    spark.conf.set("spark.sql.optimizer.excludedRules", disabledOpt)
                else:
                    spark.conf.unset("spark.sql.optimizer.excludedRules")
                if aqe:
                    spark.conf.set("spark.sql.adaptive.enabled", aqe)
                else:
                    spark.conf.unset("spark.sql.adaptive.enabled")

        return wrapper

    @classmethod
    def offload_interims(cls, spark: SparkSession, key: str, payload: str):
        if not is_serverless and cls.jvm_accessible:
            try:
                spark.sparkContext._jvm.org.apache.spark.sql.MetricsCollector.offloadInterims(
                    spark._jsparkSession, key, payload
                )
            except Exception as e:
                logging.error(f"Exception while offloading interim for key {key}: {e}")
        else:
            try:
                store = MetricsCollector.get_inmemory_store(spark)
                if store:
                    store.update_selective_interims(key, payload)
            except Exception as e:
                logging.error(
                    f"[Serverless] Exception while offloading interim for key {key}: {e}"
                )


def collectMetrics(
    spark: SparkSession,
    df: DataFrame,
    subgraph: str,
    component: str,
    port: str,
    numRows: int = 40,
    run_id: Optional[str] = None,
    config=None,
) -> DataFrame:
    global interimConfig
    interimConfig.maybeInitialize(spark)
    pdf = ProphecyDataFrame(df, spark)
    conf_str = None
    if config is not None:
        conf_str = json.dumps(config.to_dict(), default=str)

    return pdf.interim(
        subgraph,
        component,
        port,
        "dummy",
        numRows,
        interimConfig.interimOutput,
        detailedStats=False,
        run_id=run_id,
        config=conf_str,
    )


def createEventSendingListener(
    spark: SparkSession, execution_url: str, session: str, scheduled: bool
):
    spark.sparkContext._jvm.org.apache.spark.sql.MetricsCollector.addSparkListener(
        spark._jsparkSession, execution_url, session, scheduled
    )


def postDataToSplunk(props: dict, payload):
    import gzip
    import requests
    from requests import HTTPError
    from requests.adapters import HTTPAdapter
    from urllib3 import Retry

    with requests.Session() as session:
        adapter = HTTPAdapter(
            max_retries=Retry(
                total=int(props.get("maxRetries", 4)),
                backoff_factor=float(props.get("backoffFactor", 1)),
                status_forcelist=[429, 500, 502, 503, 504],
            )
        )
        session.mount("http://", adapter)
        session.headers.update(
            {
                "Authorization": "Splunk " + props["token"],
                "Content-Encoding": "gzip",
                "BatchId": props.get("batchId", None),
            }
        )
        res = session.post(props["url"], gzip.compress(bytes(payload, encoding="utf8")))
        print(
            f"IN SESSION URL={props['url']} res.status_code = {res.status_code} res={res.text}"
        )
        if res.status_code != 200 and props.get("stopOnFailure", False):
            raise HTTPError(res.reason)


def splunkHECForEachWriter(props: dict):
    def wrapper(batchDF: DataFrame, batchId: int):
        max_load: Optional[int] = props.get("maxPayload")
        # Take 90% of the payload limit and convert KB into Bytes
        max_load = int(0.9 * 1024 * int(max_load)) if max_load else None
        props.update({"batchId": str(batchId)})

        def f(iterableDF):
            payload, prevsize = "", 0

            for row in iterableDF:
                if max_load and prevsize + len(row) >= max_load:
                    print(f"buffer hit at size {prevsize}")
                    postDataToSplunk(props, payload)
                    payload, prevsize = "", 0
                else:
                    payload += '{"event":' + row + "}"
                    prevsize += len(row) + 10  # 10 bytes is for padding

            if payload:
                print(f"last payload with size {prevsize}")
                postDataToSplunk(props, payload)

        batchDF.toJSON().foreachPartition(f)

    return wrapper


def find_first_index(sequence, condition):
    return next((i for i, x in enumerate(sequence) if condition(x)), -1)


def find_last_index(sequence, condition):
    return next((i for i, x in reversed(list(enumerate(sequence))) if condition(x)), -1)


def currentTimeString() -> str:
    return str(int(time.time() * 1000))


def extract_hierarchical_gem_name(stack, current_frame, function) -> str:
    stack_function_names = [f.function for f in stack]
    start_index = find_first_index(stack_function_names, lambda x: x == "inner_wrapper")
    end_index = find_last_index(stack_function_names, lambda x: x == "pipeline")
    sliced_stack = stack_function_names[start_index + 1 : end_index]
    stack_without_wrapper_nesting = [s for s in sliced_stack if s != "inner_wrapper"]
    stack_without_wrapper_nesting.reverse()

    frame = current_frame.f_back
    class_name = None

    # Check if 'self' or 'cls' is in the local variables of the caller's frame
    if "self" in frame.f_locals:
        class_name = frame.f_locals["self"].__class__.__name__
    elif "cls" in frame.f_locals:
        class_name = frame.f_locals["cls"].__name__

    if class_name:
        full_stack = stack_without_wrapper_nesting + [class_name, function.__name__]
        stack_with_class = [
            s for s in full_stack if s not in ("execute", "apply", "__run__")
        ]
        return ".".join(stack_with_class)

    if len(stack) > 1:
        caller_frame = stack[1].frame
        caller_self = caller_frame.f_locals.get("self", None)
        if caller_self is not None:
            caller_class_name = caller_self.__class__.__name__
            full_stack = stack_without_wrapper_nesting + [
                caller_class_name,
                function.__name__,
            ]
            stack_with_class = [
                s for s in full_stack if s not in ("execute", "apply", "__run__")
            ]
            return ".".join(stack_with_class)

    return ".".join(stack_without_wrapper_nesting + [function.__name__])


# Add support for stdout in pipeline progress
def sendPipelineProgressEvent(
    spark: SparkSession,
    userSession: str,
    pipelineId: str,
    state: str,
    startTime: str,
    endTime: str = "",
    exception: Optional[Any] = None,
):
    if is_serverless:
        logging.info(f"Calling python impl sendPipelineProgressEvent2")
        sendPipelineProgressEvent2(
            spark, userSession, pipelineId, state, startTime, endTime, exception
        )
    else:
        if exception:
            spark.sparkContext._jvm.org.apache.spark.sql.ProphecySparkSession.sendPipelineProgressEvent(
                spark._jsparkSession,
                userSession,
                pipelineId,
                state,
                startTime,
                endTime,
                exception,
            )
        else:
            spark.sparkContext._jvm.org.apache.spark.sql.ProphecySparkSession.sendPipelineProgressEvent(
                spark._jsparkSession, userSession, pipelineId, state, startTime, endTime
            )


def send_pipeline_progress_event_on_python_exception(
    spark: SparkSession,
    userSession: str,
    pipelineId: str,
    state: str,
    startTime: str,
    endTime: str,
    exception: BaseException,
):
    serializable_exception = SerializableException.from_exception(exception)
    if is_serverless:
        sendPipelineProgressEvent3(
            spark,
            userSession,
            pipelineId,
            state,
            startTime,
            endTime,
            serializable_exception.exception_type,
            serializable_exception.msg,
            serializable_exception.cause_msg,
            serializable_exception.stack_trace,
        )
    else:
        spark.sparkContext._jvm.org.apache.spark.sql.ProphecySparkSession.sendPipelineProgressEvent(
            spark._jsparkSession,
            userSession,
            pipelineId,
            state,
            startTime,
            endTime,
            serializable_exception.exception_type,
            serializable_exception.msg,
            serializable_exception.cause_msg,
            serializable_exception.stack_trace,
        )


def send_gem_progress_event_on_python_exception(
    spark: SparkSession,
    userSession: str,
    process_id: str,
    state: str,
    startTime: str,
    endTime: str,
    stdout: str,
    stderr: str,
    exception: BaseException,
):
    serializable_exception = SerializableException.from_exception(exception)
    if is_serverless:
        sendGemProgressEvent3(
            spark,
            userSession,
            process_id,
            state,
            startTime,
            endTime,
            stdout,
            stderr,
            serializable_exception.exception_type,
            serializable_exception.msg,
            serializable_exception.cause_msg,
            serializable_exception.stack_trace,
        )
        MetricsCollector.update_gem_progress(
            spark=spark,
            process_id=process_id,
            state=state,
            startTime=startTime,
            endTime=endTime,
            stdout=stdout,
            stderr=stderr,
            exception=exception,
        )
    else:
        spark.sparkContext._jvm.org.apache.spark.sql.ProphecySparkSession.sendGemProgressEvent(
            spark._jsparkSession,
            userSession,
            process_id,
            state,
            startTime,
            endTime,
            stdout,
            stderr,
            serializable_exception.exception_type,
            serializable_exception.msg,
            serializable_exception.cause_msg,
            serializable_exception.stack_trace,
        )


def sendGemProgressEvent(
    spark: SparkSession,
    userSession: str,
    process_id: str,
    state: str,
    startTime: str,
    endTime: str = "",
    stdout: str = "[]",
    stderr: str = "[]",
    exception: Optional[Any] = None,
):
    if is_serverless:
        sendGemProgressEvent2(
            spark,
            userSession,
            process_id,
            state,
            startTime,
            endTime,
            stdout,
            stderr,
            exception,
        )
        MetricsCollector.update_gem_progress(
            spark=spark,
            process_id=process_id,
            state=state,
            startTime=startTime,
            endTime=endTime,
            stdout=stdout,
            stderr=stderr,
            exception=exception,
        )
    else:
        if exception:
            spark.sparkContext._jvm.org.apache.spark.sql.ProphecySparkSession.sendGemProgressEvent(
                spark._jsparkSession,
                userSession,
                process_id,
                state,
                startTime,
                endTime,
                stdout,
                stderr,
                exception,
            )
        else:
            spark.sparkContext._jvm.org.apache.spark.sql.ProphecySparkSession.sendGemProgressEvent(
                spark._jsparkSession,
                userSession,
                process_id,
                state,
                startTime,
                endTime,
                stdout,
                stderr,
            )


def get_process_from_gem(spark: SparkSession, gemName: str, userSession: str) -> str:
    if is_serverless:
        logging.info(f"Using python get_process_from_gem")
        return get_process_from_gem2(spark, gemName, userSession)
    else:
        return spark.sparkContext._jvm.org.apache.spark.sql.ProphecySparkSession.getProcessFromGem(
            spark._jsparkSession, gemName, userSession
        )


def instrument(function):
    def inner_wrapper(*args, **kwargs):
        if is_serverless:
            if hasattr(args[0], "_spark"):
                spark = args[0]
            else:
                spark = args[1]
        else:
            if isinstance(args[0], SPARK_SESSION_TYPES):
                spark = args[0]
            else:
                spark = args[1]

        global interimConfig
        if interimConfig.isInitialized:
            user_session = interimConfig.session
        else:
            user_session = ""
        start_time = currentTimeString()
        state = TaskState.LAUNCHING
        gem_name = extract_hierarchical_gem_name(
            inspect.stack(), inspect.currentframe(), function
        )
        process_id = get_process_from_gem(spark, gem_name, user_session)
        sendGemProgressEvent(spark, user_session, process_id, state, start_time)
        with capture_streams() as data_manager:
            try:
                state = TaskState.RUNNING
                sendGemProgressEvent(spark, user_session, process_id, state, start_time)
                result = function(*args, **kwargs)
                return result
            # Handle PythonException separately, probably similar to normal exception below?
            except CapturedException as captured_error:
                state = TaskState.FAILED
                captured_stdout, captured_stderr = data_manager.drain_thread_output()
                py4j_error = process_captured_exception(captured_error)
                sendGemProgressEvent(
                    spark,
                    user_session,
                    process_id,
                    state,
                    start_time,
                    currentTimeString(),
                    captured_stdout,
                    captured_stderr,
                    py4j_error,
                )
                raise captured_error
            except Py4JJavaError as py4j_error:
                state = TaskState.FAILED
                captured_stdout, captured_stderr = data_manager.drain_thread_output()
                sendGemProgressEvent(
                    spark,
                    user_session,
                    process_id,
                    state,
                    start_time,
                    currentTimeString(),
                    captured_stdout,
                    captured_stderr,
                    py4j_error.java_exception,
                )
                raise py4j_error
            except Exception as exception:
                state = TaskState.FAILED
                captured_stdout, captured_stderr = data_manager.drain_thread_output()
                send_gem_progress_event_on_python_exception(
                    spark,
                    user_session,
                    process_id,
                    state,
                    start_time,
                    currentTimeString(),
                    captured_stdout,
                    captured_stderr,
                    exception,
                )
                raise exception
            except BaseException as base_exception:
                state = TaskState.FAILED
                captured_stdout, captured_stderr = data_manager.drain_thread_output()
                send_gem_progress_event_on_python_exception(
                    spark,
                    user_session,
                    process_id,
                    state,
                    start_time,
                    currentTimeString(),
                    captured_stdout,
                    captured_stderr,
                    base_exception,
                )
                raise base_exception
            finally:
                if state != TaskState.FAILED:
                    state = TaskState.FINISHED
                    captured_stdout, captured_stderr = (
                        data_manager.drain_thread_output()
                    )
                    sendGemProgressEvent(
                        spark,
                        user_session,
                        process_id,
                        state,
                        start_time,
                        currentTimeString(),
                        captured_stdout,
                        captured_stderr,
                    )

    return inner_wrapper


class SecretManager:

    def __init__(self, spark: SparkSession):
        self.jvm = spark.sparkContext._jvm
        self.spark = spark
        if is_serverless:
            from prophecy.utils.secrets import ProphecySecrets

            self.secret_manager = ProphecySecrets
        else:
            self.secret_manager = self.jvm.io.prophecy.libs.secrets.ProphecySecrets

    def get(self, scope: str, key: str, provider: str):
        return self.secret_manager.get(scope, key, provider)
