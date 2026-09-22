from fivetran_connector_sdk.protos import common_pb2


class Test:
    """Factory for connector setup test responses.

    Instantiate once per test function, then call success() or failure().

    Example:
        def connection_test(configuration: dict):
            test = Test()
            try:
                connect(configuration)
                return test.success()
            except Exception as e:
                return test.failure(str(e))
    """

    @staticmethod
    def success() -> common_pb2.TestResponse:
        """Returns a successful test response."""
        return common_pb2.TestResponse(success=True)

    @staticmethod
    def failure(message: str) -> common_pb2.TestResponse:
        """Returns a failed test response.

        Args:
            message: Human-readable description of why the test failed.
        """
        return common_pb2.TestResponse(failure=message)
