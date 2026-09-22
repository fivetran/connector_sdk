import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from fivetran_connector_sdk.test import Test
from fivetran_connector_sdk.protos import common_pb2


class TestTestSuccess(unittest.TestCase):

    def test_success_returns_test_response(self):
        result = Test.success()
        self.assertIsInstance(result, common_pb2.TestResponse)

    def test_success_sets_success_true(self):
        result = Test.success()
        self.assertTrue(result.success)

    def test_success_has_no_failure_message(self):
        result = Test.success()
        self.assertEqual(result.failure, "")


class TestTestFailure(unittest.TestCase):

    def test_failure_returns_test_response(self):
        result = Test.failure("cannot connect")
        self.assertIsInstance(result, common_pb2.TestResponse)

    def test_failure_sets_failure_message(self):
        result = Test.failure("cannot connect")
        self.assertEqual(result.failure, "cannot connect")

    def test_failure_success_is_false(self):
        result = Test.failure("cannot connect")
        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()
