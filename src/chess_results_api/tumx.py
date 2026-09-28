"""Decode the binary TUMX layout observed in the 2026 Open Olympiad fixture.

This is an experimental, reverse-engineered reader, not a Swiss-Manager format
specification. Strings have a uint16 count of UTF-16 code units followed by
little-endian UTF-16. Numeric fields are little-endian. Unknown fields and
pairing/result sections are preserved without assigning them semantics.
"""

from dataclasses import dataclass
from itertools import pairwise
from os import PathLike
from pathlib import Path
from struct import unpack_from

_MAGIC = b"\x93\xff\x89\x44"
_DIRECTORY = b"\xd3\xff\x89\x44"
_END = b"\xe3\xff\x89\x44"
_SECTION_MARKERS = (0xA3, 0xA5, 0xB3, 0xB5, 0xC3)
_SECTION_NAMES = ("schedule", "players", "player_pairings", "teams", "team_pairings")


class TumxDecodeError(ValueError):
    """The input is truncated, malformed, or uses an unsupported TUMX layout."""


@dataclass(frozen=True, slots=True)
class TournamentMetadata:
    """Recognized tournament text; all 26 text fields remain available by index."""

    name: str
    section: str
    remarks: str
    organizer: str
    location: str
    time_control: str
    federation: str
    chief_arbiter: str
    website: str
    text_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Player:
    """Player record; team_number is a one-based index into Tournament.teams.

    Zero ratings and FIDE IDs are retained as stored, rather than imputed.
    Record order is not a ranking or a starting-number ordering.
    """

    last_name: str
    first_name: str
    display_name: str
    title: str
    federation: str
    rating: int
    fide_id: int
    team_number: int
    board_number: int


@dataclass(frozen=True, slots=True)
class Team:
    """A team in file order; its one-based position is its team number."""

    name: str
    display_name: str
    captain: str
    federation: str
    group: str


@dataclass(frozen=True, slots=True)
class RawSection:
    """An exact file slice, including its marker, at an absolute byte offset."""

    name: str
    offset: int
    data: bytes


@dataclass(frozen=True, slots=True)
class Tournament:
    """Decoded records and losslessly retained sections in file order."""

    tournament_id: int
    metadata: TournamentMetadata
    players: tuple[Player, ...]
    teams: tuple[Team, ...]
    sections: tuple[RawSection, ...]


class _Reader:
    def __init__(self, data: bytes, start: int, end: int) -> None:
        self.data = data
        self.position = start
        self.end = end

    def read(self, size: int) -> bytes:
        start = self.position
        if start + size > self.end:
            raise TumxDecodeError(f"Truncated record at byte {start}: need {size} bytes")
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
                raise TumxDecodeError(f"Invalid UTF-16 text at byte {start}") from exc
        return tuple(fields)


def load_tumx(path: str | PathLike[str]) -> Tournament:
    """Read a local TUMX file; filesystem errors propagate unchanged."""
    return decode_tumx(Path(path).read_bytes())


def decode_tumx(data: bytes) -> Tournament:
    """Decode bytes using the observed TUMX layout.

    Raises TumxDecodeError for invalid boundaries, text, or section markers.
    Pairings and scores are available only as raw sections in this version.
    No filename, network connection, or optional dependency is required.
    """
    if len(data) < 144 or not data.startswith(_MAGIC):
        raise TumxDecodeError("Missing TUMX header or truncated file")
    directory = len(data) - 36
    if data[directory : directory + 4] != _DIRECTORY or data[-4:] != _END:
        raise TumxDecodeError("Missing TUMX directory or end marker")
    offsets = unpack_from("<7I", data, directory + 4)
    if offsets[5] != directory or offsets[6] != 0:
        raise TumxDecodeError("Unsupported TUMX directory layout")
    boundaries = (*offsets[:5], directory)
    if boundaries[0] <= 108 or any(a >= b for a, b in pairwise(boundaries)):
        raise TumxDecodeError("Invalid TUMX section offsets")
    for offset, marker in zip(boundaries[:-1], _SECTION_MARKERS, strict=True):
        if data[offset : offset + 4] != bytes((marker, 0xFF, 0x89, 0x44)):
            raise TumxDecodeError(f"Unexpected TUMX section marker at byte {offset}")

    reader = _Reader(data, 108, boundaries[0])
    fields = reader.strings(26)
    # The observed header contains 212 reserved bytes after its text fields.
    reader.read(212)
    configuration = reader.position
    if reader.read(4) != b"\x95\xff\x89\x44":
        raise TumxDecodeError("Unsupported TUMX header layout")
    metadata = TournamentMetadata(
        name=fields[0],
        section=fields[1],
        remarks=fields[2],
        organizer=fields[4],
        location=fields[5],
        time_control=fields[14],
        federation=fields[20],
        chief_arbiter=fields[21],
        website=fields[24],
        text_fields=fields,
    )

    players = []
    reader = _Reader(data, boundaries[1] + 4, boundaries[2])
    while reader.position < reader.end:
        fields = reader.strings(18)
        # Fixed tail includes reserved fields; only identified values are exposed.
        tail = reader.read(134)
        players.append(
            Player(
                last_name=fields[0],
                first_name=fields[1],
                display_name=fields[3],
                title=fields[4],
                federation=fields[10],
                rating=unpack_from("<H", tail, 32)[0],
                fide_id=unpack_from("<I", tail, 48)[0],
                team_number=unpack_from("<H", tail, 52)[0],
                board_number=unpack_from("<H", tail, 54)[0],
            )
        )

    teams = []
    reader = _Reader(data, boundaries[3] + 4, boundaries[4])
    while reader.position < reader.end:
        fields = reader.strings(5)
        reader.read(96)
        teams.append(Team(*fields))

    starts = (0, configuration, *boundaries, len(data))
    names = ("header", "configuration", *_SECTION_NAMES, "directory")
    sections = tuple(
        RawSection(name, start, data[start:end])
        for name, (start, end) in zip(names, pairwise(starts), strict=True)
    )
    return Tournament(
        tournament_id=unpack_from("<I", data, 32)[0],
        metadata=metadata,
        players=tuple(players),
        teams=tuple(teams),
        sections=sections,
    )
