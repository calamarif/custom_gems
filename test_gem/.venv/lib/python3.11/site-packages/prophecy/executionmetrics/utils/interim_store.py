import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from threading import Lock
from pyspark.sql import SparkSession

from prophecy.executionmetrics.schemas.external import InterimKey

# Set up logging
logger = logging.getLogger(__name__)


@dataclass
class RDDInterimKey:
    """Represents an RDD interim key with associated interim key"""

    interim_key: InterimKey
    # MOCK: Additional fields would be defined based on actual implementation

    def get_prophecy_interim_event_key(self) -> str:
        """Get the prophecy interim event key"""
        # MOCK: Placeholder implementation
        return str(self.interim_key)


@dataclass
class InterimStat:
    """Represents interim statistics"""

    counter_accumulator: Any  # MOCK: Placeholder for actual accumulator type
    # MOCK: Additional fields would be defined based on actual implementation


@dataclass
class InterimSummary:
    """Summary of all interim states"""

    appended: List[InterimKey]
    planned: List[InterimKey]
    executed: List[InterimKey]
    found: List[InterimKey]


class StatsAccumulator:
    """Stats accumulator for Spark context"""

    # MOCK: Placeholder implementation for StatsAccumulator
    def __init__(self):
        self.value = 0


class InterimStore:
    """
    Manages interim storage for Spark operations.
    Tracks appended, planned, executed, and found interims.
    """

    # Class-level storage for InterimStore instances per SparkSession
    _map_of_spark_session_to_interim_store: Dict[SparkSession, "InterimStore"] = {}
    _lock = Lock()

    def __init__(
        self,
        spark_session: SparkSession,
        appended_interims: Optional[Dict[InterimKey, bool]] = None,
        planned_interims: Optional[Dict[InterimKey, bool]] = None,
        executed_interims: Optional[Dict[InterimKey, List[RDDInterimKey]]] = None,
        found_interims: Optional[Dict[RDDInterimKey, InterimStat]] = None,
    ):
        """
        Initialize InterimStore with Spark session and tracking dictionaries.

        Args:
            spark_session: The Spark session
            appended_interims: Dictionary tracking appended interims
            planned_interims: Dictionary tracking planned interims
            executed_interims: Dictionary mapping interim keys to RDD interim keys
            found_interims: Dictionary mapping RDD interim keys to their stats
        """
        self.spark_session = spark_session
        self.appended_interims = appended_interims or {}
        self.planned_interims = planned_interims or {}
        self.executed_interims = executed_interims or {}
        self.found_interims = found_interims or {}

        # Log session ID
        session_id = self._get_unique_session_id(spark_session)
        logger.info(f"Session Id {session_id}")

    @classmethod
    def get_or_create(cls, spark: SparkSession) -> "InterimStore":
        """
        Get or create an InterimStore for the given SparkSession.

        Args:
            spark: The SparkSession

        Returns:
            InterimStore instance for the session
        """
        with cls._lock:
            if spark not in cls._map_of_spark_session_to_interim_store:
                cls._map_of_spark_session_to_interim_store[spark] = cls(spark)
            return cls._map_of_spark_session_to_interim_store[spark]

    @classmethod
    def reset(cls, spark: SparkSession) -> None:
        """
        Reset the InterimStore for the given SparkSession.

        Args:
            spark: The SparkSession to reset
        """
        with cls._lock:
            if spark in cls._map_of_spark_session_to_interim_store:
                interim_store = cls._map_of_spark_session_to_interim_store.pop(spark)
                interim_store._reset_internal()

    @classmethod
    def stats_accumulator(cls, spark: SparkSession) -> StatsAccumulator:
        """
        Create and register a stats accumulator for the Spark context.

        Args:
            spark: The SparkSession

        Returns:
            StatsAccumulator instance
        """
        stats_accumulator = StatsAccumulator()
        # MOCK: In actual implementation, this would register with spark.sparkContext
        # spark.sparkContext.register(stats_accumulator)
        return stats_accumulator

    @classmethod
    def close(cls, spark: SparkSession) -> None:
        """
        Close and cleanup resources for the given SparkSession.

        Args:
            spark: The SparkSession to close
        """
        cls.reset(spark)
        # MOCK: RunConfigStore.close(spark) equivalent would be called here
        # RunConfigStore.close(spark)

    def interim_summary(self) -> InterimSummary:
        """
        Get a summary of all interim states.

        Returns:
            InterimSummary containing lists of all interim keys by state
        """
        return InterimSummary(
            appended=list(self.appended_interims.keys()),
            planned=list(self.planned_interims.keys()),
            executed=list(self.executed_interims.keys()),
            found=[key.interim_key for key in self.found_interims.keys()],
        )

    def found_interim(self, key: RDDInterimKey) -> Optional[InterimStat]:
        """
        Get the InterimStat for a given RDDInterimKey if it exists.

        Args:
            key: The RDDInterimKey to look up

        Returns:
            InterimStat if found, None otherwise
        """
        return self.found_interims.get(key)

    def reset(self) -> None:
        """Public reset method that delegates to internal reset."""
        self._reset_internal()

    def _reset_internal(self) -> None:
        """
        Internal reset method that logs current state and clears data.
        """
        # Log current state before reset
        logger.info(
            f"appended interims ({len(self.appended_interims)}: {self.appended_interims}"
        )
        logger.info(
            f"planned interims ({len(self.planned_interims)}: {self.planned_interims}"
        )
        logger.info(
            f"executed interims ({len(self.executed_interims)}: {self.executed_interims}"
        )
        logger.info(
            f"found interims ({len(self.found_interims)}: {self.found_interims}"
        )

    def update_planned_interims(self, interim_key: InterimKey) -> None:
        """
        Add an interim key to the planned interims tracking.

        Args:
            interim_key: The InterimKey to mark as planned
        """
        self.planned_interims[interim_key] = True
        logger.info(f"Adding to planned interims: {interim_key}")

    def update_appended_interims(self, interim_key: InterimKey) -> None:
        """
        Add an interim key to the appended interims tracking.

        Args:
            interim_key: The InterimKey to mark as appended
        """
        self.appended_interims[interim_key] = True
        logger.info(f"Adding to appended interims: {interim_key}")

    def update_executed_interims(
        self, interim_key: InterimKey, key: RDDInterimKey
    ) -> None:
        """
        Add an RDDInterimKey to the executed interims for a given InterimKey.

        Args:
            interim_key: The InterimKey that was executed
            key: The RDDInterimKey associated with the execution
        """
        if interim_key not in self.executed_interims:
            self.executed_interims[interim_key] = []
        self.executed_interims[interim_key].append(key)
        logger.info(f"Adding to executed interims: {interim_key} with rdd: {key}")

    def update(self, key: RDDInterimKey, stat: InterimStat) -> None:
        """
        Update the found interims with a new RDDInterimKey and its statistics.

        Args:
            key: The RDDInterimKey
            stat: The InterimStat associated with the key
        """
        self.found_interims[key] = stat
        logger.info(f"Adding to found interims: {key.interim_key} with rdd: {key}")

    def get_max_rows_received_for_key(self, rdd_interim_key: RDDInterimKey) -> int:
        """
        Get the maximum number of rows received for a given RDDInterimKey.

        Args:
            rdd_interim_key: The RDDInterimKey to check

        Returns:
            Maximum row count across all matching keys
        """
        prophecy_key = rdd_interim_key.get_prophecy_interim_event_key()
        matching_stats = [
            stat.counter_accumulator.value
            for key, stat in self.found_interims.items()
            if key.get_prophecy_interim_event_key() == prophecy_key
        ]

        if not matching_stats:
            return 0
        return max(matching_stats)

    def execute(self, key: RDDInterimKey, func: callable) -> None:
        """
        Execute a function on the InterimStat for a given key if it exists.

        Args:
            key: The RDDInterimKey to look up
            func: Function to execute with the InterimStat
        """
        stat = self.found_interims.get(key)
        if stat:
            func(stat)
        else:
            logger.error(
                f"Interim key `{key}` not found. InterimExecBase's doExecute didn't run for this stage"
            )

    def __str__(self) -> str:
        """String representation of the InterimStore."""
        return f"Interim Store(SparkSession = {self.spark_session}, interimKeys = {list(self.found_interims.keys())})"

    @staticmethod
    def _get_unique_session_id(spark_session: SparkSession) -> str:
        """
        Get unique session ID for the Spark session.

        Args:
            spark_session: The SparkSession

        Returns:
            Unique session ID string
        """
        # MOCK: MetricsCollector.getUniqueSessionId equivalent
        # In actual implementation, this would get the real session ID
        return str(id(spark_session))


# Module-level convenience functions to match Scala object methods
def get_interim_store(spark: SparkSession) -> InterimStore:
    """Get or create an InterimStore for the given SparkSession."""
    return InterimStore.get_or_create(spark)


def reset_interim_store(spark: SparkSession) -> None:
    """Reset the InterimStore for the given SparkSession."""
    InterimStore.reset(spark)


def close_interim_store(spark: SparkSession) -> None:
    """Close and cleanup resources for the given SparkSession."""
    InterimStore.close(spark)


def create_stats_accumulator(spark: SparkSession) -> StatsAccumulator:
    """Create and register a stats accumulator for the Spark context."""
    return InterimStore.stats_accumulator(spark)
