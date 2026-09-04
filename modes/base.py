"""Base class for all game modes defining standard behaviors and hooks."""

from datetime import datetime, timedelta
import os
import re
import discord

import sgfengine
from config import TIME_FORMAT
from state import GameState, save_game, remove_game
from ui import format_game_message

class BaseGameMode:
    """Abstract base strategy for a Rengo game mode.
    Subclasses override specific hooks to implement mode-specific rules.
    """
    name: str = "base"
    description: str = "Base game mode"

    async def on_new_game(self, ctx, game_key: str, *args) -> GameState:
        """Initializes a new game in this mode and saves it."""
        handicap = 0
        komi = 6.5
        if len(args) >= 1:
            try:
                handicap = int(args[0])
            except ValueError:
                handicap = 0
        if len(args) >= 2:
            try:
                komi = float(args[1])
            except ValueError:
                komi = 6.5

        sgfengine.new_game(game_key, handicap, komi)
        game = GameState(game_key=game_key, gametype=self.name, data=[[], []])
        save_game(game)

        title = f"New Game Started • {self.name.upper()} Mode"
        file, msg = format_game_message(game_key, game, title_override=title)
        msg += "\n*Play a move with `$play <move>`*"
        await ctx.send(content=msg, file=file)
        return game

    async def validate_player_turn(self, ctx, game: GameState, next_colour: int) -> tuple[bool, str | None]:
        """Validates whether the author is eligible to play on the current turn.
        Default: Anyone can play.
        """
        return True, None

    async def validate_cooldown(self, ctx, game: GameState) -> tuple[bool, str | None]:
        """Validates player move cooldowns and anti-spam."""
        user = ctx.author
        if game.last_times:
            last_time = datetime.strptime(game.last_times[-1], TIME_FORMAT)
            if datetime.now() - last_time < timedelta(seconds=4):
                last_move = sgfengine.get_last_move_formatted(game.game_key)
                dropped_msg = f"Last accepted move: {last_move}. Move dropped by anti-spam." if last_move else "Move dropped by anti-spam."
                return False, dropped_msg
        return True, None

    async def on_play(self, ctx, game: GameState, move_str: str) -> None:
        """Processes a played move."""
        user = ctx.author
        colour = sgfengine.next_colour(game.game_key)

        # 1. Player eligibility check
        allowed, err_msg = await self.validate_player_turn(ctx, game, colour)
        if not allowed:
            await ctx.send(err_msg or "It is not your turn!")
            return

        # 2. Anti-spam check
        allowed, err_msg = await self.validate_cooldown(ctx, game)
        if not allowed:
            await ctx.send(err_msg or "Move dropped by anti-spam.")
            return

        # 3. Coordinate validation
        clean_move = move_str.strip()
        legal, err = sgfengine.validate_move(game.game_key, clean_move)
        if not legal:
            await ctx.send(f"⚠️ {err}")
            return

        # 4. Play move on board
        try:
            sgfengine.play_move(game.game_key, clean_move, user.display_name)
        except ValueError as e:
            await ctx.send(str(e))
            return

        # 5. Record move in game state
        game.last_players.append(user.id)
        game.last_times.append(datetime.now().strftime(TIME_FORMAT))
        await self.after_move(ctx, game, colour, user.id)
        save_game(game)

        # 6. Post updated board and announcement
        next_col = sgfengine.next_colour(game.game_key)
        player_text, ping_text = await self.get_next_player_info(ctx, game, next_col)
        file, msg = format_game_message(game.game_key, game, next_player_display=player_text, ping_mention=ping_text)
        await ctx.send(content=msg, file=file)

    async def on_pass(self, ctx, game: GameState) -> None:
        """Processes a pass turn."""
        user = ctx.author
        colour = sgfengine.next_colour(game.game_key)

        allowed, err_msg = await self.validate_player_turn(ctx, game, colour)
        if not allowed:
            await ctx.send(err_msg or "It is not your turn!")
            return

        allowed, err_msg = await self.validate_cooldown(ctx, game)
        if not allowed:
            await ctx.send(err_msg or "Pass dropped by anti-spam.")
            return

        sgfengine.play_pass(game.game_key, user.display_name)

        game.last_players.append(user.id)
        game.last_times.append(datetime.now().strftime(TIME_FORMAT))
        await self.after_move(ctx, game, colour, user.id)
        save_game(game)

        next_col = sgfengine.next_colour(game.game_key)
        player_text, ping_text = await self.get_next_player_info(ctx, game, next_col)
        file, msg = format_game_message(game.game_key, game, next_player_display=player_text, ping_mention=ping_text)
        await ctx.send(content=msg, file=file)

    async def after_move(self, ctx, game: GameState, colour: int, user_id: int) -> None:
        """Hook called immediately after a move is recorded in state."""
        pass

    async def on_edit(self, ctx, game: GameState, move_str: str) -> None:
        """Corrects the last move within 5 minutes."""
        user = ctx.author
        if not game.last_players or game.last_players[-1] != user.id:
            await ctx.send("You cannot edit this move!")
            return

        last_time = datetime.strptime(game.last_times[-1], TIME_FORMAT)
        if datetime.now() - last_time > timedelta(minutes=5):
            await ctx.send("You cannot edit this move! (Time limit of 5 minutes exceeded)")
            return

        clean_move = move_str.strip()
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

    async def on_join(self, ctx, game: GameState) -> None:
        """Default hook when a user types $join."""
        await ctx.send("This game has no queue! Anyone can play with `$play <move>` or `$pass` :P")

    async def on_leave(self, ctx, game: GameState) -> None:
        """Default hook when a user types $leave."""
        await ctx.send("This game has no queue! No need to leave!")

    async def on_queue(self, ctx, game: GameState) -> None:
        """Default hook when a user types $queue."""
        await ctx.send("This game has no queue! No need to join, just `$play` whenever you want :P")

    async def on_board(self, ctx, game: GameState) -> None:
        """Renders the current board and posts state."""
        sgfengine.render_png(game.game_key)
        colour = sgfengine.next_colour(game.game_key)
        next_player_text, _ = await self.get_next_player_info(ctx, game, colour)
        file, msg = format_game_message(game.game_key, game, next_player_display=next_player_text, title_override="Current Board State")
        await ctx.send(content=msg, file=file)

    async def get_next_player_info(self, ctx, game: GameState, next_colour: int) -> tuple[str | None, str | None]:
        """Returns (display_name, ping_mention) for the next player to move."""
        return None, None

    async def on_resign(self, ctx, game: GameState, winner_colour: str) -> None:
        """Handles resignation and archival."""
        now = datetime.now()
        clean_channel = re.sub(r'[^a-zA-Z0-9_\-]', '', ctx.channel.name) or "channel"
        friendly_filename = f"rengo_{now.strftime('%Y_%m_%d_%H%M%S')}_{clean_channel}.sgf"
        archived_filename = f"{game.game_key}_{friendly_filename}"

        sgfengine.resign(game.game_key, winner_colour, archived_filename)
        remove_game(game.game_key)

        file = discord.File(archived_filename, filename=friendly_filename)
        await ctx.send(file=file, content=("Black" if winner_colour == "W" else "White") + " wins!")
