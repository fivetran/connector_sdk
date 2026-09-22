import io
import threading
import time
import unittest
from unittest.mock import patch

from fivetran_connector_sdk import ByteStream, FileUpload, Operations
from fivetran_connector_sdk.protos import common_pb2, connector_sdk_pb2


class TestFileUpload(unittest.TestCase):

    def setUp(self):
        from fivetran_connector_sdk.operations import Operations, _OperationStream
        # Reset the operation stream for each test
        Operations.operation_stream = _OperationStream()
        Operations._file_path_override_logged = False

    def tearDown(self):
        from fivetran_connector_sdk.constants import TABLES
        from fivetran_connector_sdk.operations import TABLES_COLUMNS_TYPES
        TABLES.clear()
        TABLES_COLUMNS_TYPES.clear()

    def _drain_all(self):
        """Consumes the operation_stream until mark_done(), flattening list-vs-single responses."""
        responses = []
        for response in Operations.operation_stream:
            if isinstance(response, list):
                responses.extend(response)
            else:
                responses.append(response)
        return responses

    def test_upsert_with_file_raises_for_empty_file_path(self):
        with self.assertRaises(ValueError):
            Operations.upsert("files", {"id": 1}, file=FileUpload("", io.BytesIO(b"x")))
        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_upsert_with_file_raises_for_non_string_file_path(self):
        with self.assertRaises(ValueError):
            Operations.upsert("files", {"id": 1}, file=FileUpload(123, io.BytesIO(b"x")))
        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_upsert_with_file_raises_for_whitespace_only_path(self):
        with self.assertRaises(ValueError) as context:
            Operations.upsert("files", {"id": 1}, file=FileUpload("   ", io.BytesIO(b"x")))
        self.assertIn("whitespace", str(context.exception).lower())
        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_upsert_with_file_trims_whitespace_from_path(self):
        """Test that leading and trailing whitespace is trimmed from file paths."""
        def producer():
            Operations.upsert("files", {"id": 1}, file=FileUpload("  invoices/report.pdf  ", io.BytesIO(b"data")))
            Operations.operation_stream.mark_done()

        threading.Thread(target=producer).start()
        responses = self._drain_all()

        # Find the structured record with the file path
        record = next(
            r.structured_records.structured_records[0]
            for r in responses
            if r.WhichOneof("operation") == "structured_records"
        )

        # Verify the path was trimmed
        self.assertEqual(record.data["_fivetran_file_path"].string, "invoices/report.pdf")

    def test_upsert_with_file_raises_for_null_byte_in_path(self):
        with self.assertRaises(ValueError) as context:
            Operations.upsert("files", {"id": 1}, file=FileUpload("invoices/\x00/001.pdf", io.BytesIO(b"x")))
        self.assertIn("null byte", str(context.exception).lower())
        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_upsert_with_file_raises_for_trailing_slash(self):
        with self.assertRaises(ValueError) as context:
            Operations.upsert("files", {"id": 1}, file=FileUpload("invoices/", io.BytesIO(b"x")))
        self.assertIn("cannot end with a slash", str(context.exception).lower())
        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_upsert_with_file_raises_for_double_slash(self):
        with self.assertRaises(ValueError) as context:
            Operations.upsert("files", {"id": 1}, file=FileUpload("invoices//001.pdf", io.BytesIO(b"x")))
        self.assertIn("double slash", str(context.exception).lower())
        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_upsert_with_file_raises_for_root_slash_only(self):
        with self.assertRaises(ValueError) as context:
            Operations.upsert("files", {"id": 1}, file=FileUpload("/", io.BytesIO(b"x")))
        self.assertIn("cannot end with a slash", str(context.exception).lower())
        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_upsert_with_file_accepts_unicode_paths(self):
        def producer():
            Operations.upsert("files", {"id": 1}, file=FileUpload("数据/文件.csv", io.BytesIO(b"data")))
            Operations.upsert("files", {"id": 2}, file=FileUpload("invoices/Q1 Report (Final).pdf", io.BytesIO(b"data")))
            Operations.operation_stream.mark_done()

        threading.Thread(target=producer).start()
        responses = self._drain_all()
        # Should succeed without errors
        self.assertTrue(any(r.WhichOneof("operation") == "unstructured_record" for r in responses))

    def test_upsert_with_file_raises_if_stream_lacks_read(self):
        with self.assertRaises(ValueError):
            Operations.upsert("files", {"id": 1}, file=FileUpload("a.pdf", object()))
        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_upsert_with_file_raises_for_negative_expected_bytes(self):
        with self.assertRaises(ValueError):
            Operations.upsert("files", {"id": 1}, file=FileUpload("a.pdf", io.BytesIO(b"x"), -1))
        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_upsert_with_file_raises_for_non_int_expected_bytes(self):
        with self.assertRaises(ValueError):
            Operations.upsert("files", {"id": 1}, file=FileUpload("a.pdf", io.BytesIO(b"x"), "1"))
        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_upsert_with_file_raises_for_expected_bytes_exceeding_java_long_max(self):
        from fivetran_connector_sdk.constants import JAVA_LONG_MAX_VALUE
        with self.assertRaises(ValueError) as context:
            Operations.upsert("files", {"id": 1}, file=FileUpload("a.pdf", io.BytesIO(b"x"), JAVA_LONG_MAX_VALUE + 1))
        self.assertIn("exceeds maximum allowed size", str(context.exception))
        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_upsert_with_file_accepts_expected_bytes_at_java_long_max(self):
        from fivetran_connector_sdk.constants import JAVA_LONG_MAX_VALUE
        def producer():
            Operations.upsert("files", {"id": 1}, file=FileUpload("a.pdf", io.BytesIO(b"x"), JAVA_LONG_MAX_VALUE))
            Operations.operation_stream.mark_done()

        threading.Thread(target=producer).start()
        responses = self._drain_all()
        # Should succeed without errors
        chunks = [r.unstructured_record for r in responses if r.WhichOneof("operation") == "unstructured_record"]
        self.assertTrue(len(chunks) > 0)
        self.assertTrue(all(c.expected_bytes == JAVA_LONG_MAX_VALUE for c in chunks))

    def test_upsert_with_file_raises_for_empty_table_name_before_file_validation(self):
        # Verify table name validation happens before file validation (no queue pollution)
        with self.assertRaises(ValueError) as context:
            Operations.upsert("", {"id": 1}, file=FileUpload("a.pdf", io.BytesIO(b"x")))
        self.assertIn("table name", str(context.exception).lower())
        # Ensure no file chunks were added to the queue
        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_delete_rejects_file_parameter(self):
        # delete() should not accept file parameter - Python will reject it
        with self.assertRaises(TypeError) as context:
            Operations.delete("table", {"id": 1}, file=FileUpload("a.pdf", io.BytesIO(b"x")))
        self.assertIn("unexpected keyword argument", str(context.exception))
        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_truncate_rejects_file_parameter(self):
        # truncate() should not accept file parameter - Python will reject it
        with self.assertRaises(TypeError) as context:
            Operations.truncate("table", file=FileUpload("a.pdf", io.BytesIO(b"x")))
        self.assertIn("unexpected keyword argument", str(context.exception))
        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_upsert_with_file_emits_chunks_then_record_in_order(self):
        def producer():
            Operations.upsert(
                "files",
                {"id": 1},
                file=FileUpload("invoices/1.pdf", io.BytesIO(b"hello world"), expected_bytes=11),
            )
            Operations.operation_stream.mark_done()

        threading.Thread(target=producer).start()
        responses = self._drain_all()
        cases = [r.WhichOneof("operation") for r in responses]

        # all unstructured_record responses come before the structured_records response, in order,
        # and the final chunk is marked is_last.
        first_record_index = cases.index("structured_records")
        self.assertTrue(all(c == "unstructured_record" for c in cases[:first_record_index]))
        chunks = [r.unstructured_record for r in responses[:first_record_index]]
        self.assertTrue(chunks[-1].is_last)
        self.assertFalse(any(c.is_last for c in chunks[:-1]))
        self.assertEqual(b"".join(c.chunk_data for c in chunks), b"hello world")
        self.assertTrue(all(c.file_path == "invoices/1.pdf" for c in chunks))
        self.assertTrue(all(c.expected_bytes == 11 for c in chunks))
        self.assertTrue(all(c.HasField("expected_bytes") for c in chunks))

        record = responses[first_record_index].structured_records.structured_records[0]
        self.assertEqual(record.data["_fivetran_file_path"].string, "invoices/1.pdf")

    def test_update_with_file_emits_chunks_then_update_record(self):
        def producer():
            Operations.update(
                "files",
                {"id": 1, "name": "updated"},
                file=FileUpload("updates/1.pdf", io.BytesIO(b"updated")),
            )
            Operations.operation_stream.mark_done()

        threading.Thread(target=producer).start()
        responses = self._drain_all()
        record = next(r.structured_records.structured_records[0] for r in responses if r.WhichOneof("operation") == "structured_records")

        self.assertEqual([r.WhichOneof("operation") for r in responses], ["unstructured_record", "unstructured_record", "structured_records"])
        self.assertEqual(record.type, common_pb2.UPDATE)
        self.assertEqual(record.data["_fivetran_file_path"].string, "updates/1.pdf")

    def test_upsert_with_file_overwrites_customer_supplied_file_path_column(self):
        with patch("fivetran_connector_sdk.operations.print_library_log") as mock_log:
            def producer():
                Operations.upsert(
                    "files",
                    {"id": 1, "_fivetran_file_path": "customer/typo/path.pdf"},
                    file=FileUpload("correct/path.pdf", io.BytesIO(b"x")),
                )
                Operations.operation_stream.mark_done()

            threading.Thread(target=producer).start()
            responses = self._drain_all()
        record = next(r.structured_records.structured_records[0] for r in responses if r.WhichOneof("operation") == "structured_records")
        self.assertEqual(record.data["_fivetran_file_path"].string, "correct/path.pdf")
        mock_log.assert_called_once()

    def test_upsert_with_empty_file_emits_single_empty_last_chunk(self):
        def producer():
            Operations.upsert("files", {"id": 1}, file=FileUpload("empty.txt", io.BytesIO(b"")))
            Operations.operation_stream.mark_done()

        threading.Thread(target=producer).start()
        responses = self._drain_all()
        chunks = [r.unstructured_record for r in responses if r.WhichOneof("operation") == "unstructured_record"]
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_data, b"")
        self.assertTrue(chunks[0].is_last)

    def test_upsert_with_file_raises_if_read_returns_none_before_emitting_upload_state(self):
        class NoneStream:
            def read(self, size=-1):
                return None

        with self.assertRaises(TypeError):
            Operations.upsert("files", {"id": 1}, file=FileUpload("none.txt", NoneStream()))

        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_upsert_with_file_raises_if_read_returns_string_before_emitting_upload_state(self):
        class StringStream:
            def read(self, size=-1):
                return ""

        with self.assertRaises(TypeError):
            Operations.upsert("files", {"id": 1}, file=FileUpload("string.txt", StringStream()))

        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_upsert_with_file_propagates_read_exception_before_emitting_upload_state(self):
        class BrokenReadError(Exception):
            pass

        read_exception = BrokenReadError("read failed")

        class BrokenStream:
            def read(self, size=-1):
                raise read_exception

        with self.assertRaises(BrokenReadError) as context:
            Operations.upsert("files", {"id": 1}, file=FileUpload("broken.bin", BrokenStream()))

        self.assertIs(context.exception, read_exception)
        self.assertTrue(Operations.operation_stream._queue.empty())

    def test_upsert_with_file_preserves_bytes_across_multiple_chunks(self):
        from fivetran_connector_sdk.constants import FILE_UPLOAD_CHUNK_SIZE_BYTES

        contents = b"a" * FILE_UPLOAD_CHUNK_SIZE_BYTES + b"tail"

        def producer():
            Operations.upsert("files", {"id": 1}, file=FileUpload("large.bin", io.BytesIO(contents)))
            Operations.operation_stream.mark_done()

        threading.Thread(target=producer).start()
        responses = self._drain_all()
        chunks = [r.unstructured_record for r in responses if r.WhichOneof("operation") == "unstructured_record"]

        self.assertEqual(len(chunks), 3)
        self.assertFalse(chunks[0].is_last)
        self.assertFalse(chunks[1].is_last)
        self.assertTrue(chunks[2].is_last)
        self.assertEqual(chunks[2].chunk_data, b"")
        self.assertEqual(b"".join(c.chunk_data for c in chunks), contents)

    def test_file_upload_and_byte_stream_are_exported(self):
        self.assertIs(FileUpload, __import__("fivetran_connector_sdk").FileUpload)
        self.assertIs(ByteStream, __import__("fivetran_connector_sdk").ByteStream)

    def test_upsert_with_file_read_timeout_raises_without_closing_stream(self):
        release_read = threading.Event()

        class BlockingStream:
            closed = False

            def read(self, size=-1):
                release_read.wait(timeout=5)
                return b""

        stream = BlockingStream()

        try:
            with patch("fivetran_connector_sdk.file_upload.FILE_UPLOAD_READ_TIMEOUT_SEC", 0.01):
                with self.assertRaises(TimeoutError):
                    Operations.upsert("files", {"id": 1}, file=FileUpload("a.pdf", stream))
        finally:
            release_read.set()

        self.assertFalse(stream.closed)

        def producer():
            Operations.upsert("files", {"id": 2}, file=FileUpload("b.pdf", io.BytesIO(b"ok")))
            Operations.operation_stream.mark_done()

        threading.Thread(target=producer).start()
        responses = self._drain_all()
        cases = [r.WhichOneof("operation") for r in responses]
        self.assertEqual(cases, ["unstructured_record", "unstructured_record", "structured_records"])

    def test_concurrent_operations_cannot_interleave_with_active_file_upload(self):
        upload_started = threading.Event()
        release_upload = threading.Event()
        responses = []

        class BlockingStream:
            """Yields one byte, then blocks until release_upload is set, to hold the lock open
            long enough for a concurrent checkpoint() call to attempt (and be forced to wait)."""

            def __init__(self):
                self._served_first = False

            def read(self, size=-1):
                if not self._served_first:
                    self._served_first = True
                    upload_started.set()
                    return b"a"
                release_upload.wait(timeout=5)
                return b""

        def consumer():
            for response in Operations.operation_stream:
                if isinstance(response, list):
                    responses.extend(response)
                    if any(r.WhichOneof("operation") == "checkpoint" for r in response):
                        Operations.operation_stream.unblock()
                else:
                    responses.append(response)

        def upload_producer():
            Operations.upsert("files", {"id": 1}, file=FileUpload("a.pdf", BlockingStream()))

        def checkpoint_producer():
            upload_started.wait(timeout=5)
            Operations.checkpoint({"cursor": 1})

        def mark_done_producer():
            upload_started.wait(timeout=5)
            Operations.operation_stream.mark_done()

        def normal_record_producers():
            upload_started.wait(timeout=5)
            Operations.upsert("files", {"id": 2})
            Operations.update("files", {"id": 3})
            Operations.delete("files", {"id": 4})

        consumer_thread = threading.Thread(target=consumer)
        upload_thread = threading.Thread(target=upload_producer)
        checkpoint_thread = threading.Thread(target=checkpoint_producer)
        normal_record_thread = threading.Thread(target=normal_record_producers)
        mark_done_thread = threading.Thread(target=mark_done_producer)

        consumer_thread.start()
        upload_thread.start()
        upload_thread.join(timeout=0.2)
        checkpoint_thread.start()
        normal_record_thread.start()
        mark_done_thread.start()

        time.sleep(0.2)
        release_upload.set()

        upload_thread.join(timeout=5)
        checkpoint_thread.join(timeout=5)
        normal_record_thread.join(timeout=5)
        mark_done_thread.join(timeout=5)
        consumer_thread.join(timeout=5)

        flattened_operations = []
        for response in responses:
            if response.WhichOneof("operation") == "structured_records":
                flattened_operations.extend(response.structured_records.structured_records)
            else:
                flattened_operations.append(response)

        metadata_index = next(
            i for i, operation in enumerate(flattened_operations)
            if (
                isinstance(operation, connector_sdk_pb2.StructuredRecord)
                and operation.data["_fivetran_file_path"].string == "a.pdf"
            )
        )
        preceding_cases = [
            "record" if isinstance(operation, connector_sdk_pb2.StructuredRecord) else operation.WhichOneof("operation")
            for operation in flattened_operations[:metadata_index]
        ]
        self.assertEqual(preceding_cases, ["unstructured_record", "unstructured_record"])


