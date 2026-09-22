import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from fivetran_connector_sdk.configuration_form import ConfigurationForm
from fivetran_connector_sdk.protos import common_pb2
from fivetran_connector_sdk import form_field


class TestConfigurationFormAddField(unittest.TestCase):

    def test_add_field_stores_proto_and_returns_self(self):
        form = ConfigurationForm()
        result = form.add_field(form_field.TextField("host", "Host"))

        self.assertIs(result, form)
        self.assertEqual(len(form._fields), 1)

    def test_add_field_chaining(self):
        form = ConfigurationForm()
        form.add_field(form_field.TextField("host", "Host")).add_field(
            form_field.ToggleField("tls", "Enable TLS")
        )

        self.assertEqual(len(form._fields), 2)

    def test_add_field_raises_when_field_is_not_form_field(self):
        form = ConfigurationForm()

        with self.assertRaisesRegex(TypeError, "field must be a form_field"):
            form.add_field("not_a_form_field")


class TestConfigurationFormAddTest(unittest.TestCase):

    def test_add_test_stores_label_and_func_and_returns_self(self):
        def my_test(config):
            pass

        form = ConfigurationForm()
        result = form.add_test(label="Check connection", func=my_test)

        self.assertIs(result, form)
        self.assertEqual(len(form._tests), 1)
        label, func = form._tests[0]
        self.assertEqual(label, "Check connection")
        self.assertIs(func, my_test)

    def test_add_test_chaining(self):
        def test_a(config):
            pass

        def test_b(config):
            pass

        form = ConfigurationForm()
        form.add_test(label="A", func=test_a).add_test(label="B", func=test_b)

        self.assertEqual(len(form._tests), 2)

    def test_add_test_raises_when_label_empty(self):
        def my_test(config):
            pass

        form = ConfigurationForm()

        with self.assertRaisesRegex(ValueError, "label must not be empty"):
            form.add_test(label="", func=my_test)

    def test_add_test_raises_when_func_not_callable(self):
        form = ConfigurationForm()

        with self.assertRaisesRegex(TypeError, "func must be callable"):
            form.add_test(label="Check connection", func="not_callable")

    def test_add_test_raises_when_func_is_lambda(self):
        form = ConfigurationForm()

        with self.assertRaisesRegex(
            ValueError,
            "anonymous lambda functions cannot be used as test functions; "
            "assign the function to a named variable first",
        ):
            form.add_test(label="Check connection", func=lambda config: None)

    def test_add_test_raises_when_same_function_registered_twice(self):
        def my_test(config):
            pass

        form = ConfigurationForm()
        form.add_test(label="First", func=my_test)

        with self.assertRaisesRegex(
            ValueError, "a test function named 'my_test' is already registered"
        ):
            form.add_test(label="Second", func=my_test)

    def test_add_test_raises_when_two_functions_share_same_name(self):
        def connection_test(config):
            pass

        first = connection_test

        def connection_test(config):  # shadows the first, same __name__
            pass

        form = ConfigurationForm()
        form.add_test(label="First", func=first)

        with self.assertRaisesRegex(
            ValueError, "a test function named 'connection_test' is already registered"
        ):
            form.add_test(label="Second", func=connection_test)


class TestConfigurationFormToProto(unittest.TestCase):

    def test_to_proto_returns_configuration_form_response(self):
        def conn_test(config):
            pass

        form = ConfigurationForm()
        form.add_field(form_field.TextField("host", "Host"))
        form.add_field(form_field.ToggleField("tls", "Enable TLS"))
        form.add_test(label="Connection test", func=conn_test)

        proto = form._to_proto()

        self.assertIsInstance(proto, common_pb2.ConfigurationFormResponse)
        self.assertEqual(len(proto.fields), 2)
        self.assertEqual(proto.fields[0].name, "host")
        self.assertEqual(proto.fields[1].name, "tls")
        self.assertEqual(len(proto.tests), 1)
        self.assertEqual(proto.tests[0].name, "conn_test")
        self.assertEqual(proto.tests[0].label, "Connection test")

    def test_to_proto_with_no_fields_or_tests(self):
        proto = ConfigurationForm()._to_proto()

        self.assertIsInstance(proto, common_pb2.ConfigurationFormResponse)
        self.assertEqual(len(proto.fields), 0)
        self.assertEqual(len(proto.tests), 0)


class TestGetTestFunctionByName(unittest.TestCase):

    def test_returns_function_matching_name(self):
        def my_test(config):
            pass

        form = ConfigurationForm()
        form.add_test(label="My test", func=my_test)

        self.assertIs(form._get_test_function_by_name("my_test"), my_test)

    def test_returns_none_when_name_not_found(self):
        form = ConfigurationForm()
        self.assertIsNone(form._get_test_function_by_name("nonexistent"))

    def test_returns_correct_function_among_multiple(self):
        def test_a(config):
            pass

        def test_b(config):
            pass

        form = ConfigurationForm()
        form.add_test(label="A", func=test_a)
        form.add_test(label="B", func=test_b)

        self.assertIs(form._get_test_function_by_name("test_a"), test_a)
        self.assertIs(form._get_test_function_by_name("test_b"), test_b)
        self.assertIsNone(form._get_test_function_by_name("test_c"))


if __name__ == "__main__":
    unittest.main()
