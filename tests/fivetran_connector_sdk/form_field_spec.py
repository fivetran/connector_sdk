import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from fivetran_connector_sdk import form_field
from fivetran_connector_sdk.protos import common_pb2


class TestTextField(unittest.TestCase):

    def test_returns_form_field_proto(self):
        field = form_field.TextField("host", "Host")

        self.assertIsInstance(field, common_pb2.FormField)
        self.assertEqual(field.name, "host")
        self.assertEqual(field.label, "Host")
        self.assertEqual(field.text_field, common_pb2.PlainText)

    def test_password_type(self):
        field = form_field.TextField("password", "Password", form_field.TextField.password)

        self.assertEqual(field.text_field, common_pb2.Password)

    def test_plain_text_constant(self):
        self.assertEqual(form_field.TextField.plain_text, common_pb2.PlainText)

    def test_password_constant(self):
        self.assertEqual(form_field.TextField.password, common_pb2.Password)

    def test_optional_description(self):
        field = form_field.TextField("host", "Host", description="The hostname")
        self.assertEqual(field.description, "The hostname")

    def test_required_flag(self):
        field = form_field.TextField("host", "Host", required=True)
        self.assertTrue(field.required)

    def test_placeholder(self):
        field = form_field.TextField("host", "Host", placeholder="e.g. localhost")
        self.assertEqual(field.placeholder, "e.g. localhost")

    def test_defaults(self):
        field = form_field.TextField("host", "Host")
        self.assertFalse(field.required)
        self.assertEqual(field.description, "")
        self.assertEqual(field.placeholder, "")


class TestDropdownField(unittest.TestCase):

    def test_returns_form_field_proto(self):
        field = form_field.DropdownField(
            "region",
            "Region",
            fields=[
                form_field.DropdownFieldParam(value="us-east-1"),
                form_field.DropdownFieldParam(value="eu-west-1"),
            ],
        )

        self.assertIsInstance(field, common_pb2.FormField)
        self.assertEqual(field.name, "region")
        self.assertEqual(field.label, "Region")
        self.assertTrue(field.HasField("descriptive_dropdown_fields"))
        items = list(field.descriptive_dropdown_fields.descriptive_dropdown_field)
        self.assertEqual([item.value for item in items], ["us-east-1", "eu-west-1"])
        self.assertEqual([item.label for item in items], ["us-east-1", "eu-west-1"])
        self.assertEqual([item.description for item in items], ["", ""])

    def test_converts_values_to_strings(self):
        field = form_field.DropdownField(
            "port",
            "Port",
            fields=[
                form_field.DropdownFieldParam(value=5432),
                form_field.DropdownFieldParam(value=3306),
            ],
        )
        items = list(field.descriptive_dropdown_fields.descriptive_dropdown_field)
        self.assertEqual([item.value for item in items], ["5432", "3306"])
        self.assertEqual([item.label for item in items], ["5432", "3306"])

    def test_optional_description(self):
        field = form_field.DropdownField(
            "region",
            "Region",
            fields=[form_field.DropdownFieldParam(value="us")],
            description="AWS region",
        )
        self.assertEqual(field.description, "AWS region")

    def test_required_flag(self):
        field = form_field.DropdownField(
            "region",
            "Region",
            fields=[form_field.DropdownFieldParam(value="us")],
            required=True,
        )
        self.assertTrue(field.required)

    def test_placeholder(self):
        field = form_field.DropdownField(
            "region",
            "Region",
            fields=[form_field.DropdownFieldParam(value="us")],
            placeholder="Select a region",
        )
        self.assertEqual(field.placeholder, "Select a region")

    def test_fields_with_value_only_returns_descriptive_dropdown_field(self):
        field = form_field.DropdownField(
            name="namedRange",
            label="Named Range",
            fields=[
                form_field.DropdownFieldParam(value="TrustPilot_CurrentDate"),
                form_field.DropdownFieldParam(value="TrustPilot_History"),
            ],
        )

        self.assertFalse(field.HasField("dropdown_field"))
        self.assertTrue(field.HasField("descriptive_dropdown_fields"))
        items = list(field.descriptive_dropdown_fields.descriptive_dropdown_field)
        self.assertEqual([item.value for item in items], ["TrustPilot_CurrentDate", "TrustPilot_History"])
        self.assertEqual([item.label for item in items], ["TrustPilot_CurrentDate", "TrustPilot_History"])
        self.assertEqual([item.description for item in items], ["", ""])

    def test_fields_with_labels_and_descriptions_returns_descriptive_dropdown_field(self):
        field = form_field.DropdownField(
            name="accountSyncMode",
            label="Account sync mode",
            fields=[
                form_field.DropdownFieldParam(
                    value="syncAll",
                    label="Sync all accounts",
                    description="Automatically sync all accounts you access to.",
                ),
                form_field.DropdownFieldParam(
                    value="syncSelected",
                    label="Sync specific accounts",
                    description="Select accounts you have access to sync.",
                ),
            ],
        )

        self.assertFalse(field.HasField("dropdown_field"))
        self.assertTrue(field.HasField("descriptive_dropdown_fields"))
        items = list(field.descriptive_dropdown_fields.descriptive_dropdown_field)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].value, "syncAll")
        self.assertEqual(items[0].label, "Sync all accounts")
        self.assertEqual(items[0].description, "Automatically sync all accounts you access to.")
        self.assertEqual(items[1].value, "syncSelected")
        self.assertEqual(items[1].label, "Sync specific accounts")
        self.assertEqual(items[1].description, "Select accounts you have access to sync.")

    def test_fields_with_description_only_defaults_label_to_value(self):
        field = form_field.DropdownField(
            "mode",
            "Mode",
            fields=[
                form_field.DropdownFieldParam(value="syncAll", description="Sync everything"),
            ],
        )

        item = field.descriptive_dropdown_fields.descriptive_dropdown_field[0]
        self.assertEqual(item.value, "syncAll")
        self.assertEqual(item.label, "syncAll")
        self.assertEqual(item.description, "Sync everything")

    def test_requires_fields(self):
        with self.assertRaises(TypeError):
            form_field.DropdownField("region", "Region")

    def test_raises_when_fields_is_empty(self):
        with self.assertRaises(ValueError) as ctx:
            form_field.DropdownField("region", "Region", fields=[])
        self.assertIn("region", str(ctx.exception))
        self.assertIn("at least one option", str(ctx.exception))


class TestToggleField(unittest.TestCase):

    def test_returns_form_field_proto(self):
        field = form_field.ToggleField("enable_tls", "Enable TLS")

        self.assertIsInstance(field, common_pb2.FormField)
        self.assertEqual(field.name, "enable_tls")
        self.assertEqual(field.label, "Enable TLS")
        self.assertTrue(field.HasField("toggle_field"))

    def test_optional_description(self):
        field = form_field.ToggleField("enable_tls", "Enable TLS", description="Use TLS encryption")
        self.assertEqual(field.description, "Use TLS encryption")

    def test_required_flag(self):
        field = form_field.ToggleField("enable_tls", "Enable TLS", required=True)
        self.assertTrue(field.required)

if __name__ == "__main__":
    unittest.main()
