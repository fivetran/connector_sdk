"""Discord API Connector for Fivetran.

This connector demonstrates how to fetch Discord server data including guilds,
channels, messages, and users using the Discord API.

See the Technical Reference documentation:
https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update

And the Best Practices documentation:
https://fivetran.com/docs/connectors/connector-sdk/best-practices
"""

# For reading configuration from a JSON file
import json

# For making HTTP requests to Discord API
import requests

# For handling time-based operations and rate limiting
import time

# For handling datetime operations
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and
# checkpoint()
from fivetran_connector_sdk import Operations as op

# Constants for API configuration and rate limiting
__MAX_RETRIES = 3  # Maximum number of retry attempts for API requests
__BASE_DELAY = 1  # Base delay in seconds for API request retries
__RATE_LIMIT_DELAY = 1  # Additional delay when rate limited
__BATCH_SIZE = 100  # Number of records to process in each batch
__CHECKPOINT_INTERVAL = 50  # Checkpoint every N records for large datasets
__DISCORD_API_MAX_MEMBERS_LIMIT = 1000  # Max members per request as per Discord API

# Discord API base URL
__DISCORD_API_BASE = "https://discord.com/api/v10"


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.

    This function is called at the start of the update method to ensure that the
    connector has all necessary configuration values.

    Args:
        configuration: a dictionary that holds the configuration settings for the
            connector.

    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    # Validate required configuration parameters
    required_configs = ["bot_token"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")

    # Validate bot token is not empty
    bot_token = configuration.get("bot_token", "")
    if not bot_token:
        raise ValueError("Bot token cannot be empty")


def _normalize_bot_token(bot_token: str) -> str:
    """
    Normalize the bot token by adding the "Bot " prefix if needed.

    Args:
        bot_token: The raw bot token from configuration

    Returns:
        str: The normalized bot token with "Bot " prefix
    """
    if not bot_token.startswith("Bot "):
        log.info("Bot token missing prefix, adding 'Bot ' prefix automatically")
        return f"Bot {bot_token}"
    else:
        log.info("Bot token already has proper prefix")
        return bot_token


def get_discord_headers(bot_token: str) -> dict:
    """
    Create headers for Discord API requests.
    Args:
        bot_token: The Discord bot token for authentication
    Returns:
        dict: Headers dictionary for API requests
    """
    return {
        "Authorization": bot_token,
        "Content-Type": "application/json",
        "User-Agent": "Fivetran-Discord-Connector/1.0",
    }


def _handle_rate_limit(response: requests.Response, attempt: int) -> None:
    """
    Handle Discord API rate limit (429) responses.
    Args:
        response: The HTTP response with 429 status
        attempt: Current retry attempt number
    """
    retry_after = float(response.headers.get("Retry-After", __RATE_LIMIT_DELAY))
    log.warning(
        f"Rate limited. Waiting {retry_after} seconds before retry "
        f"(attempt {attempt + 1}/{__MAX_RETRIES})"
    )
    time.sleep(retry_after)


def _handle_retry_with_backoff(
    error_message: str, attempt: int, error_detail: Optional[str] = None
) -> None:
    """
    Handle retries with exponential backoff for API failures.
    Args:
        error_message: Description of the error that occurred
        attempt: Current retry attempt number
        error_detail: Additional error details to log on final attempt
    Raises:
        RuntimeError: If this is the final retry attempt
    """
    if attempt < __MAX_RETRIES - 1:
        delay = __BASE_DELAY * (2**attempt)
        log.warning(
            f"{error_message}, retrying in {delay} seconds "
            f"(attempt {attempt + 1}/{__MAX_RETRIES})"
        )
        time.sleep(delay)
    else:
        error_log = error_message
        if error_detail:
            error_log = f"{error_message}: {error_detail}"
        log.error(f"{error_log} after {__MAX_RETRIES} attempts")
        raise RuntimeError(f"{error_message} after {__MAX_RETRIES} attempts")


def make_discord_request(url: str, headers: dict, params: Optional[dict] = None) -> dict:
    """
    Make a request to the Discord API with retry logic and rate limit handling.
    Args:
        url: The Discord API endpoint URL
        headers: Headers for the request
        params: Query parameters for the request
    Returns:
        dict: JSON response from the API
    Raises:
        RuntimeError: If the API request fails after all retry attempts
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                _handle_rate_limit(response, attempt)
                continue
            elif response.status_code in [500, 502, 503, 504]:
                _handle_retry_with_backoff(
                    f"Server error {response.status_code}", attempt, response.text
                )
                continue
            else:
                log.error(f"Discord API error {response.status_code}: {response.text}")
                raise RuntimeError(f"Discord API returned {response.status_code}: {response.text}")

        except requests.exceptions.RequestException as e:
            _handle_retry_with_backoff(f"Request failed: {str(e)}", attempt)
            continue

    raise RuntimeError(f"Discord API request failed after {__MAX_RETRIES} attempts")


def fetch_user_guilds(headers: dict) -> List[dict]:
    """
    Fetch all guilds the bot has access to.
    Args:
        headers: Headers for the API request
    Returns:
        List[dict]: List of guild data from Discord API
    """
    url = f"{__DISCORD_API_BASE}/users/@me/guilds"
    result = make_discord_request(url, headers)
    return result if isinstance(result, list) else []


def filter_guilds(guilds: List[dict], configuration: dict) -> List[dict]:
    """
    Filter guilds based on configuration settings.
    Args:
        guilds: List of guild data from Discord API
        configuration: Configuration dictionary
    Returns:
        List[dict]: Filtered list of guilds to process
    """
    sync_all_guilds = configuration.get("sync_all_guilds", "true").lower() == "true"
    specific_guild_ids = configuration.get("guild_ids", "")
    exclude_guild_ids = configuration.get("exclude_guild_ids", "")

    if not sync_all_guilds and not specific_guild_ids:
        log.warning(
            "sync_all_guilds is false but no specific guild_ids provided. "
            "Processing all guilds."
        )
        return guilds

    # Parse specific guild IDs if provided
    specific_ids = set()
    if specific_guild_ids:
        specific_ids = {gid.strip() for gid in specific_guild_ids.split(",") if gid.strip()}

    # Parse excluded guild IDs if provided
    excluded_ids = set()
    if exclude_guild_ids:
        excluded_ids = {gid.strip() for gid in exclude_guild_ids.split(",") if gid.strip()}

    filtered_guilds = []
    for guild in guilds:
        guild_id = guild.get("id")
        if not guild_id:
            continue

        # Skip if in excluded list
        if guild_id in excluded_ids:
            log.info(f"Excluding guild: {guild.get('name', 'Unknown')} (ID: {guild_id})")
            continue

        # If specific guilds are specified, only include those
        if specific_ids and guild_id not in specific_ids:
            continue

        filtered_guilds.append(guild)

    log.info(
        f"Filtered {len(guilds)} guilds down to {len(filtered_guilds)} guilds " f"for processing"
    )
    return filtered_guilds


def fetch_guild_data(guild_id: str, headers: dict) -> dict:
    """
    Fetch guild (server) information from Discord API.
    Args:
        guild_id: The Discord guild ID
        headers: Headers for the API request
    Returns:
        dict: Guild data from Discord API
    """
    url = f"{__DISCORD_API_BASE}/guilds/{guild_id}"
    return make_discord_request(url, headers)


def fetch_guild_channels(guild_id: str, headers: dict) -> List[dict]:
    """
    Fetch all channels from a Discord guild.
    Args:
        guild_id: The Discord guild ID
        headers: Headers for the API request
    Returns:
        list: List of channel data from Discord API
    """
    url = f"{__DISCORD_API_BASE}/guilds/{guild_id}/channels"
    result = make_discord_request(url, headers)
    return result if isinstance(result, list) else []


def fetch_guild_members(
    guild_id: str, headers: dict, limit: int = __DISCORD_API_MAX_MEMBERS_LIMIT
) -> List[dict]:
    """
    Fetch guild members from Discord API.
    Args:
        guild_id: The Discord guild ID
        headers: Headers for the API request
        limit: Maximum number of members to fetch
    Returns:
        list: List of member data from Discord API
    """
    url = f"{__DISCORD_API_BASE}/guilds/{guild_id}/members"
    params = {
        "limit": min(limit, __DISCORD_API_MAX_MEMBERS_LIMIT)
    }  # Discord API max limit is 1000
    result = make_discord_request(url, headers, params)
    return result if isinstance(result, list) else []


def fetch_channel_messages(
    channel_id: str, headers: dict, after: Optional[str] = None, limit: int = __BATCH_SIZE
) -> List[dict]:
    """
    Fetch messages from a Discord channel.
    Args:
        channel_id: The Discord channel ID
        headers: Headers for the API request
        after: Message ID to fetch messages after (for pagination)
        limit: Maximum number of messages to fetch (max 100)
    Returns:
        list: List of message data from Discord API
    """
    url = f"{__DISCORD_API_BASE}/channels/{channel_id}/messages"
    params: Dict[str, Any] = {"limit": min(limit, __BATCH_SIZE)}  # Discord API max limit is 100
    if after:
        params["after"] = after

    result = make_discord_request(url, headers, params)
    return result if isinstance(result, list) else []


def _serialize_json_fields(data: dict, fields: List[str]) -> None:
    """
    Serialize specified fields to JSON if they exist in the data dictionary.
    Args:
        data: Dictionary to modify
        fields: List of field names to serialize to JSON
    """
    for field in fields:
        if data.get(field):
            data[field] = json.dumps(data[field])


def process_guild_data(guild_data: dict) -> dict:
    """
    Process and normalize guild data for Fivetran.
    Args:
        guild_data: Raw guild data from Discord API
    Returns:
        dict: Processed guild data
    """
    # Serialize nested objects that need JSON encoding
    _serialize_json_fields(guild_data, ["welcome_screen", "stickers"])

    # Add metadata fields
    guild_data["synced_at"] = datetime.now(timezone.utc).isoformat()

    return guild_data


def process_channel_data(channel_data: dict, guild_id: str) -> dict:
    """
    Process and normalize channel data for Fivetran.
    Args:
        channel_data: Raw channel data from Discord API
        guild_id: The Discord guild ID this channel belongs to
    Returns:
        dict: Processed channel data
    """
    # Add guild_id to associate channel with its guild
    channel_data["guild_id"] = guild_id

    # Serialize nested objects that need JSON encoding
    _serialize_json_fields(
        channel_data, ["permission_overwrites", "available_tags", "default_reaction_emoji"]
    )

    # Add metadata fields
    channel_data["synced_at"] = datetime.now(timezone.utc).isoformat()

    return channel_data


def process_member_data(member_data: dict, guild_id: str) -> dict:
    """
    Process and normalize member data for Fivetran.
    Args:
        member_data: Raw member data from Discord API
        guild_id: The Discord guild ID this member belongs to
    Returns:
        dict: Processed member data
    """
    # Flatten user data into member_data for easier querying
    user = member_data.pop("user", {})
    member_data["user_id"] = user.get("id")
    member_data["username"] = user.get("username")
    member_data["discriminator"] = user.get("discriminator")
    member_data["global_name"] = user.get("global_name")
    member_data["avatar"] = user.get("avatar")
    member_data["bot"] = user.get("bot", False)
    member_data["system"] = user.get("system", False)
    member_data["mfa_enabled"] = user.get("mfa_enabled", False)
    member_data["banner"] = user.get("banner")
    member_data["accent_color"] = user.get("accent_color")
    member_data["locale"] = user.get("locale")
    member_data["verified"] = user.get("verified", False)
    member_data["email"] = user.get("email")
    member_data["avatar_decoration"] = user.get("avatar_decoration")
    member_data["premium_type"] = user.get("premium_type")
    member_data["public_flags"] = user.get("public_flags")

    # Rename conflicting 'flags' field from user to avoid collision
    if "flags" in user:
        member_data["user_flags"] = user["flags"]

    # Rename member flags field to avoid confusion
    if "flags" in member_data:
        member_data["flags_member"] = member_data.pop("flags")

    # Add guild_id to associate member with its guild
    member_data["guild_id"] = guild_id

    # Serialize roles array
    _serialize_json_fields(member_data, ["roles"])

    # Add metadata fields
    member_data["synced_at"] = datetime.now(timezone.utc).isoformat()

    return member_data


def process_message_data(message_data: dict, channel_id: str) -> dict:
    """
    Process and normalize message data for Fivetran.
    Args:
        message_data: Raw message data from Discord API
        channel_id: The Discord channel ID this message belongs to
    Returns:
        dict: Processed message data
    """
    # Extract author_id from nested author object
    author = message_data.pop("author", {})
    message_data["author_id"] = author.get("id")

    # Add channel_id to associate message with its channel
    message_data["channel_id"] = channel_id

    # Serialize array and nested object fields that need JSON encoding
    json_fields = [
        "mentions",
        "mention_roles",
        "mention_channels",
        "attachments",
        "embeds",
        "reactions",
        "components",
        "sticker_items",
        "stickers",
        "activity",
        "application",
        "message_reference",
        "referenced_message",
        "interaction",
        "thread",
        "role_subscription_data",
    ]
    _serialize_json_fields(message_data, json_fields)

    # Add metadata fields
    message_data["synced_at"] = datetime.now(timezone.utc).isoformat()

    return message_data


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector
    delivers.

    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema

    Args:
        configuration: a dictionary that holds the configuration settings for the
            connector.
    """
    return [
        {"table": "guild", "primary_key": ["id"]},
        {"table": "channel", "primary_key": ["id"]},
        {"table": "member", "primary_key": ["user_id", "guild_id"]},
        {"table": "message", "primary_key": ["id"]},
    ]


def _process_channels(
    channels_data: List[dict], guild_id: str, processed_count: int, state: dict
) -> int:
    """
    Process and upsert all channels for a guild.
    Args:
        channels_data: List of channel data
        guild_id: The Discord guild ID
        processed_count: Current count of processed records
        state: Current state dictionary
    Returns:
        int: Updated count of processed records
    """
    for channel_data in channels_data:
        processed_channel = process_channel_data(channel_data, guild_id)
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted,
        op.upsert(table="channel", data=processed_channel)
        processed_count += 1

        if processed_count % __CHECKPOINT_INTERVAL == 0:
            # Save the progress by checkpointing the state. This is important for
            # ensuring that the sync process can resume from the correct position in
            # case of next sync or interruptions.
            op.checkpoint(state=state)
            log.info(f"Checkpointed at {processed_count} records")

    return processed_count


def _process_members(
    members_data: List[dict], guild_id: str, processed_count: int, state: dict
) -> int:
    """
    Process and upsert all members for a guild.
    Args:
        members_data: List of member data
        guild_id: The Discord guild ID
        processed_count: Current count of processed records
        state: Current state dictionary
    Returns:
        int: Updated count of processed records
    """
    for member_data in members_data:
        processed_member = process_member_data(member_data, guild_id)
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted,
        op.upsert(table="member", data=processed_member)
        processed_count += 1

        if processed_count % __CHECKPOINT_INTERVAL == 0:
            # Save the progress by checkpointing the state. This is important for
            # ensuring that the sync process can resume from the correct position in
            # case of next sync or interruptions.
            op.checkpoint(state=state)
            log.info(f"Checkpointed at {processed_count} records")

    return processed_count


def _process_channel_messages(
    channel: dict,
    guild_name: str,
    headers: dict,
    last_message_id: Optional[str],
    message_limit: int,
    processed_count: int,
    state: dict,
) -> tuple:
    """
    Process messages for a single channel with pagination.
    Args:
        channel: Channel data
        guild_name: Name of the guild
        headers: API request headers
        last_message_id: Last processed message ID for resumption
        message_limit: Maximum messages to fetch
        processed_count: Current count of processed records
        state: Current state dictionary
    Returns:
        tuple: (updated_processed_count, last_message_id, messages_fetched)
    """
    channel_id = channel["id"]
    channel_name = channel.get("name", "unknown")
    messages_fetched = 0

    log.info(f"Processing messages for channel: {channel_name} in guild: {guild_name}")

    while messages_fetched < message_limit:
        try:
            messages_data = fetch_channel_messages(
                channel_id,
                headers,
                after=last_message_id,
                limit=min(__BATCH_SIZE, message_limit - messages_fetched),
            )

            if not messages_data:
                break

            for message_data in messages_data:
                processed_message = process_message_data(message_data, channel_id)
                # The 'upsert' operation is used to insert or update data in the destination table.
                # The op.upsert method is called with two arguments:
                # - The first argument is the name of the table to upsert the data into.
                # - The second argument is a dictionary containing the data to be upserted,
                op.upsert(table="message", data=processed_message)
                processed_count += 1
                messages_fetched += 1
                last_message_id = message_data["id"]

                if processed_count % __CHECKPOINT_INTERVAL == 0:
                    # Save the progress by checkpointing the state. This is important for
                    # ensuring that the sync process can resume from the correct position in
                    # case of next sync or interruptions.
                    op.checkpoint(state=state)
                    log.info(f"Checkpointed at {processed_count} records")

            # If we got fewer messages than requested, we've reached the end
            if len(messages_data) < __BATCH_SIZE:
                break

        except Exception as e:
            log.warning(
                f"Error fetching messages for channel {channel_name} in "
                f"guild {guild_name}: {str(e)}"
            )
            break

    return processed_count, last_message_id, messages_fetched


def _process_guild_messages(
    channels_data: List[dict],
    guild_name: str,
    headers: dict,
    configuration: dict,
    processed_count: int,
    last_message_sync: dict,
    state: dict,
) -> int:
    """
    Process messages for all text channels in a guild.
    Args:
        channels_data: List of all channels
        guild_name: Name of the guild
        headers: API request headers
        configuration: Configuration dictionary
        processed_count: Current count of processed records
        last_message_sync: Dictionary tracking last message ID per channel
        state: Current state dictionary
    Returns:
        int: Updated count of processed records
    """
    sync_messages = configuration.get("sync_messages", "true").lower() == "true"
    if not sync_messages:
        return processed_count

    log.info(f"Fetching message data for guild: {guild_name}")
    text_channels = [
        ch for ch in channels_data if ch.get("type") in [0, 5]
    ]  # Text and news channels
    message_limit = int(configuration.get("message_limit", "1000"))

    for channel in text_channels:
        channel_id = channel["id"]
        channel_name = channel.get("name", "unknown")
        last_message_id = last_message_sync.get(channel_id)

        processed_count, last_message_id, messages_fetched = _process_channel_messages(
            channel,
            guild_name,
            headers,
            last_message_id,
            message_limit,
            processed_count,
            state,
        )

        last_message_sync[channel_id] = last_message_id
        log.info(
            f"Processed {messages_fetched} messages for channel: "
            f"{channel_name} in guild: {guild_name}"
        )

    return processed_count


def process_single_guild(
    guild_data: dict, headers: dict, configuration: dict, state: dict
) -> dict:
    """
    Process a single guild and return updated state.
    Args:
        guild_data: Guild data from Discord API
        headers: Headers for API requests
        configuration: Configuration dictionary
        state: Current state dictionary
    Returns:
        dict: Updated state for this guild
    """
    guild_id = guild_data.get("id")
    guild_name = guild_data.get("name", "Unknown")

    log.info(f"Processing guild: {guild_name} (ID: {guild_id})")

    # Get guild-specific state
    guild_state = state.get("guilds", {}).get(guild_id, {})
    last_message_sync = guild_state.get("last_message_sync", {})
    processed_count = 0

    try:
        # Process guild data
        processed_guild = process_guild_data(guild_data)
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted,
        op.upsert(table="guild", data=processed_guild)
        processed_count += 1
        log.info(f"Processed guild: {processed_guild['name']}")

        # Fetch and process channels
        log.info(f"Fetching channel data for guild: {guild_name}")
        channels_data = fetch_guild_channels(guild_id, headers)
        processed_count = _process_channels(channels_data, guild_id, processed_count, state)
        log.info(f"Processed {len(channels_data)} channels for guild: {guild_name}")

        # Fetch and process members
        log.info(f"Fetching member data for guild: {guild_name}")
        members_data = fetch_guild_members(guild_id, headers)
        processed_count = _process_members(members_data, guild_id, processed_count, state)
        log.info(f"Processed {len(members_data)} members for guild: {guild_name}")

        # Fetch and process messages
        processed_count = _process_guild_messages(
            channels_data,
            guild_name,
            headers,
            configuration,
            processed_count,
            last_message_sync,
            state,
        )

        # Return updated guild state
        return {
            "last_message_sync": last_message_sync,
            "processed_count": processed_count,
            "last_sync_time": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        log.error(f"Error processing guild {guild_name} (ID: {guild_id}): {str(e)}")
        raise


def _fetch_and_filter_guilds(headers: dict, configuration: dict) -> List[dict]:
    """
    Fetch all guilds and filter based on configuration.
    Args:
        headers: API request headers
        configuration: Configuration dictionary
    Returns:
        List[dict]: Filtered list of guilds to process
    """
    log.info("Fetching all guilds the bot has access to")
    all_guilds = fetch_user_guilds(headers)
    log.info(f"Found {len(all_guilds)} guilds the bot has access to")

    guilds_to_process = filter_guilds(all_guilds, configuration)
    log.info(f"Processing {len(guilds_to_process)} guilds after filtering")

    return guilds_to_process


def _process_single_guild_with_error_handling(
    guild_data: dict,
    headers: dict,
    configuration: dict,
    state: dict,
    guilds_state: dict,
) -> int:
    """
    Process a single guild with error handling and state updates.
    Args:
        guild_data: Guild data from Discord API
        headers: API request headers
        configuration: Configuration dictionary
        state: Current state dictionary
        guilds_state: Dictionary to accumulate guild states
    Returns:
        int: Number of records processed for this guild
    """
    guild_id = guild_data.get("id")
    guild_name = guild_data.get("name", "Unknown")

    try:
        log.info(f"Starting processing of guild: {guild_name} (ID: {guild_id})")

        # Process this guild
        guild_state = process_single_guild(guild_data, headers, configuration, state)

        # Update guild-specific state
        guilds_state[guild_id] = guild_state
        records_processed = guild_state.get("processed_count", 0)

        log.info(f"Completed processing guild: {guild_name} - {records_processed} records")

        # Save the progress by checkpointing the state. This is important for
        # ensuring that the sync process can resume from the correct position in
        # case of next sync or interruptions.
        op.checkpoint(state=guild_state)

        return records_processed

    except Exception as e:
        log.error(f"Failed to process guild {guild_name} (ID: {guild_id}): {str(e)}")
        # Continue with other guilds even if one fails
        return 0


def _process_all_guilds(
    guilds_to_process: List[dict],
    headers: dict,
    configuration: dict,
    state: dict,
    guilds_state: dict,
) -> int:
    """
    Process all guilds and track total records processed.
    Args:
        guilds_to_process: List of guilds to process
        headers: API request headers
        configuration: Configuration dictionary
        state: Current state dictionary
        guilds_state: Dictionary to accumulate guild states
    Returns:
        int: Total number of records processed across all guilds
    """
    total_processed_count = 0

    for guild_data in guilds_to_process:
        records_processed = _process_single_guild_with_error_handling(
            guild_data, headers, configuration, state, guilds_state
        )
        total_processed_count += records_processed

    return total_processed_count


def _finalize_sync(
    guilds_state: dict, total_processed_count: int, num_guilds: int, state: dict
) -> None:
    """
    Finalize the sync by updating global state and checkpointing.
    Args:
        guilds_state: Final guild states
        total_processed_count: Total records processed
        num_guilds: Number of guilds processed
        state: Current state dictionary to update
    """
    # Update the original state dictionary with final values
    state["last_sync_time"] = datetime.now(timezone.utc).isoformat()
    state["guilds"] = guilds_state
    state["total_processed_count"] = total_processed_count

    # Save the progress by checkpointing the state. This is important for
    # ensuring that the sync process can resume from the correct position in
    # case of next sync or interruptions.
    op.checkpoint(state=state)
    log.info(
        f"Discord Connector: Multi-guild sync completed successfully. "
        f"Processed {total_processed_count} total records across {num_guilds} guilds"
    )


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by
    Fivetran during each sync.

    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: Connectors - Discord API Example")

    # Validate the configuration to ensure it contains all required values
    validate_configuration(configuration=configuration)

    # Extract and normalize configuration parameters
    raw_bot_token = configuration.get("bot_token", "")
    bot_token = _normalize_bot_token(raw_bot_token)

    # Get state variables for multi-guild sync
    guilds_state = state.get("guilds", {})

    try:
        # Create headers for Discord API requests
        headers = get_discord_headers(bot_token)

        # Fetch all guilds to process and filter based on configuration
        guilds_to_process = _fetch_and_filter_guilds(headers, configuration)

        if not guilds_to_process:
            log.warning("No guilds to process after filtering")
            return

        # Process all guilds
        total_processed_count = _process_all_guilds(
            guilds_to_process, headers, configuration, state, guilds_state
        )

        # Finalize the sync
        _finalize_sync(guilds_state, total_processed_count, len(guilds_to_process), state)

    except Exception as e:
        log.error(f"Discord Connector: Multi-guild sync failed with error: {str(e)}")
        raise RuntimeError(f"Failed to sync Discord data: {str(e)}")


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run
# directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not
# called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying
# your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
