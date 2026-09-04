"""Casual and open game modes: Random, Anarchy, and Debug."""

from datetime import datetime
from config import MIN_TIME_PLAYER, TIME_FORMAT
from state import GameState, save_game
from modes.base import BaseGameMode

class RandomMode(BaseGameMode):
    """Community casual mode. Players alternate moves with cooldown and anti-consecutive limits."""
    name: str = "random"
    description: str = "Open to all! No queue; players alternate moves with cooldown limits."

    async def validate_player_turn(self, ctx, game: GameState, next_colour: int) -> tuple[bool, str | None]:
        user_id = ctx.author.id

        # No two consecutive moves by the same player
        if len(game.last_players) > 0 and game.last_players[-1] == user_id:
            return False, "No two consecutive moves by the same player!"

        # No two consecutive same-color moves by the same player
        if len(game.last_players) > 1 and game.last_players[-2] == user_id:
            return False, "No two consecutive same-color moves by the same player!"

        # Cooldown check
        for j in range(len(game.last_players)):
            if game.last_players[j] == user_id:
                played_time = datetime.strptime(game.last_times[j], TIME_FORMAT)
                if datetime.now() - played_time < MIN_TIME_PLAYER:
                    return False, "At most one move per player per day!"

        return True, None

class AnarchyMode(BaseGameMode):
    """Open to everyone in the channel with no turn, consecutive-play, or color limits."""
    name: str = "anarchy"
    description: str = "Open to all! No queue and no consecutive-play or color limits."

    async def validate_player_turn(self, ctx, game: GameState, next_colour: int) -> tuple[bool, str | None]:
        # Anarchy: any player can play any move at any time
        return True, None

class DebugMode(BaseGameMode):
    """Testing mode for developers/admins to test moves and bypass all anti-spam and edit timers."""
    name: str = "debug"
    description: str = "Solo testing mode. Bypasses anti-spam, player restrictions, and edit timers."

    async def validate_player_turn(self, ctx, game: GameState, next_colour: int) -> tuple[bool, str | None]:
        return True, None

    async def validate_cooldown(self, ctx, game: GameState) -> tuple[bool, str | None]:
        # Debug mode ignores anti-spam
        return True, None

    async def on_edit(self, ctx, game: GameState, move_str: str) -> None:
        """Allows editing anytime without the 5-minute or last-player restriction."""
        user = ctx.author
        clean_move = move_str.strip()
        import sgfengine
        from ui import format_game_message
        try:
            sgfengine.play_move(game.game_key, clean_move, user.display_name, overwrite=True)
        except ValueError as e:
            await ctx.send(str(e))
            return

        save_game(game)
        next_col = sgfengine.next_colour(game.game_key)
        player_text, ping_text = await self.get_next_player_info(ctx, game, next_col)
        file, msg = format_game_message(
            game.game_key,
            game,
            next_player_display=player_text,
            ping_mention=ping_text,
            title_override=f"Move Edited: {clean_move.upper()}"
        )
        await ctx.send(content=msg, file=file)
