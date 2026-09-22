import queue
import threading

from dataclasses import dataclass
from typing import Iterator, Optional, Protocol, runtime_checkable

from fivetran_connector_sdk.constants import (
    FILE_UPLOAD_CHUNK_SIZE_BYTES,
    FILE_UPLOAD_READ_TIMEOUT_SEC,
    JAVA_LONG_MAX_VALUE,
)
from fivetran_connector_sdk.protos import connector_sdk_pb2


@runtime_checkable
class ByteStream(Protocol):
    """A binary read-only stream."""

    def read(self, size: int = -1) -> bytes: ...


@dataclass(frozen=True)
class FileUpload:
    path: str
    stream: ByteStream
    expected_bytes: Optional[int] = None

    def __post_init__(self):
        """Normalize the path by trimming whitespace on creation."""
        if isinstance(self.path, str):
            trimmed_path = self.path.strip()
            # Use object.__setattr__ since the dataclass is frozen
            object.__setattr__(self, 'path', trimmed_path)


# Short timeout for worker thread shutdown since it's a daemon thread
_WORKER_SHUTDOWN_TIMEOUT_SEC = 0.1


def _validate_path(path: str) -> None:
    """Validate the file path for a file upload.

    Args:
        path: The file path to validate.

    Raises:
        ValueError: If the path is invalid.
    """
    if not isinstance(path, str):
        raise ValueError(
            f"Invalid file path: expected a string, but received {type(path).__name__}."
        )
    
    if not path:
        raise ValueError(
            "Invalid file path: path cannot be empty or contain only whitespace."
        )
    if "\x00" in path:
        raise ValueError(
            "Invalid file path: path contains null bytes (\\x00), which are not allowed. "
            "Remove any null characters from the file path."
        )
    if path.endswith("/"):
        raise ValueError(
            f"Invalid file path '{path}': path cannot end with a slash. "
            f"Did you mean '{path.rstrip('/')}'? "
            "File paths must point to a file, not a directory."
        )
    if "//" in path:
        raise ValueError(
            f"Invalid file path '{path}': path contains double slashes (//). "
            "Use single slashes to separate path segments."
        )


def _validate_expected_bytes(expected_bytes: Optional[int]) -> None:
    """Validate the expected_bytes parameter for a file upload.

    Args:
        expected_bytes: The expected number of bytes in the file.

    Raises:
        ValueError: If expected_bytes is invalid.
    """
    if expected_bytes is None:
        return

    if type(expected_bytes) is not int:
        raise ValueError(
            f"Invalid expected_bytes: expected an integer, but received {type(expected_bytes).__name__}. "
            "If you know the file size, provide it as an integer (in bytes)."
        )
    if expected_bytes < 0:
        raise ValueError(
            f"Invalid expected_bytes: {expected_bytes} is negative. "
            "File size must be zero or a positive integer. "
            "If the file size is unknown, omit the expected_bytes parameter."
        )
    if expected_bytes > JAVA_LONG_MAX_VALUE:
        raise ValueError(
            f"Invalid expected_bytes: {expected_bytes} exceeds maximum allowed size of {JAVA_LONG_MAX_VALUE:,} bytes "
            f"({JAVA_LONG_MAX_VALUE / (1024**3):.2f} GB). "
            "If your file is larger than this limit, please contact Fivetran support."
        )


def validate_file_upload_if_present(file_upload: Optional[FileUpload]) -> None:
    """Validate FileUpload path, stream interface, and expected_bytes.
    
    Raises ValueError for invalid fields.
    """
    if file_upload is None:
        return

    _validate_path(file_upload.path)
    if not isinstance(file_upload.stream, ByteStream):
        raise ValueError(
            f"Invalid stream: object of type '{type(file_upload.stream).__name__}' does not have a read() method. "
            "The stream must be a file-like object with a read(size) method, such as an open file handle or io.BytesIO."
        )
    _validate_expected_bytes(file_upload.expected_bytes)


def file_upload_chunks(table: str, file_upload: FileUpload) -> Iterator[connector_sdk_pb2.UnstructuredRecord]:
    """Generator that reads from stream and yields UnstructuredRecord chunks.
    
    Reads in chunks up to FILE_UPLOAD_CHUNK_SIZE_BYTES with per-read timeout.
    Always emits a final chunk with empty data and is_last=True after reading all data.
    """
    with _FileUploadReader(file_upload.stream, FILE_UPLOAD_READ_TIMEOUT_SEC) as reader:
        while True:
            data = _read_next_chunk(reader, FILE_UPLOAD_CHUNK_SIZE_BYTES)
            is_last = len(data) == 0
            
            chunk_args = {
                "storage_name": table,
                "file_path": file_upload.path,
                "chunk_data": data,
                "is_last": is_last,
            }
            if file_upload.expected_bytes is not None:
                chunk_args["expected_bytes"] = file_upload.expected_bytes

            yield connector_sdk_pb2.UnstructuredRecord(**chunk_args)
            
            if is_last:
                break


def _read_next_chunk(reader, chunk_size: int) -> bytes:
    """Read up to chunk_size bytes from reader, handling partial reads.
    
    Loops until buffer is full or EOF. Returns empty bytes if stream exhausted.
    """
    buffer = bytearray()
    while len(buffer) < chunk_size:
        piece = reader.read(chunk_size - len(buffer))
        if not isinstance(piece, bytes):
            raise TypeError(
                f"Invalid stream.read() return type: expected bytes, but received {type(piece).__name__}. "
                "The stream's read() method must return bytes, not strings or other types. "
                "If reading from a file, ensure it's opened in binary mode with 'rb'."
            )
        if not piece:
            break
        buffer.extend(piece)
    return bytes(buffer)


class _FileUploadReader:
    """Wraps a ByteStream with per-read timeout enforcement using a worker thread.
    
    Prevents connector hangs when file upload streams block indefinitely.
    """
    _SENTINEL = object()

    def __init__(self, stream: ByteStream, timeout_sec: int):
        self._stream = stream
        self._timeout_sec = timeout_sec
        self._read_size_requests = queue.Queue()
        self._read_results = queue.Queue()
        self._closed = False
        # The worker may remain blocked inside caller-owned stream code after a timeout.
        # Daemonizing it avoids blocking process exit; the SDK does not forcibly close the stream.
        self._worker = threading.Thread(
            target=self._read_worker,
            name="connector-sdk-file-read",
            daemon=True,
        )

    def __enter__(self):
        self._worker.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._closed = True
        self._read_size_requests.put(self._SENTINEL)
        self._worker.join(timeout=_WORKER_SHUTDOWN_TIMEOUT_SEC)

    def read(self, size: int) -> bytes:
        if self._closed:
            raise RuntimeError(
                "Cannot read from file upload stream: the reader has been closed. "
                "This is an internal error. Please contact Fivetran support if this issue persists."
            )

        self._read_size_requests.put(size)
        try:
            result = self._read_results.get(timeout=self._timeout_sec)
        except queue.Empty:
            self._closed = True
            raise TimeoutError(
                f"File upload timed out: stream.read() did not return within {self._timeout_sec} seconds."
            )

        if isinstance(result, _ReadException):
            raise result.exception
        return result

    def _read_worker(self):
        while True:
            size = self._read_size_requests.get()
            if size is self._SENTINEL:
                return
            try:
                self._read_results.put(self._stream.read(size))
            except Exception as exception:
                self._read_results.put(_ReadException(exception))


@dataclass(frozen=True)
class _ReadException:
    exception: BaseException
