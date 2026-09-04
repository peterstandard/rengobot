"""Discord user interface and message formatting helpers."""

import discord
import sgfengine
from config import WHITE_STONE_EMOJI, BLACK_STONE_EMOJI

async def get_player_display(guild, user_id: int) -> tuple[str, str]:
    """Retrieves a player's display name and mention string.
    Returns (display_name, mention_string).
    """
    if not guild:
        return f"Player {user_id}", f"<@{user_id}>"
    try:
        member = await guild.fetch_member(user_id)
        return member.display_name, member.mention
    except Exception:
        return f"Player {user_id}", f"<@{user_id}>"

def format_game_message(
    game_key: str,
    game_state=None,
    next_player_display: str | None = None,
    ping_mention: str | None = None,
    title_override: str | None = None,
) -> tuple[discord.File, str]:
    """Builds the board image attachment and formatted announcement message.
    Returns (discord.File, message_string).
    """
    info = sgfengine.get_game_state(str(game_key))
    if not info:
        return discord.File(f"{game_key}.png"), ""

    lines = []

    # Title / Last move header
    if title_override:
        lines.append(f"### {title_override}")
    elif info["last_move"]:
        move_colour = f"{BLACK_STONE_EMOJI} Black" if info["last_colour"] == "B" else f"{WHITE_STONE_EMOJI} White"
        player_str = f" ({info['last_player']})" if info['last_player'] else ""
        if info["last_move"] == "Pass":
            lines.append(f"### Move #{info['move_count']} • {move_colour}{player_str} Passed")
        else:
            lines.append(f"### Move #{info['move_count']} • {move_colour}{player_str} played `{info['last_move']}`")
    else:
        lines.append("### New Game Started")

    # Turn notification
    next_colour_name = "White" if info["next_colour"] == "W" else "Black"
    turn_emoji = WHITE_STONE_EMOJI if info["next_colour"] == "W" else BLACK_STONE_EMOJI
    if ping_mention:
        lines.append(f"{turn_emoji} **{next_colour_name}'s turn:** {ping_mention} ⭐")
    elif next_player_display:
        lines.append(f"{turn_emoji} **{next_colour_name}'s turn:** {next_player_display}")
    else:
        lines.append(f"{turn_emoji} **{next_colour_name}'s turn!**")

    # Captures & Game Info line
    ruleset_str = info.get("ruleset", "AGA")
    lines.append(
        f"**Captures:** {BLACK_STONE_EMOJI} `{info['captures']['B']}`  |  "
        f"{WHITE_STONE_EMOJI} `{info['captures']['W']}`  •  "
        f"**Info:** Ruleset `{ruleset_str}` | Komi `{info['komi']}` | Handicap `{info['handicap']}`"
    )

    # Game Over / Consecutive pass warnings
    if info.get("consecutive_passes", 0) >= 2:
        lines.append("⚠️ **Game Over:** Both players passed! Use `$resign <B/W>` to record the winner or `$sgf` for the game record.")
    elif info.get("consecutive_passes", 0) == 1:
        lines.append("ℹ️ *1 pass recorded. A second consecutive pass will end the game.*")

    file = discord.File(f"{game_key}.png")
    return file, "\n".join(lines)
