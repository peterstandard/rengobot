"""Game state model and persistence manager for state.txt."""

from dataclasses import dataclass, field
import ast
import os

STATE_FILE: str = "state.txt"

@dataclass
class GameState:
    """Represents the in-memory and persisted state of an active Rengo game."""
    game_key: str
    gametype: str
    last_players: list[int] = field(default_factory=list)
    last_times: list[str] = field(default_factory=list)
    data: list = field(default_factory=lambda: [[], []])

    def to_tuple(self) -> tuple:
        """Converts to the backward-compatible tuple stored in state.txt."""
        return (self.game_key, self.gametype, self.last_players, self.last_times, self.data)

    @classmethod
    def from_tuple(cls, t: tuple) -> "GameState":
        """Instantiates GameState from a legacy tuple."""
        key = str(t[0])
        mode = str(t[1])
        players = list(t[2]) if len(t) > 2 else []
        times = list(t[3]) if len(t) > 3 else []
        extra = list(t[4]) if len(t) > 4 else [[], []]
        return cls(game_key=key, gametype=mode, last_players=players, last_times=times, data=extra)

def get_game_key(ctx) -> str:
    """Returns the composite game key '{guild_id}_{channel_id}'.
    Automatically migrates any legacy '{channel_id}.sgf' files on disk.
    """
    channel_id = ctx.channel.id
    if ctx.guild:
        combined = f"{ctx.guild.id}_{channel_id}"
        legacy_sgf = f"{channel_id}.sgf"
        combined_sgf = f"{combined}.sgf"
        if os.path.exists(legacy_sgf) and not os.path.exists(combined_sgf):
            try:
                os.rename(legacy_sgf, combined_sgf)
                if os.path.exists(f"{channel_id}.png"):
                    os.rename(f"{channel_id}.png", f"{combined}.png")
                print(f"[RengoBot] Migrated legacy game {legacy_sgf} -> {combined_sgf}")
            except Exception as e:
                print(f"[RengoBot] Error migrating legacy game files: {e}")
        return combined
    return str(channel_id)

def load_all_games() -> list[GameState]:
    """Loads all active games from state.txt."""
    if not os.path.exists(STATE_FILE):
        return []
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            raw_tuples = ast.literal_eval(content)
            return [GameState.from_tuple(t) for t in raw_tuples]
    except Exception as e:
        print(f"[RengoBot] Error reading {STATE_FILE}: {e}")
        return []

def save_all_games(games: list[GameState]) -> None:
    """Saves all active games to state.txt in backward-compatible tuple format."""
    try:
        raw = [g.to_tuple() for g in games]
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write(repr(raw))
    except Exception as e:
        print(f"[RengoBot] Error writing {STATE_FILE}: {e}")

def get_game(ctx) -> GameState | None:
    """Finds the active GameState for the given Discord context."""
    channel_id = str(ctx.channel.id)
    game_key = get_game_key(ctx)
    games = load_all_games()
    for g in games:
        if g.game_key in (channel_id, game_key):
            # Normalize legacy channel key to combined key
            if g.game_key == channel_id:
                g.game_key = game_key
            return g
    return None

def save_game(game: GameState) -> None:
    """Updates or appends an active GameState in state.txt."""
    games = load_all_games()
    found = False
    for i, g in enumerate(games):
        if g.game_key == game.game_key:
            games[i] = game
            found = True
            break
    if not found:
        games.append(game)
    save_all_games(games)

def remove_game(game_key: str) -> GameState | None:
    """Removes a game by game_key from state.txt. Returns the removed GameState if found."""
    games = load_all_games()
    removed = None
    new_games = []
    for g in games:
        if g.game_key == game_key:
            removed = g
        else:
            new_games.append(g)
    if removed:
        save_all_games(new_games)
    return removed
