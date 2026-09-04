"""Main Discord bot entry point, command routing, and lifecycle management."""

import asyncio
import os
import re
from datetime import datetime

import discord
from discord.ext import commands

import config
import channels
import state
import sgfengine
from modes import get_mode, is_valid_mode, check_vote_timers, format_vote_summary, load_votes, get_turn_header

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='$', intents=intents, help_command=None, case_insensitive=True)

# ---------------------------------------------------------------------------
# Channel Management Commands
# ---------------------------------------------------------------------------

@bot.command(name="listen")
async def listen_channel(ctx):
    if not ctx.guild:
        return
    if not config.is_game_admin(ctx):
        await ctx.send("You don't have permissions for this! Only server administrators can configure bot channels.")
        return

    added = channels.enable_channel(ctx.guild.id, ctx.channel.id)
    if not added:
        await ctx.send(f"ℹ️ RengoBot is already listening in {ctx.channel.mention}!")
        return

    await ctx.send(f"✅ RengoBot is now listening in {ctx.channel.mention}! Use `$newgame` to start a game.")

@bot.command(name="unlisten")
async def unlisten_channel(ctx):
    if not ctx.guild:
        return
    if not config.is_game_admin(ctx):
        await ctx.send("You don't have permissions for this! Only server administrators can configure bot channels.")
        return

    removed = channels.disable_channel(ctx.guild.id, ctx.channel.id)
    if not removed and ctx.channel.id not in config.PERMITTED_CHANNEL_IDS:
        await ctx.send(f"ℹ️ RengoBot is not listening in {ctx.channel.mention}.")
        return

    msg = f"🔇 RengoBot will no longer listen in {ctx.channel.mention}."
    game_key = state.get_game_key(ctx)
    if os.path.exists(f"{game_key}.sgf"):
        msg += " Active game data is preserved and can be resumed at any time with `$listen`."
    await ctx.send(msg)

@bot.command(name="channels")
async def list_channels(ctx):
    if not ctx.guild:
        return

    active_ids = channels.get_active_channels_for_guild(ctx.guild)
    if not active_ids:
        await ctx.send(
            "No channels are currently enabled for RengoBot in this server.\n"
            "An administrator can enable this channel by typing `$listen`!"
        )
        return

    mentions = [f"<#{cid}>" for cid in active_ids]
    await ctx.send(f"**Active Rengo Channels in {ctx.guild.name}:**\n" + "\n".join(f"• {m}" for m in mentions))

# ---------------------------------------------------------------------------
# Help Command
# ---------------------------------------------------------------------------

@bot.command()
async def help(ctx):
    if not ctx.guild:
        return
    if not channels.is_permitted(ctx):
        if config.is_game_admin(ctx):
            await ctx.send(
                f"ℹ️ RengoBot is not currently active in this channel.\n"
                f"Type `$listen` to enable games here, or `$channels` to view active channels."
            )
        return

    await ctx.send(
        "**Game Commands:**\n"
        "`$help`: shows this help\n"
        "`$play <move>`: play a move or cast your vote (e.g. `$play Q16`)\n"
        "`$pass`: pass your turn or vote to pass\n"
        "`$votes`: view current voting standings and countdown timer (`vote` mode)\n"
        "`$board`: shows the current board\n"
        "`$history [range]`: shows board with move numbers on stones\n"
        "`$join`: join the game in this channel (`queue`/`teachers`)\n"
        "`$leave`: leave the game in this channel\n"
        "`$queue`: shows player queue / turn order\n"
        "`$edit <move>`: correct your mistake within 5 minutes (turn-based modes)\n"
        "`$sgf`: download the SGF file of the current game\n"
        "`$channels`: show active Rengo channels on this server\n\n"
        "**Admin Commands:**\n"
        "`$listen`: enable Rengo games in this channel\n"
        "`$unlisten`: disable Rengo games in this channel\n"
        "`$newgame <mode> [options]`: start a new game\n"
        "`$resign <B/W>`: resign the game and record final SGF\n"
        "`$shutdown`: cleanly shut down the bot container (global admin only)\n\n"
        "**Game Modes:**\n"
        "• `vote <minutes> [handicap] [komi]`: Collective channel voting! Countdown begins on the first vote; most popular move is played (ties broken randomly).\n"
        "• `random`: Open to all! No queue; players alternate moves with cooldown limits.\n"
        "• `anarchy`: Open to all! No queue and no consecutive-play or color limits.\n"
        "• `queue`: Team rengo with balanced Black/White queues and strict turn rotation.\n"
        "• `teachers`: Students join Team Black in a queue; teachers play White freely."
    )

