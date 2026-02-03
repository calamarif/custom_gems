import atexit
import json
import sys
import threading
import time
import uuid
from contextlib import contextmanager

original_print = print
original_stderr_write = sys.stderr.write


def custom_print(*args, **kwargs):
    """Custom print function that captures stdout output if needed."""
    content = ' '.join(map(str, args)) + kwargs.get('end', '\n')
    stream_manager = StreamManager()
    if hasattr(stream_manager.local_data, 'function_id'):
        stream_manager.capture_stdout(content)
    # Call the original print function to display output
    original_print(*args, **kwargs)


def custom_stderr_write(data):
    """Custom write function that captures stderr output if needed."""
    stream_manager = StreamManager()
    if hasattr(stream_manager.local_data, 'function_id'):
        stream_manager.capture_stderr(data)
    # Use the original stderr write function for actual output
    original_stderr_write(data)


def monkey_patch_print():
    import builtins
    builtins.print = custom_print
    sys.stderr.write = custom_stderr_write


def revert_monkey_patching():
    import builtins
    builtins.print = original_print
    sys.stderr.write = original_stderr_write


class StreamManager:
    """Singleton class to manage output capturing and thread-specific data."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(StreamManager, cls).__new__(
                        cls, *args, **kwargs
                    )
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initializes the thread-specific data storage."""
        self._thread_data = {}
        self.local_data = threading.local()

        # Register the cleanup function to be called when the program exits
        atexit.register(self.cleanup)

    def initialize_thread_data(self):
        """Initializes data for the current thread."""
        thread_id = threading.get_ident()
        if thread_id not in self._thread_data:
            self._thread_data[thread_id] = {
                "stdout_capture": [],
                "stderr_capture": [],
                "function_id": None,
            }

    def capture_stdout(self, content):
        """Stores captured stdout for the current thread."""
        thread_id = threading.get_ident()
        if thread_id in self._thread_data:
            function_id = self._thread_data[thread_id]["function_id"]
            self._thread_data[thread_id]["stdout_capture"].append(
                TimestampedContent(content, thread_id, function_id)
            )

    def capture_stderr(self, content):
        """Stores captured stderr for the current thread."""
        thread_id = threading.get_ident()
        if thread_id in self._thread_data:
            function_id = self._thread_data[thread_id]["function_id"]
            self._thread_data[thread_id]["stderr_capture"].append(
                TimestampedContent(content, thread_id, function_id)
            )

    def drain_thread_output(self):
        """Drains captured output for the current thread and returns it as JSON strings."""
        thread_id = threading.get_ident()
        if thread_id in self._thread_data:
            stdout_capture = [
                o.to_dict() for o in self._thread_data[thread_id]["stdout_capture"]
            ]
            stderr_capture = [
                o.to_dict() for o in self._thread_data[thread_id]["stderr_capture"]
            ]
            self._thread_data[thread_id]["stdout_capture"] = []
            self._thread_data[thread_id]["stderr_capture"] = []
            return json.dumps(stdout_capture), json.dumps(stderr_capture)
        return "[]", "[]"

    def clear_thread_data(self):
        """Clears data for the current thread."""
        thread_id = threading.get_ident()
        if thread_id in self._thread_data:
            del self._thread_data[thread_id]

    def cleanup(self):
        """Clears all data"""
        self.clear_all_data()

    def clear_all_data(self):
        """Clears data for all threads."""
        self._thread_data.clear()


@contextmanager
def capture_streams():
    """Context manager to capture stdout and stderr writes for a thread-local function."""
    stream_manager = StreamManager()
    function_id = uuid.uuid4().hex

    stream_manager.initialize_thread_data()
    thread_id = threading.get_ident()
    stream_manager._thread_data[thread_id]["function_id"] = function_id
    stream_manager.local_data.function_id = function_id

    try:
        yield stream_manager
    finally:
        stream_manager.clear_thread_data()
        if hasattr(stream_manager.local_data, "function_id"):
            del stream_manager.local_data.function_id


class TimestampedContent:
    def __init__(self, content: str, thread_id: int, function_id: str):
        self.content = content
        self.thread_id = thread_id
        self.function_id = function_id
        self.time = int(time.time() * 1000)

    def to_dict(self) -> dict:
        return {"content": self.content, "time": self.time}
