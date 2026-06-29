"""
Google Trends Connector Configuration

Edit this file to configure your searches.
Each search group is normalized independently.
"""

SEARCHES = [
    {
        "name": "ETL Tools Comparison",
        "keywords": ["Fivetran", "Open Data Infrastructure"],
        "regions": [
            {"name": "Worldwide", "code": ""},
            {"name": "United States", "code": "US"},
        ],
        "timeframe": "2024-01-01 today",
    }
]
