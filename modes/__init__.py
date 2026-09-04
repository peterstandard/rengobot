"""Game mode registry and factory."""

from modes.base import BaseGameMode
from modes.casual import AnarchyMode, DebugMode, RandomMode
from modes.team import QueueMode, TeachersMode
from modes.vote import VoteMode, check_vote_timers, format_vote_summary, get_turn_header, load_votes

_RANDOM = RandomMode()
_ANARCHY = AnarchyMode()
_DEBUG = DebugMode()
_QUEUE = QueueMode()
_TEACHERS = TeachersMode()
_VOTE = VoteMode()

REGISTRY: dict[str, BaseGameMode] = {
	"random": _RANDOM,
	"anarchy": _ANARCHY,
	"debug": _DEBUG,
	"queue": _QUEUE,
	"teachers": _TEACHERS,
	"vote": _VOTE,
	"voting": _VOTE,
}


def get_mode(mode_name: str) -> BaseGameMode | None:
	"""Returns the game mode instance corresponding to mode_name."""
	if not mode_name:
		return None
	return REGISTRY.get(mode_name.strip().lower())


def is_valid_mode(mode_name: str) -> bool:
	"""Checks if mode_name is a registered game mode."""
	if not mode_name:
		return False
	return mode_name.strip().lower() in REGISTRY


__all__ = [
	"BaseGameMode",
	"RandomMode",
	"AnarchyMode",
	"DebugMode",
	"QueueMode",
	"TeachersMode",
	"VoteMode",
	"get_mode",
	"is_valid_mode",
	"check_vote_timers",
	"format_vote_summary",
	"load_votes",
	"get_turn_header",
]
