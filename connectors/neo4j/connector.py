# This is an example for how to work with the fivetran_connector_sdk module.
# This example demonstrates how to create a connector that connects to a Neo4j database and syncs data from it.
# It uses the public twitter database available at neo4j+s://demo.neo4jlabs.com:7687.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details

# Import the required classes from the connector SDK
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Operations as op
from fivetran_connector_sdk import Logging as log

# Import necessary libraries
import json
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """

    # check if required configuration values are present in configuration
    for key in ["neo4j_uri", "username", "password", "database"]:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value : {key}")

    return [
        {
            "table": "user",  # Name of the table
            "primary_key": ["username"],  # Primary key(s) of the table
            "columns": {
                "username": "STRING",
            },
        },  # Columns not defined in schema will be inferred
        {
            "table": "tweet_hashtag",
            "primary_key": ["tweet_id"],
            "columns": {"tweet_id": "STRING"},
        },
    ]


def update(configuration, state):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """

    # Extract connection details from configuration
    neo4j_uri = configuration.get("neo4j_uri")
    username = configuration.get("username")
    password = configuration.get("password")
    database = configuration.get("database")
    driver = None

    try:
        # Create a neo4j driver instance
        driver = GraphDatabase.driver(neo4j_uri, auth=(username, password))
        # Verify connectivity before proceeding
        driver.verify_connectivity()
        log.info("Connected to Neo4j database successfully.")

        # Create a session to interact with the Neo4j database
        session = driver.session(database=database)

        # Upsert the users data from the Neo4j database
        process_users(session=session, state=state)

        # Upsert the tweet-hashtag relationships from the Neo4j database in batches
        process_tweet_hashtags(session=session, state=state, batch_size=500)

    except ServiceUnavailable as e:
        # Handle the case where the Neo4j database is unavailable
        raise RuntimeError(f"Neo4j database is unavailable: {e}")
    except AuthError as e:
        # Handle authentication errors
        raise RuntimeError(f"Authentication failed: {e}")
    except Exception as e:
        # Handle any other exceptions that may occur
        raise RuntimeError(f"Error connecting to Neo4j: {e}")
    finally:
        # Close the driver connection if it was created successfully
        if driver:
            driver.close()


def process_users(session, state):
    """
    This function fetches user data from the Neo4j database and performs upsert operations for each user.
    Args:
        session: The Neo4j session object
        state: The state dictionary
    """

    # Query to fetch user data
    # This query follows the structure of the Neo4j database and Cipher query language.
    # You can modify the query to suit your needs.
    cypher_query = """
    MATCH (u:User)
    RETURN
        u.followers as followers_count,
        u.screen_name as username,
        u.following as following_count,
        u.name as name,
        u.location as location,
        u.profile_image_url as profile_image_url,
        u.url as url,
        u.betweenness as betweenness
    LIMIT 100
    """

    results = session.execute_read(lambda tx: tx.run(cypher_query).data())

    # Process each user record
    for record in results:
        # You can preprocess and modify the record to suit your needs.
        # An upsert operation to insert/update the record in the "users" table.
        op.upsert(table="user", data=record)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


def process_tweet_hashtags(session, state, batch_size=100):
    """
    This function fetches tweet-hashtag relationships from the Neo4j database and performs upsert operations for each relationship.
    This is done in batches to avoid overwhelming the database and to manage memory usage.
    The function uses pagination to fetch data in chunks, which is useful for large datasets.
    Args:
        session: The Neo4j session object
        state: The state dictionary
        batch_size: The number of records to fetch in each batch
    """

    # Initialize variables for pagination
    skip = 0
    has_more = True

    # Loop until all tweet-hashtag relationships are processed
    while has_more:
        # Query to fetch tweet-hashtag relationships
        # You can modify the query to suit your needs.
        cypher_query = """
        MATCH (t:Tweet)-[r:TAGS]->(h:Hashtag)
        RETURN
            t.id as tweet_id,
            h.name as hashtag_name
        ORDER BY t.id, h.id
        SKIP $skip LIMIT $limit
        """
        # Parameters for pagination
        params = {"skip": skip, "limit": batch_size}

        # Execute the query and fetch results
        results = session.execute_read(
            lambda tx, query=cypher_query, parameters=params: list(tx.run(query, **parameters))
        )

        # Check if there are more results to process
        count = len(results)
        log.info(f"Fetched {count} tweet-hashtag relationships.")
        has_more = count == batch_size

        # Process each tweet-hashtag relationship record and upsert it
        for record in results:
            record = record.data()
            # An upsert operation
            op.upsert(table="tweet_hashtag", data=record)

        # skip the processed records
        skip += batch_size

        # Terminate the loop if no more records are available
        if not has_more:
            log.info("No more tweet-hashtag relationships to process.")
            has_more = False

    # Checkpoint after processing each batch
    op.checkpoint(state)


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