# ---------------------------------------------------------------------------
# Core Gameplay Commands
# ---------------------------------------------------------------------------

@bot.command()
async def play(ctx, arg):
    if not channels.is_permitted(ctx): return
    game = state.get_game(ctx)
    if not game:
        return

    mode = get_mode(game.gametype)
    if not mode:
        await ctx.send("Unknown game mode for this game!")
        return

    await mode.on_play(ctx, game, arg)

@bot.command(name="pass")
async def pass_turn(ctx):
    if not channels.is_permitted(ctx): return
    game = state.get_game(ctx)
    if not game:
        await ctx.send("No active game in this channel!")
        return

    mode = get_mode(game.gametype)
    if not mode:
        await ctx.send("Unknown game mode for this game!")
        return

    await mode.on_pass(ctx, game)

@bot.command()
async def edit(ctx, arg):
    if not channels.is_permitted(ctx): return
    game = state.get_game(ctx)
    if not game:
        await ctx.send("No active game in this channel!")
        return

    mode = get_mode(game.gametype)
    if not mode:
        return

    await mode.on_edit(ctx, game, arg)

@bot.command()
async def board(ctx):
    if not channels.is_permitted(ctx): return
    game = state.get_game(ctx)
    if not game:
        await ctx.send("No active game in this channel!")
        return

    mode = get_mode(game.gametype)
    if not mode:
        return

    await mode.on_board(ctx, game)

@bot.command(name="history", aliases=["moves", "kifu"])
async def history(ctx, *args):
    if not channels.is_permitted(ctx): return
    game_key = state.get_game_key(ctx)
    if not os.path.exists(f"{game_key}.sgf"):
        await ctx.send("No game has been created yet in this channel. Use `$newgame` to start!")
        return

    move_range = args[0] if args else None
    hist_png = f"{game_key}_history.png"

    sgfengine.render_png(game_key, move_numbers=True, move_range=move_range, out_filename=hist_png)

    if not os.path.exists(hist_png):
        await ctx.send("Failed to render history board.")
        return

    info = sgfengine.get_game_state(game_key)
    total_moves = info.get("move_count", 0) if info else 0

    if move_range:
        header = f"### Move History ({move_range})"
    else:
        header = f"### Move History (Moves 1–{total_moves})"

    file = discord.File(hist_png)
    await ctx.send(content=header, file=file)
    if os.path.exists(hist_png):
        try:
            os.remove(hist_png)
        except OSError:
            pass

@bot.command()
async def join(ctx):
    if not channels.is_permitted(ctx): return
    game = state.get_game(ctx)
    if not game:
        await ctx.send("No active game in this channel!")
        return

    mode = get_mode(game.gametype)
    if mode:
        await mode.on_join(ctx, game)

@bot.command()
async def leave(ctx):
    if not channels.is_permitted(ctx): return
    game = state.get_game(ctx)
    if not game:
        await ctx.send("No active game in this channel!")
        return

    mode = get_mode(game.gametype)
    if mode:
        await mode.on_leave(ctx, game)

@bot.command()
async def queue(ctx):
    if not channels.is_permitted(ctx): return
    game = state.get_game(ctx)
    if not game:
        await ctx.send("No active game in this channel!")
        return

    mode = get_mode(game.gametype)
    if mode:
        await mode.on_queue(ctx, game)

@bot.command(name="votes", aliases=["standings", "tally"])
async def votes(ctx):
    if not channels.is_permitted(ctx): return
    game = state.get_game(ctx)
    if not game:
        await ctx.send("No active game in this channel!")
        return

    if game.gametype not in ["vote", "voting"]:
        await ctx.send("This game is not in Voting mode! Use `$help` to see available game modes.")
        return

    all_votes = load_votes()
    vdata = all_votes.get(game.game_key, {
        "channel_id": ctx.channel.id,
        "minutes": 10.0,
        "deadline": None,
        "votes": {}
    })
    turn_header = get_turn_header(game.game_key)
    await ctx.send(f"{turn_header}\n\n{format_vote_summary(vdata)}")

