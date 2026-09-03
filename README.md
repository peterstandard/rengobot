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
| **`vote`** *(Collective Voting)* | Everyone in the channel votes for moves. Countdown starts on the first vote. | • `$newgame vote <minutes> [handicap] [komi]`<br>• When a player votes with `$play <move>` or `$pass`, an N-minute timer begins.<br>• Players can change their vote anytime before the deadline.<br>• When the timer expires, the move with the most votes is played (ties broken randomly). |
| **`random`** *(Casual / Community)* | Open to everyone in the channel without joining a queue. | • Alternates Black / White automatically.<br>• **Restrictions:** No two consecutive moves by the same player, no two consecutive same-color moves by the same player, and cooldown limits apply. |
| **`anarchy`** *(Free-for-all)* | Open to everyone in the channel with no turn restrictions. | • Alternates Black / White automatically.<br>• **No restrictions:** Consecutive moves and consecutive same-color moves by the same player are permitted. |
| **`queue`** *(Team Rengo)* | Players join teams via `$join` (balanced evenly). Requires at least 2 players per team. | • **FIFO Queue Rotation:** On Black's turn, only the player at the front of Black's queue can play. Once played, they rotate to the back of the queue and White is pinged. |
| **`teachers`** *(Teaching / Simban Rengo)* | Students join Team Black via `$join`. Team White is composed of authorized teacher IDs. | • **Black (Students):** Plays via queue rotation.<br>• **White (Teachers):** Any authorized teacher can play on White's turn without being restricted to a queue rotation. |
| **`debug`** *(Testing / Solo)* | Hidden mode for testing and solo play. | • Open to play directly with `$play <move>`.<br>• Bypasses consecutive move, consecutive color, and cooldown restrictions so a single tester can play both sides. |

## Commands
- `$help`: Show command help
- `$newgame <mode> [options]`: Start a new game (e.g. `$newgame vote 15`, `$newgame random 0 6.5`) (Admin only)
- `$play <move>`: Play a move or cast your vote (e.g. `$play Q16`, `$play q16`, `$play D4`)
- `$pass`: Pass your turn or vote to pass
- `$votes`: View current voting standings and countdown timer (`vote` mode)
- `$edit <move>`: Correct your last move within 5 minutes
- `$board`: Display current board state
- `$history [range]`: Display board with move numbers on stones (e.g. `$history`, `$history 20-50`) (aliases: `$moves`, `$kifu`)
- `$sgf`: Download current game's SGF file
- `$join`: Join the game in this channel (`queue` / `teachers` modes)
- `$leave`: Leave the game in this channel
- `$queue`: View player list and queue order
- `$resign <B/W>`: Resign the game as Black or White (Admin only)
- `$channels`: Show active game channels on this server
- `$listen`: Enable Rengo in this channel (Admin only)
- `$unlisten`: Disable Rengo in this channel (Admin only)
- `$shutdown`: Gracefully shut down the bot container (Global admin only)

## Configuration & Environment Variables
Copy `.env.example` to `.env` to configure your credentials and server details without hardcoding them into code:
```env
DISCORD_TOKEN=your_bot_token_here
PERMITTED_SERVER_IDS=server_id_1,server_id_2
PERMITTED_CHANNEL_IDS=channel_id_1,channel_id_2
ADMIN_IDS=user_id_1,user_id_2
TEACHER_IDS=user_id_1,user_id_2
```
Alternatively, tokens can still be placed in `token.txt` (which is gitignored).

## Deploying with Docker (Recommended for VPS)

1. Clone the repository on your server:
   ```bash
   git clone https://github.com/peterstandard/rengobot.git
   cd rengobot/rengobot
   ```
2. Create your `.env` configuration:
   ```bash
   cp .env.example .env
   nano .env  # Add your DISCORD_TOKEN, SERVER_ID, etc.
   ```
3. Start the bot with Docker Compose:
   ```bash
   docker compose up -d --build
   ```
4. Useful commands:
   - **View live logs:** `docker compose logs -f`
   - **Restart bot:** `docker compose restart`
   - **Stop bot:** `docker compose down`
   - **Update to latest code:** `git pull && docker compose up -d --build`

All active game states and `.sgf` records persist in the `./data` directory on the host.

## To run locally without Docker:
* Install Rust dependencies: `cargo install sgf-render resvg`
* Install Python dependencies: `pip install -r requirements.txt`
* Set up your `.env` file
* Run `python rengobot.py` to start the bot! 
