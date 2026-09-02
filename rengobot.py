import ast
import asyncio
import os
os.environ["PATH"] = os.path.expanduser("~/.cargo/bin") + os.pathsep + os.environ.get("PATH", "")
import time
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks

import sgfengine

# import requests
# import raw_input

# We don't use fancy slash commands here. It seems there is this library for python but it looks a bit more involved.
# https://pypi.org/project/discord-py-slash-command/

# res = requests.get("https://sh.rustup.rs")
# print(res)
# os.system("curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh")
# os.system("cargo install sgf-render")
# os.system("cargo --version")
# raw_input()

intents = discord.Intents.default()
intents.message_content = True
# client = discord.Client(intents=intents)
# bot = commands.Bot(command_prefix='$', intents=intents)
bot = commands.Bot(command_prefix='$', intents=intents, help_command=None, case_insensitive=True)

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

min_time_player= timedelta(seconds=1) # in random games, min time between same player plays (default days=1)
time_to_skip= timedelta(seconds=1) # in queue games, how much time to wait for the next move
min_players = 2

# People who can start and resign games :O
# Later we might replace this with checking for a role.
admins = get_int_list("ADMIN_IDS", [463380651467472896, 907684282145849375, 631824578934734848, 489423695102869535])

teachers = get_int_list("TEACHER_IDS", [463380651467472896, 907684282145849375, 631824578934734848, 489423695102869535])

server_id = int(os.environ.get("SERVER_ID", 1060261462733496320))

server_name = os.environ.get("SERVER_NAME", "Columbus Go Club")

permitted_channel_ids = get_int_list("PERMITTED_CHANNEL_IDS", [1115612796734943374])

white_stone= "<:white_stone:882731089548939314>"
black_stone= "<:black_stone:882730888453046342>"

token = os.environ.get("DISCORD_TOKEN")
if not token:
    if os.path.exists("token.txt"):
        with open("token.txt") as f:
            token = f.read().strip()
    else:
        raise ValueError("Discord token not found! Provide DISCORD_TOKEN in .env or token.txt")

format="%Y_%m_%d_%H_%M_%S_%f"

def format_game_message(channel_id, state_tuple=None, next_player_display=None, ping_mention=None, title_override=None):
    info = sgfengine.get_game_state(str(channel_id))
    if not info:
        return discord.File(f"{channel_id}.png"), ""

    lines = []

    if title_override:
        lines.append(f"### {title_override}")
    elif info["last_move"]:
        move_colour = "⚫ Black" if info["last_colour"] == "B" else "⚪ White"
        player_str = f" ({info['last_player']})" if info['last_player'] else ""
        if info["last_move"] == "Pass":
            lines.append(f"### Move #{info['move_count']} • {move_colour}{player_str} Passed")
        else:
            lines.append(f"### Move #{info['move_count']} • {move_colour}{player_str} played `{info['last_move']}`")
    else:
        lines.append("### New Game Started")

    next_colour_name = "White" if info["next_colour"] == "W" else "Black"
    turn_emoji = "⚪" if info["next_colour"] == "W" else "⚫"
    if ping_mention:
        lines.append(f"{turn_emoji} **{next_colour_name}'s turn:** {ping_mention} ⭐")
    elif next_player_display:
        lines.append(f"{turn_emoji} **{next_colour_name}'s turn:** {next_player_display}")
    else:
        lines.append(f"{turn_emoji} **{next_colour_name}'s turn!**")

    lines.append(f"**Captures:** ⚫ `{info['captures']['B']}`  |  ⚪ `{info['captures']['W']}`  •  **Info:** Komi `{info['komi']}` | Handicap `{info['handicap']}`")

    if info.get("consecutive_passes", 0) >= 2:
        lines.append("⚠️ **Game Over:** Both players passed! Use `$resign <B/W>` to record the winner or `$sgf` for the game record.")
    elif info.get("consecutive_passes", 0) == 1:
        lines.append("ℹ️ *1 pass recorded. A second consecutive pass will end the game.*")

    file = discord.File(f"{channel_id}.png")
    return file, "\n".join(lines)

# The state is a list of tuples (channel_id, "queue"/"random", last_players, last_times, [black_queue, white_queue])

@bot.command()
async def blah(ctx):
    await ctx.send("blah")

