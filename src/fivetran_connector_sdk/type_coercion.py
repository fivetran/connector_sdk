import json
import math

from datetime import datetime, date
from google.protobuf import timestamp_pb2

from fivetran_connector_sdk.constants import JAVA_LONG_MAX_VALUE
from fivetran_connector_sdk.protos import common_pb2

_DT = common_pb2.DataType

_NULL_V     = b'\x00'
_PFX_SCALAR = b'\x01'
_PFX_JSON   = b'\x02'
_PFX_BINARY = b'\x03'
_PFX_FLOAT  = b'\x04'
_PFX_DOUBLE = b'\x05'


def _parse_utc_datetime_str(v):
    """
    Accepts a timezone-aware datetime object or a datetime string in one of the following formats:
    - '%Y-%m-%dT%H:%M:%S.%f%z' (e.g., '2025-08-12T15:00:00.123456+00:00')
    - '%Y-%m-%dT%H:%M:%S%z'    (e.g., '2025-08-12T15:00:00+00:00')
    - Same as above formats but with a space instead of 'T' as the separator (e.g., '2025-08-12 15:00:00+00:00')

    Returns a `google.protobuf.timestamp_pb2.Timestamp` object.
    """
    timestamp = timestamp_pb2.Timestamp()
    dt = v
    if not isinstance(v, datetime):
        dt = dt.strip().replace(' ', 'T', 1)
        dt = datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S.%f%z" if '.' in dt else "%Y-%m-%dT%H:%M:%S%z")
    timestamp.FromDatetime(dt)
    return timestamp


def _parse_naive_datetime_str(v):
    """
    Accepts a datetime.datetime object or naive datetime string in one of the following formats:
    - '%Y-%m-%dT%H:%M:%S.%f'
    - '%Y-%m-%d %H:%M:%S.%f'
    Returns a `google.protobuf.timestamp_pb2.Timestamp` object.
    """
    timestamp = timestamp_pb2.Timestamp()
    dt = v
    if not isinstance(v, datetime):
        dt = dt.strip().replace(' ', 'T', 1)
        dt = datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S.%f" if '.' in dt else "%Y-%m-%dT%H:%M:%S")
    timestamp.FromDatetime(dt)
    return timestamp


def _parse_naive_date_str(v):
    """
    Accepts a `datetime.date` object or a date string ('YYYY-MM-DD'),
    Returns a `google.protobuf.timestamp_pb2.Timestamp` object.
    """
    timestamp = timestamp_pb2.Timestamp()
    if isinstance(v, str):
        dt = datetime.strptime(v, "%Y-%m-%d")
    elif isinstance(v, (datetime, date)):
        dt = datetime.combine(v if isinstance(v, date) else v.date(), datetime.min.time())
    else:
        raise TypeError(f"Expected str, datetime.date, or datetime.datetime, got {type(v)}")
    timestamp.FromDatetime(dt)
    return timestamp


def _coerce_boolean(v):
    if isinstance(v, (bool, int, float)):
        return _PFX_SCALAR, b"true" if v else b"false"
    if isinstance(v, str) and v in ("0", "1"):
        return _PFX_SCALAR, b"false" if v == "0" else b"true"
    raise TypeError(f"BOOLEAN column does not accept {type(v).__name__}")


def _coerce_integer(v):
    if isinstance(v, float) and not v.is_integer():
        raise TypeError(f"Integer column requires int, got {type(v).__name__}")
    return _PFX_SCALAR, str(int(v)).encode('utf-8')


def _coerce_float_type(v):
    fv = float(v)
    if math.isnan(fv):  return _PFX_FLOAT, b"NaN"
    if math.isinf(fv):  return _PFX_FLOAT, b"Infinity" if fv > 0 else b"-Infinity"
    return _PFX_FLOAT, str(fv).encode('utf-8')


def _coerce_double_type(v):
    fv = float(v)
    if math.isnan(fv):  return _PFX_DOUBLE, b"NaN"
    if math.isinf(fv):  return _PFX_DOUBLE, b"Infinity" if fv > 0 else b"-Infinity"
    return _PFX_DOUBLE, str(fv).encode('utf-8')


