"""Bounded binary reads and date decoding for Swiss-Manager files."""

from datetime import date

from .models import PartialDate


class SwissManagerDecodeError(ValueError):
    """Malformed data or an unsupported Swiss-Manager binary layout."""


class _Reader:
    def __init__(self, data: bytes, start: int, end: int) -> None:
        self.data = data
        self.position = start
        self.end = end

    def read(self, size: int) -> bytes:
        start = self.position
        if start + size > self.end:
            raise SwissManagerDecodeError(f"Truncated record at byte {start}: need {size} bytes")
        self.position += size
        return self.data[start : self.position]

    def strings(self, count: int) -> tuple[str, ...]:
        fields = []
        for _ in range(count):
            size = int.from_bytes(self.read(2), "little") * 2
            start = self.position
            value = self.read(size)
            try:
                fields.append(value.decode("utf-16-le"))
            except UnicodeDecodeError as exc:
                raise SwissManagerDecodeError(f"Invalid UTF-16 text at byte {start}") from exc
        return tuple(fields)


def _partial_date(value: int) -> PartialDate | None:
    if value == 0:
        return None
    year, remainder = divmod(value, 10000)
    month, day = divmod(remainder, 100)
    try:
        if day and not month:
            raise ValueError("day without month")
        date(year, month or 1, day or 1)
    except ValueError as exc:
        raise SwissManagerDecodeError(f"Invalid date value {value}") from exc
    return PartialDate(year, month or None, day or None)


def _date(value: int) -> date | None:
    partial = _partial_date(value)
    if partial is None:
        return None
    if partial.month is None or partial.day is None:
        raise SwissManagerDecodeError(f"Incomplete scheduled date {value}")
    return date(partial.year, partial.month, partial.day)
