# RengoBot

A Discord bot for playing Rengo (multiplayer Go / Baduk) games in Discord channels!

> **Attribution:** This repository is an active fork maintained by [@peterstandard](https://github.com/peterstandard/rengobot), originally created by [@katie-oh](https://github.com/katie-oh/rengobot) with contributions from [@TimKingtonFC](https://github.com/TimKingtonFC) and the Columbus Go Club community.

# Dependencies
- sgf-render
- python-discord
- python-sgfmill

Make sure to run the bot in an environment with read/write permissions

## Game Modes

| Mode | Description | How Teams / Turns Work |
| :--- | :--- | :--- |
| **`random`** *(Casual / Community)* | Open to everyone in the channel without joining a queue. | • Alternates Black / White automatically.<br>• **Restrictions:** No two consecutive moves by the same player, no two consecutive same-color moves by the same player, and cooldown limits apply. |
| **`anarchy`** *(Free-for-all)* | Open to everyone in the channel with no turn restrictions. | • Alternates Black / White automatically.<br>• **No restrictions:** Consecutive moves and consecutive same-color moves by the same player are permitted. |
| **`queue`** *(Team Rengo)* | Players join teams via `$join` (balanced evenly). Requires at least 2 players per team. | • **FIFO Queue Rotation:** On Black's turn, only the player at the front of Black's queue can play. Once played, they rotate to the back of the queue and White is pinged. |
| **`teachers`** *(Teaching / Simban Rengo)* | Students join Team Black via `$join`. Team White is composed of authorized teacher IDs. | • **Black (Students):** Plays via queue rotation.<br>• **White (Teachers):** Any authorized teacher can play on White's turn without being restricted to a queue rotation. |
| **`debug`** *(Testing / Solo)* | Hidden mode for testing and solo play. | • Open to play directly with `$play <move>`.<br>• Bypasses consecutive move, consecutive color, and cooldown restrictions so a single tester can play both sides. |

## Commands
- `$help`: Show command help
- `$newgame <queue/random/teachers/anarchy> <handicap> <komi>`: Start a new game (Admin only)
- `$play <move>`: Play a move (e.g. `$play Q16`, `$play q16`, `$play D4`)
- `$pass`: Pass your turn (two consecutive passes concludes the game)
- `$edit <move>`: Correct your last move within 5 minutes
- `$board`: Display current board state
- `$history [range]`: Display board with move numbers on stones (e.g. `$history`, `$history 20-50`) (aliases: `$moves`, `$kifu`)
- `$sgf`: Download current game's SGF file
- `$join`: Join the game in this channel (`queue` / `teachers` modes)
- `$leave`: Leave the game in this channel
- `$queue`: View player list and queue order
- `$resign <B/W>`: Resign the game as Black or White (Admin only)
- `$shutdown`: Gracefully shut down the bot (Admin only)

## Configuration & Environment Variables
Copy `.env.example` to `.env` to configure your credentials and server details without hardcoding them into code:
```env
DISCORD_TOKEN=your_bot_token_here
SERVER_ID=your_server_id
SERVER_NAME=Your Server Name
PERMITTED_CHANNEL_IDS=channel_id_1,channel_id_2
ADMIN_IDS=user_id_1,user_id_2
TEACHER_IDS=user_id_1,user_id_2
```
Alternatively, tokens can still be placed in `token.txt` (which is gitignored).

## To run this project locally:
* Install dependencies: `pip install -r requirements.txt`
* Ensure `state.txt` exists and contains `[]`
* Set up your `.env` (or `token.txt`)
* Run `python rengobot.py` to start the bot!

##Deploying
We are currently using fly.io with a Docker image. Once you build your Docker image, you can use your image name in the `fly.toml` file
![image](https://github.com/katie-oh/rengobot/assets/56092878/281e7851-362e-47f3-90b1-9a8e58ca31a8)

Make sure that in your fly.io configuration, that there is no scaling and that the maximum number of instances is 1! 