@bot.command()
async def sgf(ctx):
    if not channels.is_permitted(ctx): return
    game_key = state.get_game_key(ctx)
    if not os.path.exists(f"{game_key}.sgf"):
        await ctx.send("No active game in this channel!")
        return

    now = datetime.now()
    clean_channel = re.sub(r'[^a-zA-Z0-9_\-]', '', ctx.channel.name) or "channel"
    friendly_filename = f"rengo_{now.strftime('%Y_%m_%d_%H%M%S')}_{clean_channel}.sgf"

    file = discord.File(f"{game_key}.sgf", filename=friendly_filename)
    await ctx.send(content=f"Current SGF for **#{ctx.channel.name}**:", file=file)

# ---------------------------------------------------------------------------
# Administrative Game Management
# ---------------------------------------------------------------------------

@bot.command()
async def newgame(ctx, gametype, *args):
    if not channels.is_permitted(ctx): return
    if not config.is_game_admin(ctx):
        await ctx.send("You don't have permissions for this! Only server administrators or bot admins can start games.")
        return

    if not is_valid_mode(gametype):
        await ctx.send("Unrecognized game type! Please try `$newgame <vote/queue/random/teachers/anarchy>`")
        return

    if state.get_game(ctx) is not None:
        await ctx.send("A game is already active in this channel!")
        return

    game_key = state.get_game_key(ctx)
    mode = get_mode(gametype)
    await mode.on_new_game(ctx, game_key, *args)

@bot.command()
async def resign(ctx, arg):
    if not channels.is_permitted(ctx): return
    if not config.is_game_admin(ctx):
        await ctx.send("You don't have permissions for this! Only server administrators or bot admins can resign games.")
        return

    norm_colour = arg.strip().upper()
    if norm_colour in ["BLACK"]: norm_colour = "B"
    if norm_colour in ["WHITE"]: norm_colour = "W"

    if norm_colour not in ["W", "B"]:
        await ctx.send("Unrecognized colour! Please try `$resign <B/W>` to resign as Black/White")
        return

    game = state.get_game(ctx)
    if not game:
        await ctx.send("No active game in this channel!")
        return

    mode = get_mode(game.gametype)
    if mode:
        await mode.on_resign(ctx, game, norm_colour)

@bot.command()
async def shutdown(ctx):
    if not channels.is_permitted(ctx): return
    if ctx.author.id not in config.ADMIN_IDS:
        await ctx.send("Only global bot administrators can shut down the bot!")
        return

    await ctx.send("🛑 Shutting down RengoBot gracefully...")
    print(f"[RengoBot] Shutdown command invoked by {ctx.author.display_name} ({ctx.author.id})")
    await bot.close()

# ---------------------------------------------------------------------------
# Background Tasks & Main Execution
# ---------------------------------------------------------------------------

async def background_task():
    await bot.wait_until_ready()
    print("Bot ready!")

    if not check_vote_timers.is_running():
        check_vote_timers.start(bot)
        print("[RengoBot] Vote timer loop started.")

    game = discord.Game("multiplayer Baduk! $help for command list")
    await bot.change_presence(status=discord.Status.online, activity=game)

async def main():
    if os.path.exists("/data"):
        os.chdir("/data")
    if not os.path.exists("state.txt"):
        with open("state.txt", "w", encoding="utf-8") as f:
            f.write("[]")
    bg_task = None
    try:
        async with bot:
            bg_task = bot.loop.create_task(background_task())
            await bot.start(config.DISCORD_TOKEN)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[RengoBot] Shutdown signal received. Closing cleanly...")
    finally:
        if check_vote_timers.is_running():
            check_vote_timers.stop()
        if bg_task and not bg_task.done():
            bg_task.cancel()
            try:
                await bg_task
            except (asyncio.CancelledError, Exception):
                pass
        if not bot.is_closed():
            await bot.close()
        print("[RengoBot] Bot shutdown complete. Goodbye!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
