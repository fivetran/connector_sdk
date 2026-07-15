"""
This module simulates a single external API call that returns users with multiple nested
data structures.:

Pattern 1 — orders → flatten everything into a single flat table (one row per order, parent fields repeated)
Pattern 2 — orders (nested list)  → break into parent/child tables
Pattern 3 — orders      → write as JSON blob

In a real-world connector, replace get_users() with your actual API call or database
query logic. Add pagination, retry handling, and rate-limit backoff as needed.
"""

# Import Faker to generate realistic synthetic data for local testing and debugging.
from faker import Faker

# For enabling logs in your connector code.
from fivetran_connector_sdk import Logging as log

# Create a Faker instance to generate synthetic data.
fake = Faker()


def get_users():
    """
    Simulate a single API call that returns users, each containing a nested orders list.
    All three data handling patterns in connector.py are applied to this single response.

    The schema (field names and structure) is fixed. Only the values are randomized using
    Faker to simulate realistic variability across syncs.

    In a real-world connector, replace this with your actual API call or database query.
    Add pagination if your source returns results across multiple pages.
    Add retry logic with exponential backoff to handle transient API errors.

    Returns:
        A list of dictionaries, each representing a user with a nested orders list.
    """

    log.info("Making API call: fetching users with nested orders")
    users = []
    for _ in range(fake.random_int(min=2, max=6)):
        user_id = fake.uuid4()
        orders = [
            {
                "order_id": f"ORD-{j}",
                "amount": round(fake.pyfloat(min_value=10, max_value=500, right_digits=2), 2),
            }
            for j in range(fake.random_int(min=1, max=4))
        ]

        users.append(
            {
                "user_id": user_id,
                "name": fake.name(),
                # Nested orders list — each order becomes its own flat row in Pattern 1 (parent fields
                # repeated per row), split into a child table in Pattern 2, and stored as JSON in Pattern 3.
                "orders": orders,
            }
        )
    return users