@bot.command()
async def help(ctx):
    if ctx.guild.id == server_id and ctx.channel.id not in permitted_channel_ids: return
    await ctx.send(
        "**Commands:**\n"
        "`$help`: shows this help\n"
        "`$join`: join the game in this channel (`queue`/`teachers`)\n"
        "`$leave`: leave the game in this channel\n"
        "`$play <move>`: play a move (e.g. `$play Q16`)\n"
        "`$pass`: pass your turn\n"
        "`$edit <move>`: correct your mistake within 5 minutes\n"
        "`$board`: shows the current board\n"
        "`$history [range]`: shows board with move numbers on stones\n"
        "`$queue`: shows player queue / turn order\n"
        "`$sgf`: get the SGF file of the current game\n"
        "`$newgame <mode> <handicap> <komi>`: starts a game (admin only)\n"
        "`$resign <B/W>`: resigns the game and returns final SGF (admin only)\n"
        "`$shutdown`: cleanly shuts down the bot (admin only)\n\n"
        "**Game Modes:**\n"
        "• `random`: Open to all! No queue; players alternate moves with consecutive-play limits.\n"
        "• `anarchy`: Open to all! No queue and no consecutive-play or color limits.\n"
        "• `queue`: Team rengo with balanced Black/White queues and strict turn rotation.\n"
        "• `teachers`: Students join Team Black in a queue; teachers play White freely."
    )

@bot.command()
async def play(ctx, arg):
    if ctx.guild.id == server_id and ctx.channel.id not in permitted_channel_ids: return
    channel_id= ctx.channel.id
    user = ctx.author
    guild= ctx.guild

    # lowest effort serialization
    with open("state.txt") as f: state = ast.literal_eval(f.read())

    filter_state= [i for i in range(len(state))  if state[i][0] == channel_id] # This is where I should use a fancy next()
    if not filter_state:
        # await ctx.send("No active game in this channel!")
        return

    i= filter_state[0]

    if state[i][1] in ["queue", "teachers"] and user.id not in state[i][4][0]+state[i][4][1]:
        await ctx.send("Player hasn't joined yet! Join us with `$join`")
        return

    if state[i][1] == "queue" and (len(state[i][4][0])<min_players or len(state[i][4][1]) <min_players):
        await ctx.send("Waiting for more players to join! Minimum {} per team".format(min_players))
        return

    colour= sgfengine.next_colour(str(channel_id))

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
        last_move = sgfengine.get_last_move_formatted(str(channel_id))
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
        sgfengine.play_move(str(channel_id), arg, user.display_name)
    except ValueError as e:
        await ctx.send(str(e))
        return

    # move registered, let's do the other things
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
        next_player=(await guild.fetch_member(state[i][4][1-colour][0]))
        next_player_text = next_player.display_name
        mention_content = next_player.mention
    elif state[i][1]=="teachers" and colour==1:
        next_player=(await guild.fetch_member(state[i][4][1-colour][0]))
        next_player_text = next_player.display_name
        mention_content = next_player.mention
    elif state[i][1]=="teachers" and colour==0:
        next_player_text = "Teachers"
        mention_content = None

    file, msg = format_game_message(channel_id, state[i], next_player_display=next_player_text, ping_mention=mention_content)
    await ctx.send(content=msg, file=file)

    with open("state.txt", "w") as f: f.write(repr(state))

@bot.command(name="pass")
async def pass_turn(ctx):
    if ctx.guild.id == server_id and ctx.channel.id not in permitted_channel_ids: return
    channel_id= ctx.channel.id
    user = ctx.author
    guild= ctx.guild

    # lowest effort serialization
    with open("state.txt") as f: state = ast.literal_eval(f.read())

    filter_state= [i for i in range(len(state)) if state[i][0] == channel_id]
    if not filter_state:
        await ctx.send("No active game in this channel!")
        return

    i= filter_state[0]

    if state[i][1] in ["queue", "teachers"] and user.id not in state[i][4][0]+state[i][4][1]:
        await ctx.send("Player hasn't joined yet! Join us with `$join`")
        return

    if state[i][1] == "queue" and (len(state[i][4][0])<min_players or len(state[i][4][1]) <min_players):
        await ctx.send("Waiting for more players to join! Minimum {} per team".format(min_players))
        return

    colour= sgfengine.next_colour(str(channel_id))

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
        last_move = sgfengine.get_last_move_formatted(str(channel_id))
        if last_move:
            await ctx.send(f"Last accepted move: {last_move}. Move PASS dropped by anti-spam.")
        else:
            await ctx.send("Move PASS dropped by anti-spam.")
        return

    sgfengine.play_pass(str(channel_id), user.display_name)

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
        next_player=(await guild.fetch_member(state[i][4][1-colour][0]))
        next_player_text = next_player.display_name
        mention_content = next_player.mention
    elif state[i][1]=="teachers" and colour==1:
        next_player=(await guild.fetch_member(state[i][4][1-colour][0]))
        next_player_text = next_player.display_name
        mention_content = next_player.mention
    elif state[i][1]=="teachers" and colour==0:
        next_player_text = "Teachers"
        mention_content = None

    file, msg = format_game_message(channel_id, state[i], next_player_display=next_player_text, ping_mention=mention_content)
    await ctx.send(content=msg, file=file)

    with open("state.txt", "w") as f: f.write(repr(state))

