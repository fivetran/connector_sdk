from dataclasses import dataclass
from typing import List, Optional

from fivetran_connector_sdk.protos import common_pb2


@dataclass
class DropdownFieldParam:
    """Represents one selectable option in a DropdownField.

    Use `value` for the configuration value that should be saved and passed to your
    connector code. Use `label` and `description` only to control how the option is
    displayed in the setup form.

    Example:
        form_field.DropdownFieldParam(
            value="syncAll",
            label="Sync all accounts",
            description="Automatically sync all accounts you have access to.",
        )

    Args:
        value: Required option value. Converted to a string, stored in `configuration.json`,
            and passed to connector code when selected.
        label: Optional display name for this option. Defaults to `str(value)`.
        description: Optional help text shown with this option. Defaults to an empty string.
    """

    value: object
    label: Optional[str] = None
    description: Optional[str] = None


class TextField:
    """Represents a text input form field.

    Use the class constants to specify the field type:
      - TextField.plain_text: visible plain-text input
      - TextField.password: masked password input

    Args:
        name: Unique identifier for this field, used as the configuration key.
        label: Human-readable label shown in the UI.
        field_type: One of TextField.plain_text or TextField.password.
            Defaults to TextField.plain_text.
        description: Optional help text displayed below the field.
        required: Whether the field must be filled before saving. Defaults to False.
        placeholder: Optional placeholder text shown when the field is empty.
    """

    plain_text = common_pb2.PlainText
    password = common_pb2.Password

    def __new__(
        cls,
        name: str,
        label: str,
        field_type: common_pb2.TextField = common_pb2.PlainText,
        *,
        description: Optional[str] = None,
        required: bool = False,
        placeholder: Optional[str] = None,
    ) -> common_pb2.FormField:
        field = common_pb2.FormField(
            name=name,
            label=label,
            text_field=field_type,
            required=required,
        )
        if description is not None:
            field.description = description
        if placeholder is not None:
            field.placeholder = placeholder
        return field


class DropdownField:
    """Represents a dropdown selection form field.

    Args:
        name: Unique identifier for this field, used as the configuration key.
        label: Human-readable label shown in the UI.
        fields: List of DropdownFieldParam options. If every option only has a value, a simple
            dropdown is created. If a label or description is provided for an option, a rich UI dropdown will be created.
        description: Optional help text displayed below the field.
        required: Whether the field must be filled before saving. Defaults to False.
        placeholder: Optional placeholder text shown when no option is selected.

    Examples:
        form_field.DropdownField(
            name="namedRange",
            label="Named Range",
            fields=[
                form_field.DropdownFieldParam(value="TrustPilot_CurrentDate"),
                form_field.DropdownFieldParam(value="TrustPilot_History"),
            ]
        )

        form_field.DropdownField(
            name="accountSyncMode",
            label="Account sync mode",
            fields=[
                form_field.DropdownFieldParam(
                    value="syncAll",
                    label="Sync all accounts",
                    description="Automatically sync all accounts you access to.",
                ),
            ]
        )
    """

    def __new__(
        cls,
        name: str,
        label: str,
        *,
        fields: List[DropdownFieldParam],
        description: Optional[str] = None,
        required: bool = False,
        placeholder: Optional[str] = None,
    ) -> common_pb2.FormField:
        if not fields:
            raise ValueError(f"DropdownField '{name}' must define at least one option in 'fields'.")
        field = common_pb2.FormField(
            name=name,
            label=label,
            descriptive_dropdown_fields=common_pb2.DescriptiveDropDownFields(
                descriptive_dropdown_field=[
                    common_pb2.DescriptiveDropDownField(
                        value=str(item.value),
                        label=str(item.label if item.label is not None else item.value),
                        description="" if item.description is None else str(item.description),
                    )
                    for item in fields
                ]
            ),
            required=required,
        )
        if description is not None:
            field.description = description
        if placeholder is not None:
            field.placeholder = placeholder
        return field


class ToggleField:
    """Represents a boolean toggle form field.

    Args:
        name: Unique identifier for this field, used as the configuration key.
        label: Human-readable label shown in the UI.
        description: Optional help text displayed below the field.
        required: Whether the field must be filled before saving. Defaults to False.
    """

    def __new__(
        cls,
        name: str,
        label: str,
        *,
        description: Optional[str] = None,
        required: bool = False,
    ) -> common_pb2.FormField:
        field = common_pb2.FormField(
            name=name,
            label=label,
            toggle_field=common_pb2.ToggleField(),
            required=required,
        )
        if description is not None:
            field.description = description
        return field

