import json
import unittest
import threading

from fivetran_connector_sdk.operations import Operations
from fivetran_connector_sdk.protos import connector_sdk_pb2, common_pb2


class TestOperationStreamIntegration(unittest.TestCase):
    def setUp(self):
        from fivetran_connector_sdk.operations import Operations, _OperationStream

        # Reset the operation stream for each test
        Operations.operation_stream = _OperationStream()

    def test_batch_upsert_flush_on_batch_record_limit(self):

        def generate_upserts():
            for rec_num in range(105):
                Operations.upsert("test_table", {"id": rec_num, "name": f"test_{rec_num}"})
            Operations.operation_stream.mark_done()

        thread = threading.Thread(target=generate_upserts)
        thread.start()

        response1 = next(Operations.operation_stream)
        response2 = next(Operations.operation_stream)

        thread.join()
        self.assertEqual(len(response1.structured_records.structured_records), 100)
        self.assertEqual(len(response2.structured_records.structured_records), 5)

    def test_batch_upsert_flush_on_batch_size(self):

        def generate_upserts():
            for rec_num in range(80):
                Operations.upsert(
                    "test_table", {"id": rec_num, "name": f"test_{rec_num}", "data": "x" * 1950}
                )
            Operations.operation_stream.mark_done()

        thread = threading.Thread(target=generate_upserts)
        thread.start()

        response1 = next(Operations.operation_stream)
        response2 = next(Operations.operation_stream)
        thread.join()

        self.assertEqual(len(response1.structured_records.structured_records), 50)
        self.assertEqual(len(response2.structured_records.structured_records), 30)

    def test_batch_upsert_with_checkpoint(self):

        def generate_upserts_with_checkpoint():
            for rec_num in range(50):
                Operations.upsert("test_table", {"id": rec_num, "name": f"test_{rec_num}"})
            checkpoint = connector_sdk_pb2.Checkpoint(
                state_json=json.dumps({"cursor": "2024-01-01T00:00:00.00Z"})
            )
            Operations.operation_stream.add_checkpoint(checkpoint)

        thread = threading.Thread(target=generate_upserts_with_checkpoint)
        thread.start()

        response1 = next(Operations.operation_stream)
        # as consumer should unblock the queue after reading the response
        Operations.operation_stream.unblock()
        thread.join()

        self.assertEqual(len(response1[0].structured_records.structured_records), 50)
        self.assertEqual(
            response1[1].checkpoint.state_json, '{"cursor": "2024-01-01T00:00:00.00Z"}'
        )

    def test_multiple_batches_with_checkpoint(self):
        # creates 5 batches, checkpoints after 10 records.
        def generate_batches_with_checkpoint():
            for rec_num in range(1, 51):
                Operations.upsert("test_table", {"id": rec_num, "name": f"test_{rec_num}"})
                if rec_num % 10 == 0:
                    checkpoint = connector_sdk_pb2.Checkpoint(
                        state_json=json.dumps({"cursor": f"{rec_num}"})
                    )
                    Operations.operation_stream.add_checkpoint(checkpoint)

        thread = threading.Thread(target=generate_batches_with_checkpoint)
        thread.start()

        # assert that we get 5 responses, each with 10 records and checkpoint state
        for batch_num in range(1, 6):
            response = next(Operations.operation_stream)
            # as consumer should unblock the queue after reading the response
            Operations.operation_stream.unblock()
            self.assertEqual(len(response[0].structured_records.structured_records), 10)
            self.assertEqual(
                response[1].checkpoint.state_json, f'{{"cursor": "{batch_num * 10}"}}'
            )

        thread.join()

    def test_multiple_producer_with_checkpoint(self):
        def generate_producer_1_data():
            for rec_num in range(1, 26):
                Operations.upsert(
                    "test_table", {"id": rec_num, "name": f"producer1_test_{rec_num}"}
                )
                if rec_num % 5 == 0:
                    Operations.checkpoint({"cursor": f"producer1_{rec_num}"})

        def generate_producer_2_data():
            for rec_num in range(26, 51):
                Operations.upsert(
                    "test_table", {"id": rec_num, "name": f"producer2_test_{rec_num}"}
                )
                if rec_num % 5 == 0:
                    Operations.checkpoint({"cursor": f"producer2_{rec_num}"})

        thread1 = threading.Thread(target=generate_producer_1_data)
        thread2 = threading.Thread(target=generate_producer_2_data)
        thread1.start()
        thread2.start()

        total_record_count = 0
        checkpoint_count = 0

        for _ in range(10):  # We expect 10 checkpoint responses
            response = next(Operations.operation_stream)
            Operations.operation_stream.unblock()

            # Handle tuple response with records and checkpoint
            if isinstance(response, list):
                total_record_count += len(response[0].structured_records.structured_records)
                checkpoint_count += 1

        # Wait for threads to complete
        thread1.join()
        thread2.join()

        self.assertEqual(total_record_count, 50)
        self.assertEqual(checkpoint_count, 10)

    def test_different_record_type_operations(self):
        def generate_records():
            for rec_num in range(1, 51):
                Operations.upsert("test_table", {"id": rec_num, "name": f"test_{rec_num}"})
                if rec_num % 10 == 0:
                    Operations.update(
                        "test_table", {"id": rec_num, "name": f"updated_test_{rec_num}"}
                    )
                if rec_num % 20 == 0:
                    Operations.delete("test_table", {"id": rec_num})
            Operations.operation_stream.mark_done()

        thread = threading.Thread(target=generate_records)
        thread.start()

        response = next(Operations.operation_stream)
        # as a consumer unblock the queue
        Operations.operation_stream.unblock()
        thread.join()

        self.assertEqual(len(response.structured_records.structured_records), 57)
        # Check individual operation types
        upsert_count = sum(
            1
            for r in response.structured_records.structured_records
            if r.type == common_pb2.RecordType.UPSERT
        )
        update_count = sum(
            1
            for r in response.structured_records.structured_records
            if r.type == common_pb2.RecordType.UPDATE
        )
        delete_count = sum(
            1
            for r in response.structured_records.structured_records
            if r.type == common_pb2.RecordType.DELETE
        )
        self.assertEqual(upsert_count, 50)
        self.assertEqual(update_count, 5)
        self.assertEqual(delete_count, 2)

    def test_checkpoint_only_operation(self):
        state = {"cursor": "2024-01-01T00:00:00.00Z"}

        def generate_checkpoint_only():
            Operations.checkpoint({"cursor": "2024-01-01T00:00:00.00Z"})
            Operations.operation_stream.mark_done()

        thread = threading.Thread(target=generate_checkpoint_only)
        thread.start()

        response = next(Operations.operation_stream)
        # as consumer should unblock the queue after reading the response
        Operations.operation_stream.unblock()
        thread.join()

        self.assertTrue(hasattr(response[0], "checkpoint"))
        self.assertEqual(response[0].checkpoint.state_json, json.dumps(state))

    def test_ensure_single_checkpoint_processing(self):
        # Reset the operation stream to ensure clean state
        checkpoint_processed_order = []
        checkpoint_count = 5
        producer_count = 3
        all_checkpoints_processed = threading.Event()

        # Producer function that adds checkpoints from different threads
        def producer_thread(thread_id):
            for rec_num in range(checkpoint_count):
                state = {"producer": thread_id, "id": rec_num}
                Operations.checkpoint(state)

        # Consumer function that processes checkpoints
        def consumer_thread():
            received = 0
            expected_total = checkpoint_count * producer_count

            while received < expected_total:
                try:
                    response = next(Operations.operation_stream)
                    if isinstance(response, list):
                        for item in response:
                            if hasattr(item, "checkpoint"):
                                checkpoint_data = json.loads(item.checkpoint.state_json)
                                checkpoint_processed_order.append(checkpoint_data)
                                received += 1
                                # Unblock to allow next checkpoint
                                Operations.operation_stream.unblock()
                    elif hasattr(response, "checkpoint"):
                        checkpoint_data = json.loads(response.checkpoint.state_json)
                        checkpoint_processed_order.append(checkpoint_data)
                        received += 1
                        # Unblock to allow next checkpoint
                        Operations.operation_stream.unblock()
                except StopIteration:
                    break

            all_checkpoints_processed.set()

        # Start multiple producer threads
        producers = []
        for producer_num in range(producer_count):
            producer = threading.Thread(target=producer_thread, args=(producer_num,))
            producers.append(producer)
            producer.start()

        # Start consumer thread
        consumer = threading.Thread(target=consumer_thread)
        consumer.start()

        # Wait for all producers to finish
        for p in producers:
            p.join()

        # Mark the operation stream as done
        Operations.operation_stream.mark_done()

        # Wait for consumer to process all checkpoints
        all_checkpoints_processed.wait(timeout=5)
        consumer.join(timeout=1)

        # Verify we processed the expected number of checkpoints
        self.assertEqual(len(checkpoint_processed_order), checkpoint_count * producer_count)

        # For each producer, verify its checkpoints were processed in order
        for producer_id in range(producer_count):
            producer_checkpoints = [
                c for c in checkpoint_processed_order if c["producer"] == producer_id
            ]
            producer_ids = [c["id"] for c in producer_checkpoints]
            self.assertEqual(producer_ids, sorted(producer_ids))

    def test_empty_operation_stream(self):
        Operations.operation_stream.mark_done()
        with self.assertRaises(StopIteration):
            next(Operations.operation_stream)

    def test_multiple_mark_done_calls(self):
        def generate_mark_done():
            Operations.operation_stream.mark_done()
            Operations.operation_stream.mark_done()

        thread = threading.Thread(target=generate_mark_done)
        thread.start()

        with self.assertRaises(StopIteration):
            next(Operations.operation_stream)

        with self.assertRaises(StopIteration):
            next(Operations.operation_stream)

    def test_checkpoint_wait_timeout_raises(self):
        # If the consumer never calls unblock(), add() should time out instead of blocking forever.
        stream = Operations.operation_stream
        stream._checkpoint_flush_signal.wait = lambda timeout=None: False
        checkpoint = connector_sdk_pb2.Checkpoint(state_json="{}")
        with self.assertRaises(TimeoutError):
            stream.add_checkpoint(checkpoint)

    def test_stop_iteration_after_buffer_flush(self):
        """
        After flushing buffered records on mark_done(), subsequent next() should raise StopIteration.
        """

        def produce():
            for i in range(3):
                Operations.upsert("test_table", {"id": i, "name": f"item_{i}"})
            Operations.operation_stream.mark_done()

        producer = threading.Thread(target=produce)
        producer.start()

        # First next() returns the buffered batch
        response = next(Operations.operation_stream)
        producer.join()
        self.assertEqual(len(response.structured_records.structured_records), 3)

        # Following next() should indicate end-of-stream
        with self.assertRaises(StopIteration):
            next(Operations.operation_stream)

    def test_iter_returns_self(self):
        """Test that __iter__ returns the stream itself"""
        stream = Operations.operation_stream
        self.assertIs(iter(stream), stream)

    def test_checkpoint_with_empty_buffer(self):
        """Test checkpoint when buffer is empty"""

        def produce_checkpoint_with_empty_buffer():
            checkpoint = connector_sdk_pb2.Checkpoint(state_json=json.dumps({"empty": True}))
            Operations.operation_stream.add_checkpoint(checkpoint)
            Operations.operation_stream.mark_done()

        producer = threading.Thread(target=produce_checkpoint_with_empty_buffer)
        producer.start()

        response = next(Operations.operation_stream)
        Operations.operation_stream.unblock()
        producer.join()

        # Should only have checkpoint, no records
        self.assertTrue(isinstance(response, list))
        self.assertEqual(len(response), 1)
        self.assertTrue(hasattr(response[0], "checkpoint"))

    def test_exact_batch_limit_records(self):
        """Test when exactly MAX_RECORDS_IN_BATCH records are added"""

        def produce_exact_limit():
            for i in range(100):  # Exactly MAX_RECORDS_IN_BATCH
                Operations.upsert("test_table", {"id": i})
            Operations.operation_stream.mark_done()

        producer = threading.Thread(target=produce_exact_limit)
        producer.start()

        response = next(Operations.operation_stream)
        producer.join()

        self.assertEqual(len(response.structured_records.structured_records), 100)

        # Should raise StopIteration on next call
        with self.assertRaises(StopIteration):
            next(Operations.operation_stream)

    def test_flush_buffer_resets_counters(self):
        """Test that _flush_buffer properly resets internal counters"""

        def produce():
            for i in range(5):
                Operations.upsert("test_table", {"id": i})
            Operations.operation_stream.mark_done()

        producer = threading.Thread(target=produce)
        producer.start()

        next(Operations.operation_stream)
        producer.join()

        # After flushing, internal counters should be reset
        stream = Operations.operation_stream
        self.assertEqual(stream._buffer_record_count, 0)
        self.assertEqual(stream._buffer_size_bytes, 0)
        self.assertEqual(len(stream._buffer), 0)

    def test_sequential_batches_without_checkpoint(self):
        """Test multiple sequential batches without checkpoints"""

        def produce():
            # Produce 250 records (will create 3 batches: 100, 100, 50)
            for i in range(250):
                Operations.upsert("test_table", {"id": i})
            Operations.operation_stream.mark_done()

        producer = threading.Thread(target=produce)
        producer.start()

        batch1 = next(Operations.operation_stream)
        batch2 = next(Operations.operation_stream)
        batch3 = next(Operations.operation_stream)
        producer.join()

        self.assertEqual(len(batch1.structured_records.structured_records), 100)
        self.assertEqual(len(batch2.structured_records.structured_records), 100)
        self.assertEqual(len(batch3.structured_records.structured_records), 50)

        with self.assertRaises(StopIteration):
            next(Operations.operation_stream)

    def test_checkpoint_between_batches(self):
        """Test checkpoint that occurs between natural batch boundaries"""

        def produce():
            # 100 records (fills first batch)
            for i in range(100):
                Operations.upsert("test_table", {"id": i})
            # Checkpoint
            Operations.checkpoint({"cursor": "100"})
            # 50 more records
            for i in range(100, 150):
                Operations.upsert("test_table", {"id": i})
            Operations.operation_stream.mark_done()

        producer = threading.Thread(target=produce)
        producer.start()

        # First batch: 100 records (batch fills and flushes)
        response1 = next(Operations.operation_stream)

        # Second response: checkpoint (comes separately after batch flush)
        response2 = next(Operations.operation_stream)
        Operations.operation_stream.unblock()

        # Third batch: 50 records
        response3 = next(Operations.operation_stream)

        producer.join()

        # First response should be 100 records
        self.assertEqual(len(response1.structured_records.structured_records), 100)

        # Second response should be checkpoint (in a list)
        self.assertTrue(isinstance(response2, list))
        self.assertTrue(hasattr(response2[0], "checkpoint"))

        # Third response should be 50 records
        self.assertEqual(len(response3.structured_records.structured_records), 50)

    def test_flush_buffer_on_warning_with_buffered_records(self):
        """Test _flush_buffer_on_warning with buffered records"""

        def produce():
            # Add some records to buffer
            for i in range(5):
                Operations.upsert("test_table", {"id": i})
            # Add a warning
            Operations.warning("Test warning message")
            Operations.operation_stream.mark_done()

        producer = threading.Thread(target=produce)
        producer.start()

        response = next(Operations.operation_stream)
        producer.join()

        # Should return a list with records and warning
        self.assertTrue(isinstance(response, list))
        self.assertEqual(len(response), 2)

        # First item should be records
        self.assertTrue(hasattr(response[0], "structured_records"))
        self.assertEqual(len(response[0].structured_records.structured_records), 5)

        # Second item should be warning
        self.assertTrue(hasattr(response[1], "warning"))
        warning_payload = json.loads(response[1].warning.message)
        self.assertEqual(warning_payload["message"], "Test warning message")

    def test_flush_buffer_on_warning_with_empty_buffer(self):
        """Test _flush_buffer_on_warning with empty buffer"""

        def produce():
            # Add a warning without any buffered records
            Operations.warning("Empty buffer warning")
            Operations.operation_stream.mark_done()

        producer = threading.Thread(target=produce)
        producer.start()

        response = next(Operations.operation_stream)
        producer.join()

        # Should return a list with only warning (no records)
        self.assertTrue(isinstance(response, list))
        self.assertEqual(len(response), 1)

        # Should be warning
        self.assertTrue(hasattr(response[0], "warning"))
        warning_payload = json.loads(response[0].warning.message)
        self.assertEqual(warning_payload["message"], "Empty buffer warning")

    def test_flush_buffer_on_task_with_buffered_records(self):
        """Test _flush_buffer_on_task with buffered records"""

        def produce():
            # Add some records to buffer
            for i in range(10):
                Operations.upsert("test_table", {"id": i})
            # Add an error (task)
            Operations.error("Test error message", trace="Stack trace here")
            Operations.operation_stream.mark_done()

        producer = threading.Thread(target=produce)
        producer.start()

        response = next(Operations.operation_stream)
        producer.join()

        # Should return a list with records and task
        self.assertTrue(isinstance(response, list))
        self.assertEqual(len(response), 2)

        # First item should be records
        self.assertTrue(hasattr(response[0], "structured_records"))
        self.assertEqual(len(response[0].structured_records.structured_records), 10)

        # Second item should be task
        self.assertTrue(hasattr(response[1], "task"))
        task_payload = json.loads(response[1].task.message)
        self.assertEqual(task_payload["message"], "Test error message")
        self.assertEqual(task_payload["trace"], "Stack trace here")

    def test_flush_buffer_on_task_with_empty_buffer(self):
        """Test _flush_buffer_on_task with empty buffer"""

        def produce():
            # Add an error without any buffered records
            Operations.error("Empty buffer error")
            Operations.operation_stream.mark_done()

        producer = threading.Thread(target=produce)
        producer.start()

        response = next(Operations.operation_stream)
        producer.join()

        # Should return a list with only task (no records)
        self.assertTrue(isinstance(response, list))
        self.assertEqual(len(response), 1)

        # Should be task
        self.assertTrue(hasattr(response[0], "task"))
        task_payload = json.loads(response[0].task.message)
        self.assertEqual(task_payload["message"], "Empty buffer error")
        self.assertNotIn("trace", task_payload)

    def test_multiple_warnings_in_sequence(self):
        """Test multiple warnings in sequence"""

        def produce():
            Operations.warning("Warning 1")
            Operations.upsert("test_table", {"id": 1})
            Operations.warning("Warning 2")
            Operations.operation_stream.mark_done()

        producer = threading.Thread(target=produce)
        producer.start()

        # First response: warning 1 (no buffered records)
        response1 = next(Operations.operation_stream)

        # Second response: warning 2 with 1 buffered record
        response2 = next(Operations.operation_stream)

        producer.join()

        # First warning should have no records
        self.assertTrue(isinstance(response1, list))
        self.assertEqual(len(response1), 1)
        self.assertTrue(hasattr(response1[0], "warning"))

        # Second warning should have 1 record
        self.assertTrue(isinstance(response2, list))
        self.assertEqual(len(response2), 2)
        self.assertTrue(hasattr(response2[0], "structured_records"))
        self.assertEqual(len(response2[0].structured_records.structured_records), 1)
        self.assertTrue(hasattr(response2[1], "warning"))

    def test_multiple_errors_in_sequence(self):
        """Test multiple errors in sequence"""

        def produce():
            Operations.error("Error 1")
            Operations.upsert("test_table", {"id": 1})
            Operations.upsert("test_table", {"id": 2})
            Operations.error("Error 2", trace="Trace 2")
            Operations.operation_stream.mark_done()

        producer = threading.Thread(target=produce)
        producer.start()

        # First response: error 1 (no buffered records)
        response1 = next(Operations.operation_stream)

        # Second response: error 2 with 2 buffered records
        response2 = next(Operations.operation_stream)

        producer.join()

        # First error should have no records
        self.assertTrue(isinstance(response1, list))
        self.assertEqual(len(response1), 1)
        self.assertTrue(hasattr(response1[0], "task"))
        task1_payload = json.loads(response1[0].task.message)
        self.assertEqual(task1_payload["message"], "Error 1")

        # Second error should have 2 records
        self.assertTrue(isinstance(response2, list))
        self.assertEqual(len(response2), 2)
        self.assertTrue(hasattr(response2[0], "structured_records"))
        self.assertEqual(len(response2[0].structured_records.structured_records), 2)
        self.assertTrue(hasattr(response2[1], "task"))
        task2_payload = json.loads(response2[1].task.message)
        self.assertEqual(task2_payload["message"], "Error 2")
        self.assertEqual(task2_payload["trace"], "Trace 2")

    def test_mixed_operations_with_warnings_and_errors(self):
        """Test mixed operations including records, warnings, errors, and checkpoints"""

        def produce():
            Operations.upsert("test_table", {"id": 1})
            Operations.warning("First warning")
            Operations.upsert("test_table", {"id": 2})
            Operations.error("First error")
            Operations.upsert("test_table", {"id": 3})
            Operations.checkpoint({"cursor": "3"})
            Operations.upsert("test_table", {"id": 4})
            Operations.warning("Second warning")
            Operations.operation_stream.mark_done()

        producer = threading.Thread(target=produce)
        producer.start()

        responses = []
        while True:
            try:
                response = next(Operations.operation_stream)
                responses.append(response)
                # Unblock if it's a checkpoint
                if isinstance(response, list) and any(r.HasField("checkpoint") for r in response):
                    Operations.operation_stream.unblock()
            except StopIteration:
                break

        producer.join()

        # Should have 4 responses:
        # 1. Warning with 1 record
        # 2. Error with 1 record
        # 3. Checkpoint with 1 record
        # 4. Warning with 1 record
        self.assertEqual(len(responses), 4)

        # Response 1: warning with 1 record
        self.assertTrue(isinstance(responses[0], list))
        self.assertEqual(len(responses[0]), 2)
        self.assertTrue(hasattr(responses[0][1], "warning"))

        # Response 2: error with 1 record
        self.assertTrue(isinstance(responses[1], list))
        self.assertEqual(len(responses[1]), 2)
        self.assertTrue(hasattr(responses[1][1], "task"))

        # Response 3: checkpoint with 1 record
        self.assertTrue(isinstance(responses[2], list))
        self.assertEqual(len(responses[2]), 2)
        self.assertTrue(hasattr(responses[2][1], "checkpoint"))

        # Response 4: warning with 1 record
        self.assertTrue(isinstance(responses[3], list))
        self.assertEqual(len(responses[3]), 2)
        self.assertTrue(hasattr(responses[3][1], "warning"))

    def test_warning_after_full_batch(self):
        """Test warning that comes after a full batch is flushed"""

        def produce():
            # Fill a batch with 100 records
            for i in range(100):
                Operations.upsert("test_table", {"id": i})
            # Add a warning after the batch is full
            Operations.warning("Post-batch warning")
            Operations.operation_stream.mark_done()

        producer = threading.Thread(target=produce)
        producer.start()

        # First response: full batch of 100 records
        response1 = next(Operations.operation_stream)

        # Second response: warning with no records
        response2 = next(Operations.operation_stream)

        producer.join()

        # First response should be 100 records
        self.assertEqual(len(response1.structured_records.structured_records), 100)

        # Second response should be just the warning
        self.assertTrue(isinstance(response2, list))
        self.assertEqual(len(response2), 1)
        self.assertTrue(hasattr(response2[0], "warning"))

    def test_error_after_full_batch(self):
        """Test error that comes after a full batch is flushed"""

        def produce():
            # Fill a batch with 100 records
            for i in range(100):
                Operations.upsert("test_table", {"id": i})
            # Add an error after the batch is full
            Operations.error("Post-batch error", trace="Full trace")
            Operations.operation_stream.mark_done()

        producer = threading.Thread(target=produce)
        producer.start()

        # First response: full batch of 100 records
        response1 = next(Operations.operation_stream)

        # Second response: error with no records
        response2 = next(Operations.operation_stream)

        producer.join()

        # First response should be 100 records
        self.assertEqual(len(response1.structured_records.structured_records), 100)

        # Second response should be just the error
        self.assertTrue(isinstance(response2, list))
        self.assertEqual(len(response2), 1)
        self.assertTrue(hasattr(response2[0], "task"))
        task_payload = json.loads(response2[0].task.message)
        self.assertEqual(task_payload["message"], "Post-batch error")
        self.assertEqual(task_payload["trace"], "Full trace")

    def test_add_checkpoint_releases_producer_lock_before_waiting_for_flush(self):
        stream = Operations.operation_stream
        checkpoint = connector_sdk_pb2.Checkpoint(state_json="{}")
        record = connector_sdk_pb2.StructuredRecord(
            table_name="normal", type=common_pb2.RecordType.UPSERT, data={}
        )
        record_added = threading.Event()

        def wait_for_flush(timeout=None):
            thread = threading.Thread(
                target=lambda: (stream.add_record(record), record_added.set())
            )
            thread.start()
            added = record_added.wait(timeout=1)
            thread.join(timeout=1)
            return added

        stream._checkpoint_flush_signal.wait = wait_for_flush
        stream.add_checkpoint(checkpoint)

        self.assertTrue(record_added.is_set())


if __name__ == "__main__":
    unittest.main()
