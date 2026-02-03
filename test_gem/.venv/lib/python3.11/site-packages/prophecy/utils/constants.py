# Constants


class ProphecySparkConstants:
    GROUP_ID_KEY = "spark.jobGroup.id"
    SPARK_CONF_PIPELINE_URI_KEY = "spark.prophecy.metadata.pipeline.uri"
    SPARK_CONF_FABRIC_ID_KEY = "spark.prophecy.metadata.fabric.id"
    SPARK_CONF_SERVICE_URL_KEY = "spark.prophecy.execution.service.url"
    SPARK_CONF_RUN_TYPE_KEY = "spark.prophecy.metadata.is.interactive.run"
    SPARK_CONF_JOB_URI_KEY = "spark.prophecy.metadata.job.uri"
    SPARK_CONF_USER_ID_KEY = "spark.prophecy.metadata.user.id"
    SPARK_CONF_PIPELINE_PROCESSES_KEY = "spark.prophecy.metadata.pipeline.processes"
    SPARK_CONF_PIPELINE_CODE_KEY = "spark.prophecy.metadata.pipeline.code"
    SPARK_CONF_PIPELINE_PACKAGE_KEY = "spark.prophecy.pipeline.package"
    SPARK_DELTA_PATH_PREFIX = "spark.prophecy.delta.path.prefix"
    SPARK_CONF_PIPELINE_UUID_KEY = "spark.prophecy.metadata.pipeline.uuid"
    SPARK_CONF_EXPECTED_INTERIMS = "spark.prophecy.metadata.expected-interims"
    SPARK_CONF_JOB_BRANCH = "spark.prophecy.metadata.job.branch"
    SPARK_CONF_URL = "spark.prophecy.metadata.url"
    SPARK_CONF_OFFLOAD_FOR_TEST_ENABLED = (
        "spark.prophecy.execution.offload-for-test.enabled"
    )
    SPARK_CONF_TEST_LISTENER_ENABLED = "spark.prophecy.execution.test.listener.enabled"
    SPARK_CONF_UNIT_TEST_ENVIRONMENT = "spark.prophecy.unit.test.environment"
    SPARK_CONF_PROJECT_ID = "spark.prophecy.project.id"
    SPARK_CONF_PACKAGES_PATH = "spark.prophecy.packages.path"
    SPARK_CONF_STORAGE_FORMAT = "spark.prophecy.execution.metrics.storage.format"
    SPARK_CONF_DISABLE_OFFLOAD = "spark.prophecy.execution.metrics.disabled"
    SPARK_CONF_PIPELINE_METRICS_TABLE = (
        "spark.prophecy.execution.metrics.pipeline-metrics.table"
    )
    SPARK_CONF_COMPONENT_METRICS_TABLE = (
        "spark.prophecy.execution.metrics.component-metrics.table"
    )
    SPARK_CONF_INTERIMS_TABLE = "spark.prophecy.execution.metrics.interims.table"
    SPARK_CONF_COLLECT_BASIC_STATS = "spark.prophecy.collect.basic.stats"
    SPARK_CONF_TASKS = "spark.prophecy.tasks"
    SPARK_CONF_PIPELINE_SUBMISSION_TIME = "spark.prophecy.pipeline.submission-time"
    SPARK_CONF_TABLE_PARTITIONING_DISABLED = (
        "spark.prophecy.table.partitioning.disabled"
    )
    SPARK_CONF_HASHICORP_NAMESPACE = "spark.prophecy.execution.hashicorp.namespace"