def _coerce_utc_datetime(v):
    if isinstance(v, date) and not isinstance(v, datetime):
        return _PFX_SCALAR, (v.isoformat() + "T00:00:00Z").encode('utf-8')
    ts = _parse_utc_datetime_str(v)
    return _PFX_SCALAR, ts.ToJsonString().encode('utf-8')


def _coerce_naive_datetime(v):
    if isinstance(v, date) and not isinstance(v, datetime):
        return _PFX_SCALAR, (v.isoformat() + "T00:00:00").encode('utf-8')
    ts = _parse_naive_datetime_str(v)
    return _PFX_SCALAR, ts.ToDatetime().isoformat().encode('utf-8')


def _coerce_naive_date(v):
    ts = _parse_naive_date_str(v)
    return _PFX_SCALAR, ts.ToDatetime().date().isoformat().encode('utf-8')


def _raise_unsupported_type(v):
    raise ValueError("Unsupported data type encountered. Please use valid data types.")


def _coerce_json(v):
    return _PFX_JSON, json.dumps(v).encode('utf-8')


def _coerce_string(v):
    s = v if isinstance(v, str) else str(v)
    return _PFX_SCALAR, s.encode('utf-8')


def _coerce_decimal(v):
    if isinstance(v, bool):
        raise TypeError("DECIMAL column does not accept bool")
    if isinstance(v, (str, int)):
        return _PFX_SCALAR, str(v).encode('utf-8')
    raise TypeError(f"DECIMAL column requires str or int, got {type(v).__name__}")


def _coerce_xml(v):
    if not isinstance(v, str):
        raise TypeError(f"XML column requires str, got {type(v).__name__}")
    return _PFX_SCALAR, v.encode('utf-8')


def _coerce_binary_type(v):
    if isinstance(v, (bytes, bytearray)):
        return _PFX_BINARY, bytes(v)
    raise TypeError(f"BINARY column requires bytes or bytearray, got {type(v).__name__}")


def _coerce_inferred(v):
    if isinstance(v, str):
        return _PFX_SCALAR, v.encode('utf-8')
    if isinstance(v, bool):
        return _PFX_SCALAR, b"true" if v else b"false"
    if isinstance(v, int):
        if abs(v) > JAVA_LONG_MAX_VALUE:
            return _coerce_float_type(v)
        return _PFX_SCALAR, str(v).encode('utf-8')
    if isinstance(v, float):
        return _coerce_float_type(v)
    if isinstance(v, bytes):
        return _PFX_BINARY, v
    if isinstance(v, (dict, list)):
        return _PFX_JSON, json.dumps(v).encode('utf-8')
    return _PFX_SCALAR, str(v).encode('utf-8')


_COERCE_FN_BY_TYPE = {
    _DT.BOOLEAN:        _coerce_boolean,
    _DT.SHORT:          _coerce_integer,
    _DT.INT:            _coerce_integer,
    _DT.LONG:           _coerce_integer,
    _DT.FLOAT:          _coerce_float_type,
    _DT.DOUBLE:         _coerce_double_type,
    _DT.DECIMAL:        _coerce_decimal,
    _DT.STRING:         _coerce_string,
    _DT.XML:            _coerce_xml,
    _DT.UTC_DATETIME:   _coerce_utc_datetime,
    _DT.NAIVE_DATETIME: _coerce_naive_datetime,
    _DT.NAIVE_DATE:     _coerce_naive_date,
    _DT.JSON:           _coerce_json,
    _DT.BINARY:         _coerce_binary_type,
    _DT.NAIVE_TIME:     _raise_unsupported_type,
}


def _encode_row_data(column_types: dict, data: dict) -> dict:
    row_data = {}
    for key, v in data.items():
        if v is None:
            row_data[key] = _NULL_V
        else:
            pfx, val_b = _COERCE_FN_BY_TYPE.get(column_types.get(key), _coerce_inferred)(v)
            row_data[key] = pfx + val_b
    return row_data
