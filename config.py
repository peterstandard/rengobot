"""Configuration and environment settings for RengoBot."""

import os
from datetime import timedelta

# Ensure Cargo/Rust binaries are on PATH for sgf-render and resvg
os.environ["PATH"] = os.path.expanduser("~/.cargo/bin") + os.pathsep + os.environ.get("PATH", "")


def load_env(env_path: str = ".env") -> None:
	"""Loads key-value pairs from a .env file into os.environ if not already set."""
	if os.path.exists(env_path):
		with open(env_path, "r", encoding="utf-8") as f:
			for line in f:
				line = line.strip()
				if line and not line.startswith("#") and "=" in line:
					key, val = line.split("=", 1)
					key = key.strip()
					val = val.strip().strip("'\"")
					if key not in os.environ:
						os.environ[key] = val


load_env()


def get_int_list(env_var: str, default: list[int] | None = None) -> list[int]:
	"""Parses a comma-separated string of integers from an environment variable."""
	val = os.environ.get(env_var)
	if val is not None:
		return [int(x.strip()) for x in val.split(",") if x.strip().isdigit()]
	return default if default is not None else []


# Game timing constants
TIME_FORMAT: str = "%Y_%m_%d_%H_%M_%S_%f"
MIN_TIME_PLAYER: timedelta = timedelta(seconds=1)  # Cooldown between moves by same player
TIME_TO_SKIP: timedelta = timedelta(seconds=1)  # Queue skip threshold
MIN_PLAYERS: int = 2  # Minimum players per team in queue games

# Global bot administrators (can manage games anywhere and trigger $shutdown)
ADMIN_IDS: list[int] = get_int_list("ADMIN_IDS", [])

# Authorized teacher IDs for teaching games
TEACHER_IDS: list[int] = get_int_list("TEACHER_IDS", [])

# Optional server & channel filtering (empty list permits all)
PERMITTED_SERVER_IDS: list[int] = get_int_list("PERMITTED_SERVER_IDS", [])
PERMITTED_CHANNEL_IDS: list[int] = get_int_list("PERMITTED_CHANNEL_IDS", [])

# Custom stone emojis (falls back to unicode circles if not set)
WHITE_STONE_EMOJI: str = os.environ.get("WHITE_STONE_EMOJI", "⚪")
BLACK_STONE_EMOJI: str = os.environ.get("BLACK_STONE_EMOJI", "⚫")

# Discord Token
DISCORD_TOKEN: str | None = os.environ.get("DISCORD_TOKEN")
if not DISCORD_TOKEN:
	if os.path.exists("token.txt"):
		with open("token.txt", "r", encoding="utf-8") as f:
			DISCORD_TOKEN = f.read().strip()
	else:
		raise ValueError("Discord token not found! Provide DISCORD_TOKEN in .env or token.txt")


def is_game_admin(ctx) -> bool:
	"""Checks if the command author is a global admin or has server admin/manage permissions."""
	if ctx.author.id in ADMIN_IDS:
		return True
	if ctx.guild and (
		ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild
	):
		return True
	return False
