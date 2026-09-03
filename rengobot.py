import ast
import asyncio
import json
import os
os.environ["PATH"] = os.path.expanduser("~/.cargo/bin") + os.pathsep + os.environ.get("PATH", "")
import random
import re
import time
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks

import sgfengine

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='$', intents=intents, help_command=None, case_insensitive=True)

CHANNELS_FILE = "channels.json"
VOTES_FILE = "votes.json"

def load_env(env_path=".env"):
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

def get_int_list(env_var, default=None):
    val = os.environ.get(env_var)
    if val is not None:
        return [int(x.strip()) for x in val.split(",") if x.strip().isdigit()]
    return default if default is not None else []

min_time_player = timedelta(seconds=1) # in random games, min time between same player plays (default days=1)
time_to_skip = timedelta(seconds=1) # in queue games, how much time to wait for the next move
min_players = 2

# Global bot admins (can manage all games and execute $shutdown)
admins = get_int_list("ADMIN_IDS", [])

# Teachers for teachers mode
teachers = get_int_list("TEACHER_IDS", [])

# Server & Channel filtering (empty allows all)
permitted_server_ids = get_int_list("PERMITTED_SERVER_IDS", [])
permitted_channel_ids = get_int_list("PERMITTED_CHANNEL_IDS", [])

white_stone = os.environ.get("WHITE_STONE_EMOJI", "⚪")
black_stone = os.environ.get("BLACK_STONE_EMOJI", "⚫")

token = os.environ.get("DISCORD_TOKEN")
if not token:
    if os.path.exists("token.txt"):
        with open("token.txt") as f:
            token = f.read().strip()
    else:
        raise ValueError("Discord token not found! Provide DISCORD_TOKEN in .env or token.txt")

format = "%Y_%m_%d_%H_%M_%S_%f"

def load_channels():
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[RengoBot] Error loading {CHANNELS_FILE}: {e}")
    return {}

def save_channels(data):
    try:
        with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[RengoBot] Error saving {CHANNELS_FILE}: {e}")

