from typing import Dict, List

# Import required classes from fivetran_connector_sdk.
# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

from uuid import uuid4  # for generating batch boundaries
import json
from requests_toolbelt.multipart import decoder  # for batch request processing
import datetime


class ODataClient:
    def __init__(self, base_url: str, session, state: Dict = None, timeout: int = 120):
        if not base_url.endswith("/"):
            base_url += "/"
        self.base_url = base_url
        self.session = session
        self.timeout = timeout
        self.batch_requests = []
        self.state = state or {}
        log.info(f"OData client initialized : {self.base_url}")

    def _build_query_options(self, options: Dict) -> str:
        """
        Build OData query options string from a dictionary.
        This method converts a Python dictionary of query options to OData query syntax.
        """
        if not options:
            return ""

        query_parts = []
        self._process_standard_options(options=options, query_parts=query_parts)
        self._process_expand_option(options=options, query_parts=query_parts)
        return "&".join(query_parts)

    @staticmethod
    def _process_standard_options(options: Dict, query_parts: List[str]) -> None:
        """Process standard OData options and add to query_parts."""
        standard_options = {
            "select": "$select",
            "filter": "$filter",
            "orderby": "$orderby",
            "top": "$top",
            "skip": "$skip",
            "count": "$count",
            "search": "$search",
        }

        for key, odata_key in standard_options.items():
            if key not in options:
                continue

            value = options[key]
            if key == "count" and isinstance(value, bool):
                query_parts.append(f"{odata_key}={str(value).lower()}")
            elif isinstance(value, list):
                query_parts.append(f"{odata_key}={','.join(value)}")
            else:
                query_parts.append(f"{odata_key}={value}")

    def _process_expand_option(self, options: Dict, query_parts: List[str]) -> None:
        """
        Process expand option and add to query_parts.
        Handles complex expand scenarios including nested expands and options.
        """
        if "expand" not in options:
            return

        expand_value = options["expand"]
        if isinstance(expand_value, list):
            query_parts.append(f"$expand={','.join(expand_value)}")
        elif isinstance(expand_value, dict):
            expand_parts = self._build_expand_parts(expand_dict=expand_value)
            query_parts.append(f"$expand={expand_parts}")
        else:
            query_parts.append(f"$expand={expand_value}")

    def _build_expand_parts(self, expand_dict: Dict) -> str:
        """Build the expand expression parts from a dictionary."""
        expand_parts = []
        for entity, entity_options in expand_dict.items():
            if isinstance(entity_options, dict):
                nested_options = self._build_nested_options(options=entity_options)
                expand_parts.append(f"{entity}({';'.join(nested_options)})")
            else:
                expand_parts.append(entity)
        return ",".join(expand_parts)

    def _build_nested_options(self, options: Dict) -> List[str]:
        """Build nested options for expand."""
        nested_options = []
        for opt_key, opt_val in options.items():
            if opt_key == "select" and isinstance(opt_val, list):
                nested_options.append(f"$select={','.join(opt_val)}")
            elif opt_key == "expand" and isinstance(opt_val, list):
                nested_options.append(f"$expand={','.join(opt_val)}")
            elif opt_key == "expand" and isinstance(opt_val, dict):
                nested_expand = self._build_expand_parts(expand_dict=opt_val)
                nested_options.append(f"$expand={nested_expand}")
            else:
                nested_options.append(f"${opt_key}={opt_val}")
        return nested_options

    def _build_request_url(
        self, base_path: str, query_options: Dict = None, relative_url: bool = False
    ) -> str:
        """Build a request URL with the given path and query options."""
        if relative_url:
            url = base_path
        else:
            url = f"{self.base_url}{base_path}"

        if query_options:
            query_string = self._build_query_options(options=query_options)
            if query_string:
                url = f"{url}?{query_string}"

        return url

    def _make_request(self, url: str):
        """Make a GET request to the given URL and return the JSON response."""
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        response_data = response.json()
        return response_data

    def _update_state_tracker(self, item: Dict, update_state: Dict) -> None:
        """Updates the state tracker with the highest values from the current record."""
        if not update_state:
            return

        for state_var, column in update_state.items():
            try:
                current_value = item[column]
                if state_var not in self.state or current_value > self.state[state_var]:
                    self.state[state_var] = current_value
            except KeyError as e:
                log.error(f"{column} not found in the fetched data", e)

    def _upsert_formatted_data(self, formatted_data, table, update_state, query_options=None):
        """Upsert the formatted data and update the state tracker."""
        if formatted_data["success"]:
            for record in formatted_data["data"]:
                # Handle expanded entities if expand option is present
                if query_options and "expand" in query_options:
                    self._upsert_expanded_data(
                        record=record,
                        expand_options=query_options["expand"],
                        parent_table=table,
                        parent_data=record,
                    )

                op.upsert(table=table, data=record)
                self._update_state_tracker(item=record, update_state=update_state)

            log.info(f"upserted {formatted_data['count']} records into {table}")
            op.checkpoint(self.state)
        else:
            raise RuntimeError(f"Error fetching entity set for table {table}")

    def _upsert_expanded_data(
        self, record: Dict, expand_options: Dict, parent_table: str, parent_data: Dict
    ):
        """
        Upsert expanded entities to separate tables.
        This method extracts expanded navigation properties from the record
        and upserts them to separate tables named {parent_table}.{nav_prop}.
        It also handles nested expansions recursively and includes parent keys in child records.
        """
        # Extract parent key fields (scalar values that are likely identifiers)
        parent_keys = self._extract_parent_keys(
            parent_data=parent_data, expand_options=expand_options
        )

        # Handle both dict and list expand options formats
        if isinstance(expand_options, dict):
            nav_props = expand_options
        elif isinstance(expand_options, list):
            # Convert list format to dict format for processing
            nav_props = {prop: {} for prop in expand_options}
        else:
            return

        for nav_prop, options in nav_props.items():
            if nav_prop not in record or record[nav_prop] is None:
                continue

            # Extract expanded data and immediately remove from parent record
            expanded_data = record.pop(nav_prop)
            child_table = f"{parent_table}.{nav_prop}"

            # Handle collections (one-to-many relationships)
            if isinstance(expanded_data, list):
                for item in expanded_data:
                    if isinstance(item, dict):
                        # Add parent keys to child record
                        item.update(parent_keys)
                        # Process nested expansions recursively
                        if isinstance(options, dict) and "expand" in options:
                            self._upsert_expanded_data(
                                record=item,
                                expand_options=options["expand"],
                                parent_table=child_table,
                                parent_data=item,
                            )
                        # Clean and upsert to child table
                        cleaned_item = self.clean_odata_fields(data=item)
                        op.upsert(table=child_table, data=cleaned_item)

            # Handle single entity (one-to-one relationships)
            elif isinstance(expanded_data, dict):
                # Add parent keys to child record
                expanded_data.update(parent_keys)
                # Process nested expansions recursively
                if isinstance(options, dict) and "expand" in options:
                    self._upsert_expanded_data(
                        record=expanded_data,
                        expand_options=options["expand"],
                        parent_table=child_table,
                        parent_data=expanded_data,
                    )
                # Clean and upsert to child table
                cleaned_data = self.clean_odata_fields(data=expanded_data)
                op.upsert(table=child_table, data=cleaned_data)

    def _extract_parent_keys(self, parent_data: Dict, expand_options: Dict) -> Dict:
        """
        Extract key fields from parent data to be included in child records.
        This method identifies likely primary key fields and scalar values
        (excluding expanded navigation properties).
        """
        parent_keys = {}

        # Handle both dict and list expand options formats
        if isinstance(expand_options, dict):
            expand_props = set(expand_options.keys())
        elif isinstance(expand_options, list):
            expand_props = set(expand_options)
        else:
            expand_props = set()

        for key, value in parent_data.items():
            # Skip navigation properties (they are being expanded)
            if key in expand_props:
                continue
            # Include scalar values that are likely keys or important identifiers
            if isinstance(value, (str, int, float, bool)) or value is None:
                parent_keys[key] = value

        return parent_keys

    def upsert_entity(
        self,
        entity: Dict,
        additional_headers: Dict = None,
        handle_pagination: bool = True,
        state: Dict = None,
    ):
        """Fetch an entity set from the OData service and upsert records."""
        entity_set = entity.get("entity_set", None)
        query_options = entity.get("query_options", {})
        table = entity.get("table", entity_set)
        update_state = entity.get("update_state", None)

        if not entity_set:
            raise ValueError("entity_set must be specified")

        if state:
            self.state = state

        url = self._build_request_url(base_path=entity_set, query_options=query_options)

        if additional_headers:
            self.session.headers.update(additional_headers)

        try:
            if handle_pagination:
                self._handle_pagination(
                    initial_url=url,
                    table=table,
                    update_state=update_state,
                    query_options=query_options,
                )
            else:
                response_data = self._make_request(url=url)
                formatted_data = self._standardize_output(response=response_data)
                self._upsert_formatted_data(
                    formatted_data=formatted_data,
                    table=table,
                    update_state=update_state,
                    query_options=query_options,
                )

            return self.state

        except Exception as e:
            raise ConnectionError(f"Error fetching entity set: {str(e)}")

    def upsert_multiple_entity(self, entity_list: List[Dict], state: Dict = None):
        """
        Fetch data from multiple entity sets and upserts records.
        Convenient method to process multiple entity sets sequentially.
        """
        if state:
            self.state = state
        for entity in entity_list:
            self.upsert_entity(entity=entity)
        return self.state

    def _handle_pagination(
        self,
        initial_url: str,
        table: str = None,
        update_state: Dict = None,
        query_options: Dict = None,
    ):
        """
        Handles pagination by following @odata.nextLink until all pages are fetched.
        You can modify this method to handle service-specific pagination formats
        """
        next_link = initial_url

        while next_link:
            current_page = self._make_request(url=next_link)
            formatted_data = self._standardize_output(response=current_page)
            self._upsert_formatted_data(
                formatted_data=formatted_data,
                table=table,
                update_state=update_state,
                query_options=query_options,
            )
            next_link = current_page.get("@odata.nextLink") or current_page.get("odata.nextLink")
            if next_link and "http" not in next_link:
                next_link = f"{self.base_url}{next_link}"

    @staticmethod
    def clean_odata_fields(data):
        """
        Recursively clean OData metadata fields (fields starting with '@odata').
        You can modify this method if your service uses different metadata conventions
        or if you want to preserve certain metadata fields.
        """
        if isinstance(data, dict):
            return {
                k: ODataClient.clean_odata_fields(v)
                for k, v in data.items()
                if not (isinstance(k, str) and "@odata" in k)
            }
        elif isinstance(data, list):
            return [ODataClient.clean_odata_fields(item) for item in data]
        elif isinstance(data, datetime.datetime):
            return data.isoformat()
        else:
            return data

    @staticmethod
    def _standardize_output(response: Dict) -> Dict:
        """
        Standardizes the output format for all OData responses, focusing on business data.
        Creates a consistent format from potentially varied OData responses.
        This is a critical method to customize if your OData service
        has a non-standard response format. You can modify this method to handle service-specific
        response structures or to transform data before upserting.
        """
        result = {"data": [], "count": 0, "success": False}

        if "@odata.count" in response:
            result["count"] = response["@odata.count"]

        if "value" in response:
            result["data"] = ODataClient.clean_odata_fields(data=response["value"])
        else:
            entity_data = {k: v for k, v in response.items() if not k.contains("@odata")}
            if entity_data:
                result["data"] = [ODataClient.clean_odata_fields(data=entity_data)]

        if result["count"] == 0:
            result["count"] = len(result["data"])

        result["success"] = True

        return result

    def _paginate_with_batch(
        self, table, update_state=None, initial_response=None, query_options=None
    ):
        """
        Paginate using $skip and $top parameters.
        Helper method for handling pagination in batch responses.
        """

        if initial_response:
            formatted_data = self._standardize_output(response=initial_response)
            self._upsert_formatted_data(
                formatted_data=formatted_data,
                table=table,
                update_state=update_state,
                query_options=query_options,
            )
            next_link = initial_response.get("@odata.nextLink") or initial_response.get(
                "odata.nextLink"
            )

            if next_link:
                next_url = f"{self.base_url}{next_link}"
                self._handle_pagination(
                    initial_url=next_url,
                    table=table,
                    update_state=update_state,
                    query_options=query_options,
                )
        else:
            raise RuntimeError(f"Error fetching entity set for table {table}")

    def _build_batch_request_body(self, batch_requests, batch_boundary):
        """
        Build the multipart batch request body.
        Creates the MIME multipart request body according to OData batch specification.
        """
        body = []

        for i, request in enumerate(batch_requests):
            body.append(f"--{batch_boundary}")
            body.append("Content-Type: application/http")
            body.append("Content-Transfer-Encoding: binary")
            body.append("")

            entity_set = request["entity_set"]
            query_options = request.get("query_options", {})

            relative_url = self._build_request_url(
                base_path=entity_set, query_options=query_options, relative_url=True
            )

            body.append(f"GET {relative_url} HTTP/1.1")
            body.append("Accept: application/json")
            body.append("")
            body.append("")

        body.append(f"--{batch_boundary}--")
        return "\r\n".join(body)

    def _process_batch_response(self, response):
        """
        Process multipart batch response using requests_toolbelt.
        Decodes the multipart response and processes each part.
        """
        log.info(f"Processing batch response with {len(self.batch_requests)} requests")
        content_type = response.headers.get("Content-Type", "")

        if "multipart/mixed" not in content_type:
            log.error(f"Invalid content type: {content_type}")
            raise ValueError(f"Expected multipart/mixed response, got: {content_type}")

        try:
            multipart_data = decoder.MultipartDecoder(response.content, content_type)
            log.info(
                f"Successfully decoded multipart response with {len(multipart_data.parts)} parts"
            )

            for i, part in enumerate(multipart_data.parts):
                if i >= len(self.batch_requests):
                    break

                self._process_batch_part(part=part, part_index=i)

        except Exception as e:
            log.error("Failed to process batch response.", e)
            raise

    def _process_batch_part(self, part, part_index: int):
        """Process an individual part from a multipart response."""
        request_config = self.batch_requests[part_index]
        entity_set = request_config["entity_set"]
        table = request_config.get("table", entity_set)
        update_state = request_config.get("update_state")
        query_options = request_config.get("query_options", {})

        log.info(f"Processing part {part_index + 1} for entity: {entity_set}")

        if not part.content:
            log.error(f"Empty content in part {part_index}")
            return

        try:
            # Extract JSON data from the part
            json_content = self._extract_json_from_part(part=part, part_index=part_index)
            if not json_content:
                return

            # Parse the JSON content
            response_data = json.loads(json_content)
            record_count = len(response_data.get("value", []))
            log.info(f"Part {part_index} contains {record_count} records")

            # Process with pagination
            self._paginate_with_batch(
                table=table,
                update_state=update_state,
                initial_response=response_data,
                query_options=query_options,
            )

        except Exception as e:
            raise RuntimeError(f"Error processing part {part_index}: {str(e)}")

    def _extract_json_from_part(self, part, part_index: int) -> str:
        """Extract JSON content from a multipart part, handling nested HTTP structure."""
        try:
            content_str = part.content.decode("utf-8")

            body_start = ODataClient._find_header_body_separator(content=content_str)
            if body_start == -1:
                raise RuntimeError(f"Cannot find HTTP headers/body separator in part {part_index}")

            http_body = content_str[body_start:].strip()
            json_start = ODataClient._find_header_body_separator(content=http_body)

            if json_start != -1:
                return http_body[json_start:].strip()
            else:
                return http_body.strip()

        except UnicodeDecodeError:
            log.error(f"Unicode decode error in part {part_index}")
            raise

    @staticmethod
    def _find_header_body_separator(content: str) -> int:
        """Find the separator between headers and body in HTTP content."""

        separator_pos = content.find("\r\n\r\n")
        if separator_pos != -1:
            return separator_pos + 4

        separator_pos = content.find("\n\n")
        if separator_pos != -1:
            return separator_pos + 2

        return -1

    def add_batch(self, entity: Dict):
        """
        Add a batch request to the batch queue.
        Use this method to queue multiple requests before executing them
        in a single batch with upsert_batch().
        """
        entity_set = entity.get("entity_set", None)

        if not entity_set:
            raise ValueError("entity_set must be specified")

        batch_request = {
            "entity_set": entity_set,
            "query_options": entity.get("query_options", {}),
            "table": entity.get("table", entity_set),
            "update_state": entity.get("update_state", None),
        }

        self.batch_requests.append(batch_request)
        return self  # Enable method chaining

    def upsert_batch(self, state: Dict = None):
        """
        Execute a batch request with multiple parts.
        Sends all queued batch requests in a single HTTP request and processes the responses.
        """
        if not self.batch_requests:
            log.warning("No batch requests to execute")
            return self.state

        if state:
            self.state = state

        batch_boundary = f"batch_{uuid4().hex}"

        headers = {
            "Content-Type": f"multipart/mixed; boundary={batch_boundary}",
            "Accept": "multipart/mixed",
            "Content-Transfer-Encoding": "binary",
        }

        request_body = self._build_batch_request_body(
            batch_requests=self.batch_requests, batch_boundary=batch_boundary
        )

        batch_url = f"{self.base_url}$batch"
        response = self.session.post(
            batch_url, headers=headers, data=request_body, timeout=self.timeout
        )
        response.raise_for_status()

        self._process_batch_response(response=response)

        self.batch_requests = []
        return self.state
