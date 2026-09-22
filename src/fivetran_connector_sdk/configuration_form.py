from typing import Callable, Optional

from fivetran_connector_sdk.protos import common_pb2


class ConfigurationForm:
    """Represents the setup form returned by the connector's configuration_form() method.

    Use add_field() to add form fields and add_test() to register setup test functions.
    The platform calls each registered test function by its __name__ when running setup tests.

    Example:
        def configuration_form():
            form = ConfigurationForm()
            form.add_field(form_field.TextField("host", "Host"))
            form.add_field(form_field.TextField("password", "Password", form_field.TextField.password))
            form.add_test(label="Test database connection", func=connection_test)
            return form
    """

    def __init__(self):
        self._fields = []
        self._tests = []  # list of (label: str, func: Callable)

    def add_field(self, field) -> "ConfigurationForm":
        """Adds a form field.

        Args:
            field: A form_field.TextField, DropdownField, or ToggleField instance.

        Returns:
            self, for method chaining.
        """
        if not isinstance(field, common_pb2.FormField):
            raise TypeError(f"field must be a form_field, got {type(field).__name__}: {field!r}")

        self._fields.append(field)  # field is already a common_pb2.FormField proto
        return self

    def add_test(self, *, label: str, func: Callable) -> "ConfigurationForm":
        """Registers a setup test function.

        The function's __name__ is used as the test identifier sent to the platform.

        Args:
            label: Short human-readable description shown in the setup UI.
            func: The test function to call. Must accept a single configuration dict argument
                and return a Test().success() or Test().failure(...) result.

        Returns:
            self, for method chaining.
        """
        if not label:
            func_name = getattr(func, "__name__", repr(func))
            raise ValueError(f"label must not be empty for test function '{func_name}'")
        if not callable(func):
            raise TypeError("func must be callable")
        if func.__name__ == "<lambda>":
            raise ValueError(
                "anonymous lambda functions cannot be used as test functions; "
                "assign the function to a named variable first"
            )
        if any(f.__name__ == func.__name__ for _, f in self._tests):
            raise ValueError(
                f"a test function named '{func.__name__}' is already registered; "
                "each test function must have a unique name"
            )

        self._tests.append((label, func))
        return self

    def _get_test_function_by_name(self, name: str) -> Optional[Callable]:
        """Returns the registered test function matching the given name, or None."""
        for _, func in self._tests:
            if func.__name__ == name:
                return func
        return None

    def _to_proto(self) -> common_pb2.ConfigurationFormResponse:
        return common_pb2.ConfigurationFormResponse(
            fields=self._fields,
            tests=[
                common_pb2.ConfigurationTest(name=func.__name__, label=label)
                for label, func in self._tests
            ],
        )