def load_votes():
    if os.path.exists(VOTES_FILE):
        try:
            with open(VOTES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[RengoBot] Error loading {VOTES_FILE}: {e}")
    return {}

def save_votes(data):
    try:
        with open(VOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[RengoBot] Error saving {VOTES_FILE}: {e}")

def format_vote_summary(vdata):
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

    tally = {}
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

def is_channel_enabled(guild_id, channel_id):
    if channel_id in permitted_channel_ids:
        return True
    data = load_channels()
    guild_channels = data.get(str(guild_id), [])
    return channel_id in guild_channels

def is_permitted(ctx):
    if not ctx.guild:
        return False
    if permitted_server_ids and ctx.guild.id not in permitted_server_ids:
        return False
    return is_channel_enabled(ctx.guild.id, ctx.channel.id)

def is_game_admin(ctx):
    if ctx.author.id in admins:
        return True
    if ctx.guild and (ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild):
        return True
    return False

def get_game_key(ctx):
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

def find_game(state, ctx):
    channel_id = ctx.channel.id
    game_key = get_game_key(ctx)
    for idx, s in enumerate(state):
        entry_id = str(s[0])
        if entry_id == str(channel_id) or entry_id == game_key:
            return idx
    return None

async def get_player_display(guild, user_id):
    if not guild:
        return f"Player {user_id}", f"<@{user_id}>"
    try:
        member = await guild.fetch_member(user_id)
        return member.display_name, member.mention
    except Exception:
        return f"Player {user_id}", f"<@{user_id}>"

def format_game_message(game_key, state_tuple=None, next_player_display=None, ping_mention=None, title_override=None):
    info = sgfengine.get_game_state(str(game_key))
    if not info:
        return discord.File(f"{game_key}.png"), ""

    lines = []

    if title_override:
        lines.append(f"### {title_override}")
    elif info["last_move"]:
        move_colour = f"{black_stone} Black" if info["last_colour"] == "B" else f"{white_stone} White"
        player_str = f" ({info['last_player']})" if info['last_player'] else ""
        if info["last_move"] == "Pass":
            lines.append(f"### Move #{info['move_count']} • {move_colour}{player_str} Passed")
        else:
            lines.append(f"### Move #{info['move_count']} • {move_colour}{player_str} played `{info['last_move']}`")
    else:
        lines.append("### New Game Started")

    next_colour_name = "White" if info["next_colour"] == "W" else "Black"
    turn_emoji = white_stone if info["next_colour"] == "W" else black_stone
    if ping_mention:
        lines.append(f"{turn_emoji} **{next_colour_name}'s turn:** {ping_mention} ⭐")
    elif next_player_display:
        lines.append(f"{turn_emoji} **{next_colour_name}'s turn:** {next_player_display}")
    else:
        lines.append(f"{turn_emoji} **{next_colour_name}'s turn!**")

    ruleset_str = info.get("ruleset", "AGA")
    lines.append(f"**Captures:** {black_stone} `{info['captures']['B']}`  |  {white_stone} `{info['captures']['W']}`  •  **Info:** Ruleset `{ruleset_str}` | Komi `{info['komi']}` | Handicap `{info['handicap']}`")

    if info.get("consecutive_passes", 0) >= 2:
        lines.append("⚠️ **Game Over:** Both players passed! Use `$resign <B/W>` to record the winner or `$sgf` for the game record.")
    elif info.get("consecutive_passes", 0) == 1:
        lines.append("ℹ️ *1 pass recorded. A second consecutive pass will end the game.*")

    file = discord.File(f"{game_key}.png")
    return file, "\n".join(lines)

async def resolve_vote(game_key, vdata):
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

    tally = {}
    for uid, mv in votes.items():
        tally[mv] = tally.get(mv, 0) + 1

    max_votes = max(tally.values())
    top_moves = [mv for mv, cnt in tally.items() if cnt == max_votes]

    tied = len(top_moves) > 1
    winning_move = random.choice(top_moves) if tied else top_moves[0]

    # Reset voting state for next turn
    all_votes = load_votes()
    if game_key in all_votes:
        all_votes[game_key]["deadline"] = None
        all_votes[game_key]["votes"] = {}
        save_votes(all_votes)

    state = []
    if os.path.exists("state.txt"):
        with open("state.txt") as f:
            try:
                state = ast.literal_eval(f.read())
            except Exception:
                state = []

    idx = None
    for i, s in enumerate(state):
        entry_id = str(s[0])
        if entry_id == str(game_key):
            idx = i
            break

    if idx is None:
        return

    # Execute winning move
    try:
        if winning_move == "Pass":
            sgfengine.play_pass(game_key, "Vote Decision")
        else:
            sgfengine.play_move(game_key, winning_move, "Vote Decision")
    except Exception as e:
        if channel:
            await channel.send(f"⚠️ Error playing winning move `{winning_move}`: {e}")
        return

    state[idx][2].append(0)
    state[idx][3].append(datetime.now().strftime(format))
    with open("state.txt", "w") as f:
        f.write(repr(state))

    if channel:
        minutes = vdata.get("minutes", 10.0)
        mins_display = int(minutes) if minutes == int(minutes) else minutes

        title = f"Move Decided by Vote: {winning_move}"
        if tied:
            details = f"🎲 **Tie-breaker!** `{winning_move}` was randomly selected among tied top moves: {', '.join(f'`{m}`' for m in top_moves)} ({max_votes} votes each)."
        else:
            details = f"🗳️ `{winning_move}` won the vote with **{max_votes}** vote{'s' if max_votes != 1 else ''}!"

        file, msg = format_game_message(game_key, state[idx], title_override=title)
        full_msg = f"{details}\n\n{msg}\n*Next turn's {mins_display}m countdown begins when someone votes with `$play <move>` or `$pass`.*"
        await channel.send(content=full_msg, file=file)

@tasks.loop(seconds=5)
async def check_vote_timers():
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
            await resolve_vote(game_key, vdata)

@bot.command(name="listen")
async def listen_channel(ctx):
    if not ctx.guild:
        return
    if not is_game_admin(ctx):
        await ctx.send("You don't have permissions for this! Only server administrators can configure bot channels.")
        return

    data = load_channels()
    g_key = str(ctx.guild.id)
    ch_list = data.get(g_key, [])
    if ctx.channel.id in ch_list or ctx.channel.id in permitted_channel_ids:
        await ctx.send(f"ℹ️ RengoBot is already listening in {ctx.channel.mention}!")
        return

    ch_list.append(ctx.channel.id)
    data[g_key] = ch_list
    save_channels(data)
    await ctx.send(f"✅ RengoBot is now listening in {ctx.channel.mention}! Use `$newgame` to start a game.")

@bot.command(name="unlisten")
async def unlisten_channel(ctx):
    if not ctx.guild:
        return
    if not is_game_admin(ctx):
        await ctx.send("You don't have permissions for this! Only server administrators can configure bot channels.")
        return

    data = load_channels()
    g_key = str(ctx.guild.id)
    ch_list = data.get(g_key, [])

    if ctx.channel.id not in ch_list and ctx.channel.id not in permitted_channel_ids:
        await ctx.send(f"ℹ️ RengoBot is not listening in {ctx.channel.mention}.")
        return

    if ctx.channel.id in ch_list:
        ch_list.remove(ctx.channel.id)
        data[g_key] = ch_list
        save_channels(data)

    msg = f"🔇 RengoBot will no longer listen in {ctx.channel.mention}."
    game_key = get_game_key(ctx)
    if os.path.exists(f"{game_key}.sgf"):
        msg += " Active game data is preserved and can be resumed at any time with `$listen`."
    await ctx.send(msg)

@bot.command(name="channels")
async def list_channels(ctx):
    if not ctx.guild:
        return

    data = load_channels()
    g_key = str(ctx.guild.id)
    ch_set = set(data.get(g_key, []))

    for cid in permitted_channel_ids:
        if ctx.guild.get_channel(cid):
            ch_set.add(cid)

    if not ch_set:
        await ctx.send("No channels are currently enabled for RengoBot in this server.\nAn administrator can enable this channel by typing `$listen`!")
        return

    mentions = [f"<#{cid}>" for cid in sorted(ch_set)]
    await ctx.send(f"**Active Rengo Channels in {ctx.guild.name}:**\n" + "\n".join(f"• {m}" for m in mentions))

@bot.command(name="votes", aliases=["standings", "tally"])
async def show_votes(ctx):
    if not is_permitted(ctx): return
    game_key = get_game_key(ctx)
    with open("state.txt") as f: state = ast.literal_eval(f.read())
    idx = find_game(state, ctx)
    if idx is None:
        await ctx.send("No active game in this channel!")
        return

    if state[idx][1] not in ["vote", "voting"]:
        await ctx.send("This game is not in Voting mode! Use `$help` to see available game modes.")
        return

    all_votes = load_votes()
    vdata = all_votes.get(game_key, {
        "channel_id": ctx.channel.id,
        "minutes": 10.0,
        "deadline": None,
        "votes": {}
    })
    await ctx.send(format_vote_summary(vdata))

@bot.command()
async def help(ctx):
    if not ctx.guild:
        return
    if not is_permitted(ctx):
        if is_game_admin(ctx):
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

@bot.command()
async def play(ctx, arg):
    if not is_permitted(ctx): return
    game_key = get_game_key(ctx)
    user = ctx.author
    guild = ctx.guild

    with open("state.txt") as f: state = ast.literal_eval(f.read())

    idx = find_game(state, ctx)
    if idx is None:
        return
    i = idx
    state[i] = (game_key, state[i][1], state[i][2], state[i][3], state[i][4])

    # Voting Mode Logic
    if state[i][1] in ["vote", "voting"]:
        arg = arg.strip()
        legal, err = sgfengine.validate_move(game_key, arg)
        if not legal:
            await ctx.send(f"⚠️ {err}")
            return

        move_formatted = arg.upper()
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

        if old_vote and old_vote != move_formatted:
            ack = f"🔄 {user.mention} changed vote from `{old_vote}` to **`{move_formatted}`**!"
        else:
            ack = f"🗳️ {user.mention} voted for **`{move_formatted}`**!"

        summary = format_vote_summary(vdata)
        await ctx.send(f"{ack}\n\n{summary}")
        return

    if state[i][1] in ["queue", "teachers"] and user.id not in state[i][4][0]+state[i][4][1]:
        await ctx.send("Player hasn't joined yet! Join us with `$join`")
        return

    if state[i][1] == "queue" and (len(state[i][4][0])<min_players or len(state[i][4][1]) <min_players):
        await ctx.send("Waiting for more players to join! Minimum {} per team".format(min_players))
        return

    colour = sgfengine.next_colour(game_key)

    if (state[i][1] == "queue" and user.id!= state[i][4][colour][0]) or (state[i][1]=="teachers" and ((colour==0 and user.id!=state[i][4][0][0]) or (colour==1 and user.id not in state[i][4][1]))):
        await ctx.send("It is not your turn yet!")
        return

    if state[i][1] == "random":
        assert( len(state[i][2]) == len(state[i][3]))

        if len(state[i][2])>0 and state[i][2][-1] == user.id and (state[i][1]!="teachers" or colour=="0"):
            await ctx.send("No two consecutive moves by the same player!")
            return

        if len(state[i][2])>1 and state[i][2][-2] == user.id and (state[i][1]!="teachers" or colour=="0"):
            await ctx.send("No two consecutive same-color moves by the same player!")
            return

        for j in range(len(state[i][2])):
            if (state[i][2][j] == user.id and
                datetime.now() - datetime.strptime(state[i][3][j],format) < min_time_player):
                await ctx.send("At most one move per player per day!")
                return

    arg = arg.strip()
    if state[i][1] != "debug" and state[i][3] != [] and datetime.now()-datetime.strptime(state[i][3][-1],format)<timedelta(seconds=4):
        last_move = sgfengine.get_last_move_formatted(game_key)
        dropped_move = arg.upper()
        if last_move:
            await ctx.send(f"Last accepted move: {last_move}. Move {dropped_move} dropped by anti-spam.")
        else:
            await ctx.send(f"Move {dropped_move} dropped by anti-spam.")
        return
    legal_moves=[chr(col+ord('A')-1)+str(row) for col in range(1,21) if col!=9 for row in range(1,20)]
    legal_moves+=[chr(col+ord('a')-1)+str(row) for col in range(1,21) if col!=9 for row in range(1,20)]
    if arg not in legal_moves:
        await ctx.send("I don't understand the move! Please input it in the format `$play Q16`")
        return

    try:
        sgfengine.play_move(game_key, arg, user.display_name)
    except ValueError as e:
        await ctx.send(str(e))
        return

    state[i][2].append(user.id)
    state[i][3].append(datetime.now().strftime(format))

    if state[i][1] == "queue":
        state[i][4][colour].pop(0)
        state[i][4][colour].append(user.id)

    if state[i][1] == "teachers" and colour==0:
        state[i][4][0].pop(0)
        state[i][4][0].append(user.id)

    next_player_text = None
    mention_content = None
    if state[i][1]=="queue":
        next_player_text, mention_content = await get_player_display(guild, state[i][4][1-colour][0])
    elif state[i][1]=="teachers" and colour==1:
        next_player_text, mention_content = await get_player_display(guild, state[i][4][1-colour][0])
    elif state[i][1]=="teachers" and colour==0:
        next_player_text = "Teachers"
        mention_content = None

    file, msg = format_game_message(game_key, state[i], next_player_display=next_player_text, ping_mention=mention_content)
    await ctx.send(content=msg, file=file)

    with open("state.txt", "w") as f: f.write(repr(state))

@bot.command(name="pass")
async def pass_turn(ctx):
    if not is_permitted(ctx): return
    game_key = get_game_key(ctx)
    user = ctx.author
    guild = ctx.guild

    with open("state.txt") as f: state = ast.literal_eval(f.read())

    idx = find_game(state, ctx)
    if idx is None:
        await ctx.send("No active game in this channel!")
        return

    i = idx
    state[i] = (game_key, state[i][1], state[i][2], state[i][3], state[i][4])

    # Voting Mode Logic for Pass
    if state[i][1] in ["vote", "voting"]:
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

        if old_vote and old_vote != move_formatted:
            ack = f"🔄 {user.mention} changed vote from `{old_vote}` to **`Pass`**!"
        else:
            ack = f"🗳️ {user.mention} voted to **`Pass`**!"

        summary = format_vote_summary(vdata)
        await ctx.send(f"{ack}\n\n{summary}")
        return

    if state[i][1] in ["queue", "teachers"] and user.id not in state[i][4][0]+state[i][4][1]:
        await ctx.send("Player hasn't joined yet! Join us with `$join`")
        return

    if state[i][1] == "queue" and (len(state[i][4][0])<min_players or len(state[i][4][1]) <min_players):
        await ctx.send("Waiting for more players to join! Minimum {} per team".format(min_players))
        return

    colour = sgfengine.next_colour(game_key)

    if (state[i][1] == "queue" and user.id!= state[i][4][colour][0]) or (state[i][1]=="teachers" and ((colour==0 and user.id!=state[i][4][0][0]) or (colour==1 and user.id not in state[i][4][1]))):
        await ctx.send("It is not your turn yet!")
        return

    if state[i][1] == "random":
        assert( len(state[i][2]) == len(state[i][3]))

        if len(state[i][2])>0 and state[i][2][-1] == user.id and (state[i][1]!="teachers" or colour=="0"):
            await ctx.send("No two consecutive moves by the same player!")
            return

        if len(state[i][2])>1 and state[i][2][-2] == user.id and (state[i][1]!="teachers" or colour=="0"):
            await ctx.send("No two consecutive same-color moves by the same player!")
            return

        for j in range(len(state[i][2])):
            if (state[i][2][j] == user.id and
                datetime.now() - datetime.strptime(state[i][3][j],format) < min_time_player):
                await ctx.send("At most one move per player per day!")
                return

    if state[i][1] != "debug" and state[i][3] != [] and datetime.now()-datetime.strptime(state[i][3][-1],format)<timedelta(seconds=4):
        last_move = sgfengine.get_last_move_formatted(game_key)
        if last_move:
            await ctx.send(f"Last accepted move: {last_move}. Move PASS dropped by anti-spam.")
        else:
            await ctx.send("Move PASS dropped by anti-spam.")
        return

    sgfengine.play_pass(game_key, user.display_name)

    state[i][2].append(user.id)
    state[i][3].append(datetime.now().strftime(format))

    if state[i][1] == "queue":
        state[i][4][colour].pop(0)
        state[i][4][colour].append(user.id)

    if state[i][1] == "teachers" and colour==0:
        state[i][4][0].pop(0)
        state[i][4][0].append(user.id)

    next_player_text = None
    mention_content = None
    if state[i][1]=="queue":
        next_player_text, mention_content = await get_player_display(guild, state[i][4][1-colour][0])
    elif state[i][1]=="teachers" and colour==1:
        next_player_text, mention_content = await get_player_display(guild, state[i][4][1-colour][0])
    elif state[i][1]=="teachers" and colour==0:
        next_player_text = "Teachers"
        mention_content = None

    file, msg = format_game_message(game_key, state[i], next_player_display=next_player_text, ping_mention=mention_content)
    await ctx.send(content=msg, file=file)

    with open("state.txt", "w") as f: f.write(repr(state))

@bot.command()
async def edit(ctx, arg):
    if not is_permitted(ctx): return
    game_key = get_game_key(ctx)
    user = ctx.author
    guild = ctx.guild

    with open("state.txt") as f: state = ast.literal_eval(f.read())

    idx = find_game(state, ctx)
    if idx is None:
        await ctx.send("No active game in this channel!")
        return

    i = idx
    if state[i][1] in ["vote", "voting"]:
        await ctx.send("Moves in Voting mode cannot be edited once resolved. You can change your active vote with `$play <move>` or `$pass` before the voting timer ends!")
        return

    colour = sgfengine.next_colour(game_key)

    if len(state[i][2])==0 or (state[i][1] != "debug" and (state[i][2][-1] != user.id or datetime.now()-datetime.strptime(state[i][3][-1],format) > timedelta(minutes=5))):
        await ctx.send("You cannot edit this move!")
        return

    arg = arg.strip()
    legal_moves=[chr(col+ord('A')-1)+str(row) for col in range(1,21) if col!=9 for row in range(1,20)]
    legal_moves+=[chr(col+ord('a')-1)+str(row) for col in range(1,21) if col!=9 for row in range(1,20)]
    if arg not in legal_moves:
        await ctx.send("I don't understand the move! Please input it in the format `$play Q16`")
        return

    try:
        sgfengine.play_move(game_key, arg, user.display_name, True)
    except ValueError as e:
        await ctx.send(str(e))
        return

    next_player_text = None
    mention_content = None
    if state[i][1]=="queue":
        next_player_text, mention_content = await get_player_display(guild, state[i][4][colour][0])
    elif state[i][1]=="teachers" and colour==0:
        next_player_text, mention_content = await get_player_display(guild, state[i][4][colour][0])
    elif state[i][1]=="teachers" and colour==1:
        next_player_text = "Teachers"
        mention_content = None

    file, msg = format_game_message(game_key, state[i], next_player_display=next_player_text, ping_mention=mention_content, title_override=f"Move Edited: {arg.upper()}")
    await ctx.send(content=msg, file=file)

    with open("state.txt", "w") as f: f.write(repr(state))

@bot.command()
async def board(ctx):
    if not is_permitted(ctx): return
    game_key = get_game_key(ctx)
    guild = ctx.guild

    with open("state.txt") as f: state = ast.literal_eval(f.read())

    idx = find_game(state, ctx)
    if idx is None:
        await ctx.send("No active game in this channel!")
        return

    i = idx
    colour = sgfengine.next_colour(game_key)
    sgfengine.render_png(game_key)

    next_player_text = None
    if state[i][1]=="queue":
        if len(state[i][4][colour]) > 0:
            next_player_text, _ = await get_player_display(guild, state[i][4][colour][0])
        else:
            next_player_text = "Waiting for players"
    elif state[i][1]=="teachers":
        if colour==0:
            next_player_text, _ = await get_player_display(guild, state[i][4][colour][0])
        else:
            next_player_text = "Teachers"
    elif state[i][1] in ["vote", "voting"]:
        all_votes = load_votes()
        vdata = all_votes.get(game_key, {})
        mins = vdata.get("minutes", 10.0)
        mins_str = f"{int(mins) if mins == int(mins) else mins}m"
        if vdata.get("deadline"):
            next_player_text = f"Channel Vote in progress ({mins_str} timer)"
        else:
            next_player_text = f"Channel Vote (awaiting first vote for {mins_str} timer)"

    file, msg = format_game_message(game_key, state[i], next_player_display=next_player_text, title_override="Current Board State")
    if state[i][1] in ["vote", "voting"]:
        all_votes = load_votes()
        vdata = all_votes.get(game_key, {})
        if vdata.get("votes"):
            msg += f"\n\n{format_vote_summary(vdata)}"
    await ctx.send(content=msg, file=file)

@bot.command(name="history", aliases=["moves", "kifu"])
async def history(ctx, *args):
    if not is_permitted(ctx): return
    game_key = get_game_key(ctx)
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
    total_moves = info.get("move_count", 0)

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
    if not is_permitted(ctx): return
    game_key = get_game_key(ctx)
    user = ctx.author

    with open("state.txt") as f: state = ast.literal_eval(f.read())

    idx = find_game(state, ctx)
    if idx is None:
        await ctx.send("No active game in this channel!")
        return

    i = idx

    if state[i][1] in ["random", "anarchy", "debug", "vote", "voting"]:
        await ctx.send("This game has no queue! Anyone can participate by voting with `$play <move>` or `$pass` :P")
        return

    if user.id in (state[i][4][0]+state[i][4][1]):
        await ctx.send("Player already in this game!")
        return

    colour = 0 if len(state[i][4][0])<=len(state[i][4][1]) else 1
    if state[i][1]=="teachers": colour= 0

    state[i][4][colour].append(user.id)

    await ctx.send("{} joined Team {}!".format(user.display_name, ("Black" if colour==0 else "White")))

    with open("state.txt", "w") as f: f.write(repr(state))

@bot.command()
async def leave(ctx):
    if not is_permitted(ctx): return
    game_key = get_game_key(ctx)
    user = ctx.author

    with open("state.txt") as f: state = ast.literal_eval(f.read())

    idx = find_game(state, ctx)
    if idx is None:
        await ctx.send("No active game in this channel!")
        return

    i = idx

    if state[i][1] in ["random", "anarchy", "debug", "vote", "voting"]:
        await ctx.send("This game has no queue! No need to leave!")
        return

    if user.id not in (state[i][4][0]+state[i][4][1]):
        await ctx.send("Player not in this game!")
        return

    colour = 0 if (user.id in state[i][4][0]) else 1
    state[i][4][colour].remove(user.id)

    await ctx.send("{} left :(".format(user.display_name))

    with open("state.txt", "w") as f: f.write(repr(state))

@bot.command()
async def queue(ctx):
    if not is_permitted(ctx): return
    game_key = get_game_key(ctx)
    guild = ctx.guild

    with open("state.txt") as f: state = ast.literal_eval(f.read())

    idx = find_game(state, ctx)
    if idx is None:
        await ctx.send("No active game in this channel!")
        return

    i = idx
    colour = sgfengine.next_colour(game_key)

    if state[i][1] in ["vote", "voting"]:
        all_votes = load_votes()
        vdata = all_votes.get(game_key, {"channel_id": ctx.channel.id, "minutes": 10.0, "deadline": None, "votes": {}})
        await ctx.send(f"This game is in Voting mode! Check the current standings with `$votes`:\n\n{format_vote_summary(vdata)}")
        return

    if state[i][1] in ["random", "anarchy", "debug"]:
        await ctx.send("This game has no queue! No need to join, just `$play` whenever you want :P")
        return

    if state[i][1] =="teachers":
        output="Player list for Team Black: "+black_stone+"\n"
        for j, player_id in enumerate(state[i][4][0]):
            player_name, _ = await get_player_display(guild, player_id)
            output+=str(j+1).rjust(3)+". "+ player_name+"\n"
        await ctx.send(output)
        return

    output= "Player list:\n"
    if state[i][4][0]==[] and state[i][4][1] == []:
        output+="Nobody yet! Join us with `$join`"
        await ctx.send(output)
        return

    if state[i][4][0] == []:
        for j, player_id in enumerate(state[i][4][1]):
            player_name, _ = await get_player_display(guild, player_id)
            output+=white_stone+str(j+1).rjust(3)+". "+ player_name+"\n"
        output+="\n Team Black needs more members!"
        await ctx.send(output)
        return

    if state[i][4][1] == []:
        for j, player_id in enumerate(state[i][4][0]):
            player_name, _ = await get_player_display(guild, player_id)
            output+=black_stone+str(j+1).rjust(3)+". "+ player_name+"\n"
        output+="\n Team White needs more members!"
        await ctx.send(output)
        return

    if len(state[i][4][colour]) > len(state[i][4][1-colour]):
        last_player = state[i][4][colour][-1]
    else: last_player= state[i][4][1-colour][-1]

    j=1
    pointers=[0,0]
    while(True):
        output+= white_stone if ((colour+1) % 2 ==0) else black_stone
        output+= str(j).rjust(3)+". "

        player_name, _ = await get_player_display(guild, state[i][4][colour][pointers[colour]])
        output+= player_name+"\n"

        if state[i][4][colour][pointers[colour]] == last_player: break

        pointers[colour] = (pointers[colour]+1) % len(state[i][4][colour])
        colour=1-colour

        j+=1

    if len(state[i][4][0])<min_players:
        output+="\n Team Black needs at least {} members!".format(min_players)
    if len(state[i][4][1])<min_players:
        output+="\n Team White needs at least {} members!".format(min_players)

    await ctx.send(output)

@bot.command()
async def sgf(ctx):
    if not is_permitted(ctx): return
    game_key = get_game_key(ctx)
    if not os.path.exists(f"{game_key}.sgf"):
        await ctx.send("No active game in this channel!")
        return

    now = datetime.now()
    clean_channel = re.sub(r'[^a-zA-Z0-9_\-]', '', ctx.channel.name) or "channel"
    friendly_filename = f"rengo_{now.strftime('%Y_%m_%d_%H%M%S')}_{clean_channel}.sgf"

    file = discord.File(f"{game_key}.sgf", filename=friendly_filename)
    await ctx.send(content=f"Current SGF for **#{ctx.channel.name}**:", file=file)

@bot.command()
async def newgame(ctx, gametype, *args):
    if not is_permitted(ctx): return
    game_key = get_game_key(ctx)

    if not is_game_admin(ctx):
        await ctx.send("You don't have permissions for this! Only server administrators or bot admins can start games.")
        return

    gametype = gametype.strip().lower()
    if gametype not in ["queue", "random", "teachers", "anarchy", "debug", "vote", "voting"]:
        await ctx.send("Unrecognized game type! Please try `$newgame <vote/queue/random/teachers/anarchy>`")
        return

    with open("state.txt") as f: state = ast.literal_eval(f.read())

    if find_game(state, ctx) is not None:
        await ctx.send("A game is already active in this channel!")
        return

    if gametype in ["vote", "voting"]:
        minutes = 10.0
        handicap = 0
        komi = 6.5
        if len(args) >= 1:
            try:
                minutes = max(0.5, float(args[0]))
            except ValueError:
                await ctx.send("Please specify voting time in minutes, e.g. `$newgame vote 15`")
                return
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
        state.append((game_key, "vote", [], [], [[], []]))

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
        file, msg = format_game_message(game_key, state[-1], title_override=title)
        msg += f"\n*Everyone can vote! The {mins_display}m countdown begins when the first vote is cast with `$play <move>` or `$pass`.*"
        await ctx.send(content=msg, file=file)
        with open("state.txt", "w") as f: f.write(repr(state))
        return

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
    if gametype == "teachers":
        state.append((game_key, gametype, [], [], [[], list(teachers)]))
    else:
        state.append((game_key, gametype, [], [], [[], []]))

    title = f"New Game Started • {gametype.upper()} Mode"
    file, msg = format_game_message(game_key, state[-1], title_override=title)
    if gametype in ["queue", "teachers"]:
        msg += "\n*Join the game with `$join`*"
    else:
        msg += "\n*Play a move with `$play <move>`*"
    await ctx.send(content=msg, file=file)

    with open("state.txt", "w") as f: f.write(repr(state))

@bot.command()
async def resign(ctx, arg):
    if not is_permitted(ctx): return
    game_key = get_game_key(ctx)

    if not is_game_admin(ctx):
        await ctx.send("You don't have permissions for this! Only server administrators or bot admins can resign games.")
        return

    arg = arg.strip().upper()
    if arg in ["BLACK"]: arg = "B"
    if arg in ["WHITE"]: arg = "W"

    if arg not in ["W","B"]:
        await ctx.send("Unrecognized colour! Please try `$resign <B/W>` to resign as Black/White")
        return

    with open("state.txt") as f: state = ast.literal_eval(f.read())

    idx = find_game(state, ctx)
    if idx is None:
        await ctx.send("No active game in this channel!")
        return

    now = datetime.now()
    clean_channel = re.sub(r'[^a-zA-Z0-9_\-]', '', ctx.channel.name) or "channel"
    friendly_filename = f"rengo_{now.strftime('%Y_%m_%d_%H%M%S')}_{clean_channel}.sgf"
    archived_filename = f"{game_key}_{friendly_filename}"

    sgfengine.resign(game_key, arg, archived_filename)

    file = discord.File(archived_filename, filename=friendly_filename)
    await ctx.send(file=file, content=("Black" if arg=="W" else "White")+" wins!")

    # Clean up vote data if present
    all_votes = load_votes()
    if game_key in all_votes:
        all_votes.pop(game_key, None)
        save_votes(all_votes)

    state.pop(idx)
    with open("state.txt", "w") as f: f.write(repr(state))

@bot.command()
async def shutdown(ctx):
    if not is_permitted(ctx): return
    if ctx.author.id not in admins:
        await ctx.send("Only global bot administrators can shut down the bot!")
        return

    await ctx.send("🛑 Shutting down RengoBot gracefully...")
    print(f"[RengoBot] Shutdown command invoked by {ctx.author.display_name} ({ctx.author.id})")
    await bot.close()

async def background_task():
    await bot.wait_until_ready()
    print("Bot ready!")

    if not check_vote_timers.is_running():
        check_vote_timers.start()
        print("[RengoBot] Vote timer loop started.")

    game = discord.Game("multiplayer Baduk! $help for command list")
    await bot.change_presence(status=discord.Status.online, activity=game)

async def main():
    if os.path.exists("/data"):
        os.chdir("/data")
    if not os.path.exists("state.txt"):
        with open("state.txt", "w") as f:
            f.write("[]")
    bg_task = None
    try:
        async with bot:
            bg_task = bot.loop.create_task(background_task())
            await bot.start(token)
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
