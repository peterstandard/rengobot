"""Voting game mode: community move voting with countdown timer and random tie-breaking."""

from datetime import datetime, timedelta
import json
import os
import random
import re
import discord
from discord.ext import tasks

import sgfengine
from config import WHITE_STONE_EMOJI, BLACK_STONE_EMOJI, TIME_FORMAT
from state import GameState, save_game, remove_game, load_all_games
from ui import format_game_message
from modes.base import BaseGameMode

VOTES_FILE: str = "votes.json"

def load_votes() -> dict:
    """Loads all active voting sessions from votes.json."""
    if os.path.exists(VOTES_FILE):
        try:
            with open(VOTES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[RengoBot] Error loading {VOTES_FILE}: {e}")
    return {}

def save_votes(data: dict) -> None:
    """Saves active voting sessions to votes.json."""
    try:
        with open(VOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[RengoBot] Error saving {VOTES_FILE}: {e}")

def format_vote_summary(vdata: dict) -> str:
    """Formats the remaining time and descending standings for a voting session."""
    votes = vdata.get("votes", {})
    deadline_str = vdata.get("deadline")
    minutes = vdata.get("minutes", 10.0)
    mins_display = int(minutes) if minutes == int(minutes) else minutes

    if not deadline_str or not votes:
        return f"🗳️ No votes cast yet for this turn. Timer (`{mins_display}m`) will begin when the first vote is cast with `$play <move>` or `$pass`."

    try:
        deadline_dt = datetime.fromisoformat(deadline_str)
        remaining_sec = max(0, int((deadline_dt - datetime.now()).total_seconds()))
    except Exception:
        remaining_sec = 0

    mins = remaining_sec // 60
    secs = remaining_sec % 60
    time_str = f"{mins}m {secs:02d}s" if mins > 0 else f"{secs}s"

    tally: dict[str, int] = {}
    for mv in votes.values():
        tally[mv] = tally.get(mv, 0) + 1

    sorted_moves = sorted(tally.items(), key=lambda x: (-x[1], x[0]))

    total_votes = len(votes)
    lines = [
        f"⏱️ **Time remaining:** `{time_str}`  •  **Total votes:** `{total_votes}`",
        "**Current Standings:**"
    ]
    for rank, (mv, cnt) in enumerate(sorted_moves, 1):
        lines.append(f"{rank}. `{mv}` — **{cnt}** vote{'s' if cnt != 1 else ''}")

    return "\n".join(lines)

def get_turn_header(game_key: str) -> str:
    """Returns the '<emoji> Black/White to play!' header for the current turn."""
    colour = sgfengine.next_colour(game_key)
    turn_colour_name = "White" if colour == 1 else "Black"
    turn_emoji = WHITE_STONE_EMOJI if colour == 1 else BLACK_STONE_EMOJI
    return f"{turn_emoji} **{turn_colour_name} to play!**"

class VoteMode(BaseGameMode):
    """Collective channel voting mode with countdown timers and random tie-breaks."""
    name: str = "vote"
    description: str = "Collective channel voting! Countdown begins on first vote; highest voted move is played."

    async def on_new_game(self, ctx, game_key: str, *args) -> GameState:
        minutes = 10.0
        handicap = 0
        komi = 6.5

        if len(args) >= 1:
            try:
                minutes = max(0.5, float(args[0]))
            except ValueError:
                await ctx.send("Please specify voting time in minutes, e.g. `$newgame vote 15`")
                raise

        if len(args) >= 2:
            try:
                handicap = int(args[1])
            except ValueError:
                handicap = 0

        if len(args) >= 3:
            try:
                komi = float(args[2])
            except ValueError:
                komi = 6.5

        sgfengine.new_game(game_key, handicap, komi)
        game = GameState(game_key=game_key, gametype=self.name, data=[[], []])
        save_game(game)

        all_votes = load_votes()
        all_votes[game_key] = {
            "channel_id": ctx.channel.id,
            "minutes": minutes,
            "deadline": None,
            "votes": {}
        }
        save_votes(all_votes)

        mins_display = int(minutes) if minutes == int(minutes) else minutes
        title = f"New Game Started • VOTE Mode ({mins_display} min per move)"
        file, msg = format_game_message(game_key, game, title_override=title)
        msg += f"\n*Everyone can vote! The {mins_display}m countdown begins when the first vote is cast with `$play <move>` or `$pass`.*"
        await ctx.send(content=msg, file=file)
        return game

    async def on_play(self, ctx, game: GameState, move_str: str) -> None:
        user = ctx.author
        game_key = game.game_key

        clean_move = move_str.strip()
        legal, err = sgfengine.validate_move(game_key, clean_move)
        if not legal:
            await ctx.send(f"⚠️ {err}")
            return

        move_formatted = clean_move.upper()
        all_votes = load_votes()
        vdata = all_votes.get(game_key, {
            "channel_id": ctx.channel.id,
            "minutes": 10.0,
            "deadline": None,
            "votes": {}
        })

        old_vote = vdata.get("votes", {}).get(str(user.id))
        is_first_vote = (vdata.get("deadline") is None)
        if is_first_vote:
            minutes = vdata.get("minutes", 10.0)
            vdata["deadline"] = (datetime.now() + timedelta(minutes=minutes)).isoformat()
            vdata["channel_id"] = ctx.channel.id

        if "votes" not in vdata:
            vdata["votes"] = {}
        vdata["votes"][str(user.id)] = move_formatted
        all_votes[game_key] = vdata
        save_votes(all_votes)

        turn_header = get_turn_header(game_key)
        if old_vote and old_vote != move_formatted:
            ack = f"🔄 {user.mention} changed vote from `{old_vote}` to **`{move_formatted}`**!"
        else:
            ack = f"🗳️ {user.mention} voted for **`{move_formatted}`**!"

        summary = format_vote_summary(vdata)
        await ctx.send(f"{turn_header}\n{ack}\n\n{summary}")

    async def on_pass(self, ctx, game: GameState) -> None:
        user = ctx.author
        game_key = game.game_key
        move_formatted = "Pass"

        all_votes = load_votes()
        vdata = all_votes.get(game_key, {
            "channel_id": ctx.channel.id,
            "minutes": 10.0,
            "deadline": None,
            "votes": {}
        })

        old_vote = vdata.get("votes", {}).get(str(user.id))
        is_first_vote = (vdata.get("deadline") is None)
        if is_first_vote:
            minutes = vdata.get("minutes", 10.0)
            vdata["deadline"] = (datetime.now() + timedelta(minutes=minutes)).isoformat()
            vdata["channel_id"] = ctx.channel.id

        if "votes" not in vdata:
            vdata["votes"] = {}
        vdata["votes"][str(user.id)] = move_formatted
        all_votes[game_key] = vdata
        save_votes(all_votes)

        turn_header = get_turn_header(game_key)
        if old_vote and old_vote != move_formatted:
            ack = f"🔄 {user.mention} changed vote from `{old_vote}` to **`Pass`**!"
        else:
            ack = f"🗳️ {user.mention} voted to **`Pass`**!"

        summary = format_vote_summary(vdata)
        await ctx.send(f"{turn_header}\n{ack}\n\n{summary}")

    async def on_edit(self, ctx, game: GameState, move_str: str) -> None:
        await ctx.send(
            "Moves in Voting mode cannot be edited once resolved. "
            "You can change your active vote with `$play <move>` or `$pass` before the voting timer ends!"
        )

    async def on_queue(self, ctx, game: GameState) -> None:
        all_votes = load_votes()
        vdata = all_votes.get(game.game_key, {"channel_id": ctx.channel.id, "minutes": 10.0, "deadline": None, "votes": {}})
        turn_header = get_turn_header(game.game_key)
        await ctx.send(f"This game is in Voting mode! Check standings with `$votes`:\n\n{turn_header}\n\n{format_vote_summary(vdata)}")

    async def on_board(self, ctx, game: GameState) -> None:
        sgfengine.render_png(game.game_key)
        all_votes = load_votes()
        vdata = all_votes.get(game.game_key, {})
        mins = vdata.get("minutes", 10.0)
        mins_str = f"{int(mins) if mins == int(mins) else mins}m"

        if vdata.get("deadline"):
            next_player_text = f"Channel Vote in progress ({mins_str} timer)"
        else:
            next_player_text = f"Channel Vote (awaiting first vote for {mins_str} timer)"

        file, msg = format_game_message(game.game_key, game, next_player_display=next_player_text, title_override="Current Board State")
        if vdata.get("votes"):
            msg += f"\n\n{format_vote_summary(vdata)}"
        await ctx.send(content=msg, file=file)

    async def on_resign(self, ctx, game: GameState, winner_colour: str) -> None:
        all_votes = load_votes()
        if game.game_key in all_votes:
            all_votes.pop(game.game_key, None)
            save_votes(all_votes)
        await super().on_resign(ctx, game, winner_colour)

async def resolve_vote(bot, game_key: str, vdata: dict) -> None:
    """Executes the winning move for an expired voting countdown."""
    channel_id = vdata.get("channel_id")
    channel = bot.get_channel(channel_id)
    if not channel and channel_id:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:
            channel = None

    votes = vdata.get("votes", {})
    if not votes:
        all_votes = load_votes()
        if game_key in all_votes:
            all_votes[game_key]["deadline"] = None
            save_votes(all_votes)
        return

    # Tally votes
    tally: dict[str, int] = {}
    for uid, mv in votes.items():
        tally[mv] = tally.get(mv, 0) + 1

    max_votes = max(tally.values())
    top_moves = [mv for mv, cnt in tally.items() if cnt == max_votes]

    # Random tie-breaker
    tied = len(top_moves) > 1
    winning_move = random.choice(top_moves) if tied else top_moves[0]

    # Reset voting state for the next turn
    all_votes = load_votes()
    if game_key in all_votes:
        all_votes[game_key]["deadline"] = None
        all_votes[game_key]["votes"] = {}
        save_votes(all_votes)

    games = load_all_games()
    game = None
    for g in games:
        if g.game_key == game_key:
            game = g
            break

    if not game:
        return

    # Execute winning move in SGF engine
    try:
        if winning_move == "Pass":
            sgfengine.play_pass(game_key, "Vote Decision")
        else:
            sgfengine.play_move(game_key, winning_move, "Vote Decision")
    except Exception as e:
        if channel:
            await channel.send(f"⚠️ Error playing winning move `{winning_move}`: {e}")
        return

    game.last_players.append(0)
    game.last_times.append(datetime.now().strftime(TIME_FORMAT))
    save_game(game)

    if channel:
        minutes = vdata.get("minutes", 10.0)
        mins_display = int(minutes) if minutes == int(minutes) else minutes

        title = f"Move Decided by Vote: {winning_move}"
        if tied:
            details = f"🎲 **Tie-breaker!** `{winning_move}` was randomly selected among tied top moves: {', '.join(f'`{m}`' for m in top_moves)} ({max_votes} votes each)."
        else:
            details = f"🗳️ `{winning_move}` won the vote with **{max_votes}** vote{'s' if max_votes != 1 else ''}!"

        file, msg = format_game_message(game_key, game, title_override=title)
        full_msg = f"{details}\n\n{msg}\n*Next turn's {mins_display}m countdown begins when someone votes with `$play <move>` or `$pass`.*"
        await channel.send(content=full_msg, file=file)

@tasks.loop(seconds=5)
async def check_vote_timers(bot):
    """Background task checking for expired vote timers every 5 seconds."""
    all_votes = load_votes()
    now = datetime.now()
    for game_key, vdata in list(all_votes.items()):
        deadline_str = vdata.get("deadline")
        if not deadline_str:
            continue
        try:
            deadline_dt = datetime.fromisoformat(deadline_str)
        except Exception:
            continue

        if now >= deadline_dt:
            await resolve_vote(bot, game_key, vdata)
