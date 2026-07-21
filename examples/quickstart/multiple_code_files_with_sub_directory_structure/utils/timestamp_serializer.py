from datetime import datetime, timezone


class TimestampSerializer:
    """
    This class allows you to parse timestamp strings in two specific formats
    This class also converts them into a standardized ISO 8601 format which is widely recommended, including by Fivetran
    This class assumes that the incoming timestamps are in UTC timezone.
    """

    # Define the acceptable formats for the timestamp
    TIMESTAMP_FORMATS = [
        "%Y/%m/%d %H:%M:%S",  # yyyy/MM/dd HH:mm:ss
        "%Y-%m-%d %H:%M:%S",  # yyyy-MM-dd HH:mm:ss
    ]

    @classmethod
    def parse_timestamp(cls, timestamp_str):
        # Try to parse the timestamp using the known formats
        for fmt in cls.TIMESTAMP_FORMATS:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                # If the format doesn't match, continue to try the next format
                continue
        raise ValueError(f"Timestamp format not recognized: {timestamp_str}")

    @classmethod
    def serialize(cls, timestamp):

        # Process the timestamp field
        # Parse the timestamp using the custom logic and add UTC timezone
        parsed_timestamp = cls.parse_timestamp(timestamp).replace(tzinfo=timezone.utc)

        # Optionally, reformat the timestamp to a standardized format (Fivetran recommends ISO 8601 format)
        formatted_timestamp = parsed_timestamp.isoformat()

        # Return the formatted timestamp
        return formatted_timestamp
