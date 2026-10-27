"""
Mock data for the Iceberg destination example.
Keep the sample data in its own file so the connector logic stays easy to read.
Replace these rows with data from your source system.
"""

# Each row has three columns: id (primary key), name, and amount.
__MOCK_ORDERS = [
    {"id": 1, "name": "Coffee beans", "amount": 18.50},
    {"id": 2, "name": "Espresso machine", "amount": 249.00},
    {"id": 3, "name": "Milk frother", "amount": 39.99},
    {"id": 4, "name": "Paper filters", "amount": 7.25},
    {"id": 5, "name": "Grinder", "amount": 129.00},
    {"id": 6, "name": "Cups set", "amount": 32.00},
    {"id": 7, "name": "Descaling kit", "amount": 15.75},
    {"id": 8, "name": "Tamper", "amount": 22.40},
    {"id": 9, "name": "Knock box", "amount": 45.00},
    {"id": 10, "name": "Scale", "amount": 58.90},
    {"id": 11, "name": "Cleaning brush", "amount": 6.50},
    {"id": 12, "name": "Gift card", "amount": 50.00},
]
