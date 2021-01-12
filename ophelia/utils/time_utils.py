"""Time utils module."""

from datetime import datetime

import pytz


def to_utc_datetime(timestamp: int) -> datetime:
    """
    Convert UNIX timestamp to timezone aware UTC datetime.

    :param timestamp: UNIX timestamp with seconds accuracy
    :return: Timezone aware datetime
    """
    return pytz.utc.localize(datetime.utcfromtimestamp(timestamp))


def to_embed_timestamp(timestamp: int) -> datetime:
    """
    Convert UNIX timestamp to datetime object for embed timestamps.

    :param timestamp: UNIX timestamp with seconds accuracy.
    :return: Timezone native datetime
    """
    return datetime.utcfromtimestamp(timestamp)


def utc_time_now() -> datetime:
    """
    Get current UTC timezone aware time.

    :return: Timezone aware datetime
    """
    return pytz.utc.localize(datetime.utcnow())