@bot.command()
async def edit(ctx, arg): #literally play but with less things
    if ctx.guild.id == server_id and ctx.channel.id not in permitted_channel_ids: return
    # It should wait until the queue has 4 players or so
    channel_id= ctx.channel.id
    user = ctx.author
    guild= ctx.guild

    # lowest effort serialization
    with open("state.txt") as f: state = ast.literal_eval(f.read())

    filter_state= [i for i in range(len(state))  if state[i][0] == channel_id]
    if not filter_state:
        await ctx.send("No active game in this channel!")
        return

    i= filter_state[0]
    colour= sgfengine.next_colour(str(channel_id))

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
        sgfengine.play_move(str(channel_id), arg, user.display_name, True)
    except ValueError as e:
        await ctx.send(str(e))
        return

    next_player_text = None
    mention_content = None
    if state[i][1]=="queue":
        next_player=(await guild.fetch_member(state[i][4][colour][0]))
        next_player_text = next_player.display_name
        mention_content = next_player.mention
    elif state[i][1]=="teachers" and colour==0:
        next_player=(await guild.fetch_member(state[i][4][colour][0]))
        next_player_text = next_player.display_name
        mention_content = next_player.mention
    elif state[i][1]=="teachers" and colour==1:
        next_player_text = "Teachers"
        mention_content = None

    file, msg = format_game_message(channel_id, state[i], next_player_display=next_player_text, ping_mention=mention_content, title_override=f"Move Edited: {arg.upper()}")
    await ctx.send(content=msg, file=file)

    with open("state.txt", "w") as f: f.write(repr(state))

@bot.command()
async def board(ctx):
    if ctx.guild.id == server_id and ctx.channel.id not in permitted_channel_ids: return
    channel_id= ctx.channel.id
    user = ctx.author
    guild= ctx.guild

    with open("state.txt") as f: state = ast.literal_eval(f.read())

    filter_state= [i for i in range(len(state))  if state[i][0] == channel_id]
    if not filter_state:
        await ctx.send("No active game in this channel!")
        return

    i= filter_state[0]
    colour= sgfengine.next_colour(str(channel_id))

    sgfengine.render_png(str(channel_id))

    next_player_text = None
    if state[i][1]=="queue":
        if len(state[i][4][colour]) > 0:
            next_player=(await guild.fetch_member(state[i][4][colour][0]))
            next_player_text = next_player.display_name
        else:
            next_player_text = "Waiting for players"
    elif state[i][1]=="teachers":
        if colour==0:
            next_player=(await guild.fetch_member(state[i][4][colour][0]))
            next_player_text = next_player.display_name
        else:
            next_player_text = "Teachers"

    file, msg = format_game_message(channel_id, state[i], next_player_display=next_player_text, title_override="Current Board State")
    await ctx.send(content=msg, file=file)

@bot.command(name="history", aliases=["moves", "kifu"])
async def history(ctx, *args):
    if ctx.guild.id == server_id and ctx.channel.id not in permitted_channel_ids: return
    channel_id = str(ctx.channel.id)
    if not os.path.exists(f"{channel_id}.sgf"):
        await ctx.send("No game has been created yet in this channel. Use `$newgame` to start!")
        return

    move_range = args[0] if args else None
    hist_png = f"{channel_id}_history.png"

    sgfengine.render_png(channel_id, move_numbers=True, move_range=move_range, out_filename=hist_png)

    if not os.path.exists(hist_png):
        await ctx.send("Failed to render history board.")
        return

    info = sgfengine.get_game_state(channel_id)
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
    if ctx.guild.id == server_id and ctx.channel.id not in permitted_channel_ids: return
    channel_id= ctx.channel.id
    user = ctx.author

    # lowest effort serialization
    with open("state.txt") as f: state = ast.literal_eval(f.read())

    filter_state= [i for i in range(len(state))  if state[i][0] == channel_id]
    if not filter_state:
        await ctx.send("No active game in this channel!")
        return

    i= filter_state[0]

    if user.id in (state[i][4][0]+state[i][4][1]):
        await ctx.send("Player already in this game!")
        return

    if state[i][1] in ["random", "anarchy", "debug"]:
        await ctx.send("This game has no queue! No need to join, just `$play` whenever you want :P")
        return

    colour = 0 if len(state[i][4][0])<=len(state[i][4][1]) else 1
    if state[i][1]=="teachers": colour= 0

    state[i][4][colour].append(user.id)

    await ctx.send("{} joined Team {}!".format(user.display_name, ("Black" if colour==0 else "White")))

    with open("state.txt", "w") as f: f.write(repr(state))