class TestFileUploadStreamIntegration(unittest.TestCase):

    def setUp(self):
        from fivetran_connector_sdk.operations import Operations, _OperationStream
        # Reset the operation stream for each test
        Operations.operation_stream = _OperationStream()

    def test_add_file_upload_flushes_buffer_before_chunks_then_metadata_record(self):
        stream = Operations.operation_stream
        chunk1 = connector_sdk_pb2.UnstructuredRecord(
            storage_name="files", file_path="a.pdf", chunk_data=b"a", is_last=False
        )
        chunk2 = connector_sdk_pb2.UnstructuredRecord(
            storage_name="files", file_path="a.pdf", chunk_data=b"", is_last=True
        )
        metadata_record = connector_sdk_pb2.StructuredRecord(table_name="files", type=common_pb2.RecordType.UPSERT, data={})

        def produce():
            Operations.upsert("test_table", {"id": 1})
            stream.add_file_upload([ chunk1, chunk2], metadata_record)
            stream.mark_done()

        thread = threading.Thread(target=produce)
        thread.start()

        response1 = next(stream)
        response2 = next(stream)
        response3 = next(stream)
        thread.join(timeout=5)

        self.assertEqual(len(response1[0].structured_records.structured_records), 1)
        self.assertEqual(response1[1].unstructured_record, chunk1)
        self.assertEqual(response2[0].unstructured_record, chunk2)
        self.assertEqual(response3.structured_records.structured_records[0], metadata_record)

    def test_add_file_upload_blocks_normal_producers_until_metadata_record_is_queued(self):
        stream = Operations.operation_stream
        upload_started = threading.Event()
        release_upload = threading.Event()
        normal_producer_done = threading.Event()
        chunk = connector_sdk_pb2.UnstructuredRecord(
            storage_name="files", file_path="a.pdf", chunk_data=b"a", is_last=False
        )
        final_chunk = connector_sdk_pb2.UnstructuredRecord(
            storage_name="files", file_path="a.pdf", chunk_data=b"", is_last=True
        )
        metadata_record = connector_sdk_pb2.StructuredRecord(table_name="files", type=common_pb2.RecordType.UPSERT, data={})
        normal_record = connector_sdk_pb2.StructuredRecord(table_name="normal", type=common_pb2.RecordType.UPSERT, data={})

        def chunks():
            yield chunk
            upload_started.set()
            release_upload.wait(timeout=5)
            yield final_chunk

        upload_thread = threading.Thread(target=lambda: stream.add_file_upload(chunks(), metadata_record))
        normal_thread = threading.Thread(
            target=lambda: (stream.add_record(normal_record), normal_producer_done.set())
        )

        upload_thread.start()
        upload_started.wait(timeout=5)
        normal_thread.start()
        self.assertFalse(normal_producer_done.wait(timeout=0.2))

        release_upload.set()
        upload_thread.join(timeout=5)
        normal_thread.join(timeout=5)
        stream.mark_done()

        queued_operations = []
        while not stream._queue.empty():
            queued_operations.append(stream._queue.get())

        self.assertEqual(queued_operations[:-1], [chunk, final_chunk, metadata_record, normal_record])
        self.assertIs(queued_operations[-1], stream._sentinel)


if __name__ == "__main__":
    unittest.main()
