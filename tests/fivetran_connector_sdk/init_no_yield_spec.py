import unittest
from unittest.mock import MagicMock
from fivetran_connector_sdk import Connector, Operations


class TestConnectorUpdateYieldApproach(unittest.TestCase):
    def setUp(self):
        def yield_update_method(configuration, state):
            for index in range(5):
                primary_key = "pk_" + str(index)
                message = "message: " + str(index)
                yield Operations.upsert("table_name", {"id": primary_key, "name": message})

        def no_yield_update_method(configuration, state):
            for index in range(5):
                primary_key = "pk_" + str(index)
                message = "message: " + str(index)
                Operations.upsert("table_name", {"id": primary_key, "name": message})

        # set the batch size to 1 for tests
        from fivetran_connector_sdk import operation_stream

        operation_stream.MAX_RECORDS_IN_BATCH = 1

        # Reset the operation_stream before each test
        from fivetran_connector_sdk.operations import _OperationStream

        Operations.operation_stream = _OperationStream()

        self.yield_update_method = yield_update_method
        self.no_yield_update_method = no_yield_update_method
        configuration = {"api_key": "test_key", "api_secret": "test_secret"}
        self.request = MagicMock()
        self.request.configuration = configuration
        self.request.state_json = '{"state": "test_state"}'

    def test_no_yield_approach_for_method_with_yield(self):
        self.connector = Connector(update=self.yield_update_method)

        Operations.upsert("table_name", {"id": 1, "name": "test"})
        update_response = next(Operations.operation_stream)
        responses = []

        count = 0
        for resp in self.connector.Update(self.request, MagicMock()):
            responses.append(resp)
            self.assertIsInstance(resp, type(update_response))
            self.assertEqual(
                resp.structured_records.structured_records[0].table_name, "table_name"
            )
            self.assertTrue(
                f"pk_{count}" in str(resp.structured_records.structured_records[0].data["id"])
            )
            self.assertTrue(
                f"message: {count}"
                in str(resp.structured_records.structured_records[0].data["name"])
            )
            count += 1

        self.assertEqual(len(responses), 5)

    def test_no_yield_approach_for_method_without_yield(self):
        self.connector = Connector(update=self.no_yield_update_method)

        Operations.upsert("table_name", {"id": 1, "name": "test"})
        update_response = next(Operations.operation_stream)
        responses = []

        count = 0
        for resp in self.connector.Update(self.request, MagicMock()):
            responses.append(resp)
            self.assertIsInstance(resp, type(update_response))
            self.assertEqual(
                resp.structured_records.structured_records[0].table_name, "table_name"
            )
            self.assertTrue(
                f"pk_{count}" in str(resp.structured_records.structured_records[0].data["id"])
            )
            self.assertTrue(
                f"message: {count}"
                in str(resp.structured_records.structured_records[0].data["name"])
            )
            count += 1

        self.assertEqual(len(responses), 5)

    def test_no_yield_approach_with_exception_in_update_method(self):
        def update_method_with_failure(configuration, state):
            for i in range(5):
                primary_key = "pk_" + str(i)
                message = "message: " + str(i)
                Operations.upsert("table_name", {"id": primary_key, "name": message})
            raise RuntimeError("Test error")

        connector = Connector(update=update_method_with_failure)

        responses = []

        with self.assertRaises(RuntimeError):
            for resp in connector.Update(self.request, MagicMock()):
                responses.append(resp)

        self.assertEqual(
            len(responses), 5
        )  # the first 5 responses should be processed before the exception

    def test_no_yield_approach_with_type_error_in_update_method(self):
        def update_method_with_type_error(configuration, state):
            # This will cause a TypeError: 'NoneType' object is not iterable
            for item in None:
                Operations.upsert("table_name", {"id": item})

        connector = Connector(update=update_method_with_type_error)

        with self.assertRaises(RuntimeError) as context:
            list(connector.Update(self.request, MagicMock()))

        # The TypeError should now be re-raised as RuntimeError after the change
        self.assertIn("'NoneType' object is not iterable", str(context.exception))


if __name__ == "__main__":
    unittest.main()