@bot.command()
async def leave(ctx):
    if ctx.guild.id == server_id and ctx.channel.id not in permitted_channel_ids: return
    channel_id= ctx.channel.id
    user = ctx.author

    # lowest effort serialization
    with open("state.txt") as f: state = ast.literal_eval(f.read())

    filter_state= [i for i in range(len(state))  if state[i][0] == channel_id]
    if not filter_state:
        await ctx.send("No active game in this channel!")
        return

    i= filter_state[0]

    if user.id not in (state[i][4][0]+state[i][4][1]):
        await ctx.send("Player not in this game!")
        return

    if state[i][1] in ["random", "anarchy", "debug"]:
        await ctx.send("This game has no queue! No need to leave!")
        return

    colour = 0 if (user.id in state[i][4][0]) else 1
    state[i][4][colour].remove(user.id)

    await ctx.send("{} left :(".format(user.display_name))

    with open("state.txt", "w") as f: f.write(repr(state))

@bot.command()
async def queue(ctx):
    if ctx.guild.id == server_id and ctx.channel.id not in permitted_channel_ids: return
    channel_id= ctx.channel.id
    channel= bot.get_channel(channel_id) # thonk the order
    guild = channel.guild

    # lowest effort serialization
    with open("state.txt") as f: state = ast.literal_eval(f.read())

    filter_state= [i for i in range(len(state))  if state[i][0] == channel_id]
    if not filter_state:
        await ctx.send("No active game in this channel!")
        return

    i= filter_state[0]
    colour= sgfengine.next_colour(str(channel_id))

    if state[i][1] in ["random", "anarchy", "debug"]:
        await ctx.send("This game has no queue! No need to join, just `$play` whenever you want :P")
        return

    if state[i][1] =="teachers":
        output="Player list for Team Black: "+black_stone+"\n"
        for j, player_id in enumerate(state[i][4][0]):
            player_name=(await guild.fetch_member(player_id)).display_name
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
            player_name=(await guild.fetch_member(player_id)).display_name
            output+=white_stone+str(j+1).rjust(3)+". "+ player_name+"\n"
        output+="\n Team Black needs more members!"
        await ctx.send(output)
        return

    if state[i][4][1] == []:
        for j, player_id in enumerate(state[i][4][0]):
            player_name=(await guild.fetch_member(player_id)).display_name
            output+=black_stone+str(j+1).rjust(3)+". "+ player_name+"\n"
        output+="\n Team White needs more members!"
        await ctx.send(output)
        return

    # Which team has more members? Or in case of a tie, which team goes first?
    if len(state[i][4][colour]) > len(state[i][4][1-colour]):
        last_player = state[i][4][colour][-1]
    else: last_player= state[i][4][1-colour][-1]

    j=1
    pointers=[0,0]
    while(True):
        #print(channel_id, j, pointers, colour, state[i][0], state[i][4])
        output+= white_stone if ((colour+1) % 2 ==0)  else black_stone
        output+= str(j).rjust(3)+". "

        player_name= (await guild.fetch_member(state[i][4][colour][pointers[colour]])).display_name
        output+= player_name+"\n"

        if state[i][4][colour][pointers[colour]] == last_player: break

        pointers[colour] = (pointers[colour]+1) % len(state[i][4][colour])
        colour=1-colour

        j+=1

    if len(state[i][4][0])<min_players:
        output+="\n Team Black needs more members!"

    if len(state[i][4][1])<min_players:
        output+="\n Team White needs more members!"

    await ctx.send(output)

