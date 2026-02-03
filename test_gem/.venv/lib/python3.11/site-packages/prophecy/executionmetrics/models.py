class RunType:
    """Run type enum."""

    INTERACTIVE = "Interactive"
    SCHEDULED = "Scheduled"
    ADHOC = "Adhoc"


class PipelineStatus:
    """Pipeline status enum."""

    STARTED = "STARTED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @staticmethod
    def is_status_higher_than_previous_status(current: str, new: str) -> bool:
        """Check if new status is higher priority than current."""
        priority = {
            PipelineStatus.STARTED: 1,
            PipelineStatus.RUNNING: 2,
            PipelineStatus.SUCCEEDED: 3,
            PipelineStatus.FAILED: 4,
            PipelineStatus.CANCELLED: 4,
        }
        return priority.get(new, 0) > priority.get(current, 0)
