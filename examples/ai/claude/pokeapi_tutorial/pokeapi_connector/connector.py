"""
PokeAPI connector for Fivetran Connector SDK
This connector fetches Pokémon data from the PokeAPI (https://pokeapi.co/docs/v2)
and loads it into the destination in Fivetran.
"""

import requests
from typing import Dict, Any, List
import time

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op


def schema(configuration: dict) -> List[Dict[str, Any]]:
    """
    Define the schema for the PokeAPI connector.

    Args:
        configuration: Configuration dictionary.

    Returns:
        List of table schema definitions.
    """
    return [
        {
            "table": "pokemon",
            "primary_key": ["id"],
            "columns": {
                "id": "INT",
                "name": "STRING",
                "height": "INT",
                "weight": "INT",
                "base_experience": "INT",
                "order": "INT",
                "is_default": "BOOLEAN",
                "species_id": "INT",
                "species_name": "STRING",
                "image_url": "STRING",
            },
        },
        {
            "table": "pokemon_types",
            "primary_key": ["pokemon_id", "type_id"],
            "columns": {
                "pokemon_id": "INT",
                "type_id": "INT",
                "type_name": "STRING",
                "slot": "INT",
            },
        },
        {
            "table": "pokemon_abilities",
            "primary_key": ["pokemon_id", "ability_id"],
            "columns": {
                "pokemon_id": "INT",
                "ability_id": "INT",
                "ability_name": "STRING",
                "is_hidden": "BOOLEAN",
                "slot": "INT",
            },
        },
        {
            "table": "pokemon_stats",
            "primary_key": ["pokemon_id", "stat_id"],
            "columns": {
                "pokemon_id": "INT",
                "stat_id": "INT",
                "stat_name": "STRING",
                "base_value": "INT",
                "effort": "INT",
            },
        },
    ]


def update(configuration: dict, state: dict):
    """
    Update function that fetches data from PokeAPI and yields operations for Fivetran.

    Args:
        configuration: Configuration dictionary containing any secrets or config.
        state: Dictionary containing checkpoint state from previous runs.

    Yields:
        Operations for Fivetran to process.
    """
    log.info("Starting PokeAPI connector sync")

    # Get limit from configuration or use default, convert string to int
    limit = int(configuration.get("limit", "100"))

    # Get the offset from state or start from 0
    offset = state.get("offset", 0)

    # Get the API base URL from configuration or use default
    api_base_url = configuration.get("api_base_url", "https://pokeapi.co/api/v2")

    # Respect rate limits - wait between requests, convert string to float
    request_delay = float(configuration.get("request_delay", "1.0"))  # in seconds

    # Track total processed
    processed_count = 0

    try:
        # Get the list of Pokémon
        pokemon_list_url = f"{api_base_url}/pokemon?offset={offset}&limit={limit}"
        log.info(f"Fetching Pokémon list from: {pokemon_list_url}")

        response = requests.get(pokemon_list_url)
        response.raise_for_status()
        pokemon_list_data = response.json()

        total_pokemon = pokemon_list_data.get("count", 0)
        log.info(f"Total Pokémon available: {total_pokemon}, processing from offset: {offset}")

        # Process each Pokémon
        for pokemon_entry in pokemon_list_data.get("results", []):
            name = pokemon_entry.get("name")
            pokemon_url = pokemon_entry.get("url")

            log.debug(f"Processing Pokémon: {name}")

            # Get detailed Pokémon data
            pokemon_response = requests.get(pokemon_url)
            time.sleep(request_delay)  # Respect rate limits

            if pokemon_response.status_code != 200:
                log.warning(
                    f"Failed to fetch details for Pokémon: {name}. Status code: {pokemon_response.status_code}"
                )
                continue

            pokemon_data = pokemon_response.json()
            pokemon_id = pokemon_data.get("id")

            # Extract species data
            species_url = pokemon_data.get("species", {}).get("url")
            species_id = None
            species_name = pokemon_data.get("species", {}).get("name")

            if species_url:
                # Extract species ID from URL
                species_id = int(species_url.rstrip("/").split("/")[-1])

            # Prepare main Pokémon data
            pokemon_record = {
                "id": pokemon_id,
                "name": name,
                "height": pokemon_data.get("height"),
                "weight": pokemon_data.get("weight"),
                "base_experience": pokemon_data.get("base_experience"),
                "order": pokemon_data.get("order"),
                "is_default": pokemon_data.get("is_default"),
                "species_id": species_id,
                "species_name": species_name,
                "image_url": pokemon_data.get("sprites", {}).get("front_default"),
            }

            # Yield the main Pokémon record
            yield op.upsert(table="pokemon", data=pokemon_record)

            # Process types
            for type_entry in pokemon_data.get("types", []):
                type_data = type_entry.get("type", {})
                type_id = int(type_data.get("url", "").rstrip("/").split("/")[-1])

                type_record = {
                    "pokemon_id": pokemon_id,
                    "type_id": type_id,
                    "type_name": type_data.get("name"),
                    "slot": type_entry.get("slot"),
                }
                yield op.upsert(table="pokemon_types", data=type_record)

            # Process abilities
            for ability_entry in pokemon_data.get("abilities", []):
                ability_data = ability_entry.get("ability", {})
                ability_id = int(ability_data.get("url", "").rstrip("/").split("/")[-1])

                ability_record = {
                    "pokemon_id": pokemon_id,
                    "ability_id": ability_id,
                    "ability_name": ability_data.get("name"),
                    "is_hidden": ability_entry.get("is_hidden"),
                    "slot": ability_entry.get("slot"),
                }
                yield op.upsert(table="pokemon_abilities", data=ability_record)

            # Process stats
            for stat_entry in pokemon_data.get("stats", []):
                stat_data = stat_entry.get("stat", {})
                stat_id = int(stat_data.get("url", "").rstrip("/").split("/")[-1])

                stat_record = {
                    "pokemon_id": pokemon_id,
                    "stat_id": stat_id,
                    "stat_name": stat_data.get("name"),
                    "base_value": stat_entry.get("base_stat"),
                    "effort": stat_entry.get("effort"),
                }
                yield op.upsert(table="pokemon_stats", data=stat_record)

            processed_count += 1

            # Checkpoint every 10 Pokémon to ensure data is saved
            if processed_count % 10 == 0:
                new_offset = offset + processed_count
                log.info(f"Checkpointing at offset: {new_offset}")
                yield op.checkpoint(state={"offset": new_offset})

        # Final checkpoint at the end
        new_offset = offset + processed_count

        # If we've processed all Pokémon, start over
        if new_offset >= total_pokemon:
            log.info("Completed processing all Pokémon. Resetting offset for next sync.")
            new_offset = 0

        log.info(f"Final checkpoint at offset: {new_offset}")
        yield op.checkpoint(state={"offset": new_offset})

    except Exception as e:
        log.error("Error during sync process", e)
        # Still checkpoint to avoid reprocessing the same data
        new_offset = offset + processed_count
        yield op.checkpoint(state={"offset": new_offset})


# Create the connector instance
connector = Connector(update=update, schema=schema)

# For local debugging
if __name__ == "__main__":
    connector.debug()