@bot.command()
async def sgf(ctx):
    if ctx.guild.id == server_id and ctx.channel.id not in permitted_channel_ids: return
    if not os.path.exists(str(ctx.channel.id)+".sgf"):
        await ctx.send("No active game in this channel!")
        return
    file = discord.File(str(ctx.channel.id)+".sgf")
    await ctx.send(file=file)

@bot.command()
async def newgame(ctx, gametype, handicap=0, komi=6.5):
    if ctx.guild.id == server_id and ctx.channel.id not in permitted_channel_ids: return
    channel_id= ctx.channel.id
    user = ctx.author

    if user.id not in admins:
        await ctx.send("You don't have permissions for this!")
        return

    gametype = gametype.strip().lower()
    if gametype not in ["queue", "random", "teachers", "anarchy", "debug"]:
        await ctx.send("Unrecognized game type! Please try `$newgame <queue/random/teachers/anarchy>`")
        return

    # lowest effort serialization
    with open("state.txt") as f: state = ast.literal_eval(f.read())

    if ctx.channel.id in [ ch for (ch,_,_,_,_) in state]:
        await ctx.send("A game is already active in this channel!")
        return

    sgfengine.new_game(str(ctx.channel.id), handicap, komi)
    if gametype== "teachers":
        state.append((ctx.channel.id, gametype, [], [], [[],teachers]))
    else:
        state.append((ctx.channel.id, gametype, [], [], [[],[]]))

    title = f"New Game Started • {gametype.upper()} Mode"
    file, msg = format_game_message(channel_id, state[-1], title_override=title)
    if gametype in ["queue", "teachers"]:
        msg += "\n*Join the game with `$join`*"
    else:
        msg += "\n*Play a move with `$play <move>`*"
    await ctx.send(content=msg, file=file)

    with open("state.txt", "w") as f: f.write(repr(state))

@bot.command()
async def resign(ctx, arg):
    if ctx.guild.id == server_id and ctx.channel.id not in permitted_channel_ids: return
    channel_id= ctx.channel.id
    user = ctx.author

    if user.id not in admins:
        await ctx.send("You don't have permissions for this!")
        return

    arg = arg.strip().upper()
    if arg in ["BLACK"]: arg = "B"
    if arg in ["WHITE"]: arg = "W"

    if arg not in ["W","B"]:
        await ctx.send("Unrecognized colour! Please try `$resign <B/W>` to resign as Black/White")
        return

    with open("state.txt") as f: state = ast.literal_eval(f.read())

    now=datetime.now()
    file_name= "rengo_"+now.strftime("%Y_%m_%d_%H_%M_%S_")+ctx.channel.name+".sgf" #remove the hour minute and second later

    sgfengine.resign(str(channel_id), arg, file_name)

    file = discord.File(file_name)
    await ctx.send(file=file, content=("Black" if arg=="W" else "White")+" wins!")

    state = [s for s in state if s[0]!=channel_id]

    with open("state.txt", "w") as f: f.write(repr(state))

@bot.command()
async def shutdown(ctx):
    if ctx.guild.id == server_id and ctx.channel.id not in permitted_channel_ids: return
    channel_id = ctx.channel.id
    user = ctx.author

    if user.id not in admins:
        await ctx.send("You don't have permissions for this!")
        return

    await ctx.send("🛑 Shutting down RengoBot gracefully...")
    print(f"[RengoBot] Shutdown command invoked by {user.display_name} ({user.id})")
    await bot.close()

async def background_task():
    await bot.wait_until_ready()
    print("Bot ready!")

    guild = discord.utils.get(bot.guilds, name=server_name)
    game = discord.Game("multiplayer Baduk! $help for command list")
    await bot.change_presence(status=discord.Status.online, activity=game)

    try:
        while not bot.is_closed():
            try:
                with open("state.txt") as f: state = ast.literal_eval(f.read())

                channel_id = permitted_channel_ids[0]
                channel = bot.get_channel(channel_id)

                if os.path.exists(str(channel_id) + ".sgf"):
                    colour = sgfengine.next_colour(str(channel_id))

                with open("state.txt", "w") as f: f.write(repr(state))
                await asyncio.sleep(10)

            except asyncio.CancelledError:
                break
            except Exception as e:
                pass
    except asyncio.CancelledError:
        pass


async def main():
    if os.path.exists("/data"):
        os.chdir("/data")
    bg_task = None
    try:
        async with bot:
            bg_task = bot.loop.create_task(background_task())
            await bot.start(token)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[RengoBot] Shutdown signal received. Closing cleanly...")
    finally:
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
