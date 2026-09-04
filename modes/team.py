"""Team-based game modes: Queue (Team Rengo) and Teachers mode."""

import sgfengine
from config import BLACK_STONE_EMOJI, MIN_PLAYERS, TEACHER_IDS, WHITE_STONE_EMOJI
from modes.base import BaseGameMode
from state import GameState, save_game
from ui import format_game_message, get_player_display


class QueueMode(BaseGameMode):
	"""Team Rengo with balanced Black/White queues and strict FIFO turn rotation."""

	name: str = "queue"
	description: str = "Team rengo with balanced Black/White queues and strict turn rotation."

	async def on_new_game(self, ctx, game_key: str, *args) -> GameState:
		handicap = int(args[0]) if len(args) >= 1 and str(args[0]).isdigit() else 0
		komi = float(args[1]) if len(args) >= 2 else 6.5

		sgfengine.new_game(game_key, handicap, komi)
		game = GameState(game_key=game_key, gametype=self.name, data=[[], []])
		save_game(game)

		title = f"New Game Started • {self.name.upper()} Mode"
		file, msg = format_game_message(game_key, game, title_override=title)
		msg += "\n*Join the game with `$join`*"
		await ctx.send(content=msg, file=file)
		return game

	async def validate_player_turn(
		self, ctx, game: GameState, next_colour: int
	) -> tuple[bool, str | None]:
		user_id = ctx.author.id
		black_q, white_q = game.data[0], game.data[1]

		# Must have joined
		if user_id not in (black_q + white_q):
			return False, "Player hasn't joined yet! Join us with `$join`"

		# Minimum players
		if len(black_q) < MIN_PLAYERS or len(white_q) < MIN_PLAYERS:
			return False, f"Waiting for more players to join! Minimum {MIN_PLAYERS} per team"

		# Must be user's turn
		active_team = black_q if next_colour == 0 else white_q
		if user_id != active_team[0]:
			return False, "It is not your turn yet!"

		return True, None

	async def after_move(self, ctx, game: GameState, colour: int, user_id: int) -> None:
		"""Rotates the player who just moved to the end of their team queue."""
		team = game.data[colour]
		if team and team[0] == user_id:
			team.pop(0)
			team.append(user_id)

	async def get_next_player_info(
		self, ctx, game: GameState, next_colour: int
	) -> tuple[str | None, str | None]:
		guild = ctx.guild
		team = game.data[next_colour]
		if team:
			return await get_player_display(guild, team[0])
		return "Waiting for players", None

	async def on_join(self, ctx, game: GameState) -> None:
		user = ctx.author
		black_q, white_q = game.data[0], game.data[1]

		if user.id in (black_q + white_q):
			await ctx.send("Player already in this game!")
			return

		# Balance teams evenly (join team with fewer or equal players)
		colour = 0 if len(black_q) <= len(white_q) else 1
		game.data[colour].append(user.id)
		save_game(game)

		team_name = "Black" if colour == 0 else "White"
		await ctx.send(f"{user.display_name} joined Team {team_name}!")

	async def on_leave(self, ctx, game: GameState) -> None:
		user = ctx.author
		black_q, white_q = game.data[0], game.data[1]

		if user.id not in (black_q + white_q):
			await ctx.send("Player not in this game!")
			return

		colour = 0 if user.id in black_q else 1
		game.data[colour].remove(user.id)
		save_game(game)

		await ctx.send(f"{user.display_name} left :(")

	async def on_queue(self, ctx, game: GameState) -> None:
		guild = ctx.guild
		black_q, white_q = game.data[0], game.data[1]
		colour = sgfengine.next_colour(game.game_key)

		if not black_q and not white_q:
			await ctx.send("Nobody yet! Join us with `$join`")
			return

		if not black_q:
			output = "Player list:\n"
			for j, p_id in enumerate(white_q):
				p_name, _ = await get_player_display(guild, p_id)
				output += f"{WHITE_STONE_EMOJI}{str(j + 1).rjust(3)}. {p_name}\n"
			output += f"\n Team Black needs at least {MIN_PLAYERS} members!"
			await ctx.send(output)
			return

		if not white_q:
			output = "Player list:\n"
			for j, p_id in enumerate(black_q):
				p_name, _ = await get_player_display(guild, p_id)
				output += f"{BLACK_STONE_EMOJI}{str(j + 1).rjust(3)}. {p_name}\n"
			output += f"\n Team White needs at least {MIN_PLAYERS} members!"
			await ctx.send(output)
			return

		output = "Player list:\n"
		last_player = black_q[-1] if len(black_q) > len(white_q) else white_q[-1]

		j = 1
		curr_col = colour
		pointers = [0, 0]
		while True:
			stone = WHITE_STONE_EMOJI if curr_col == 1 else BLACK_STONE_EMOJI
			p_id = game.data[curr_col][pointers[curr_col]]
			p_name, _ = await get_player_display(guild, p_id)
			output += f"{stone}{str(j).rjust(3)}. {p_name}\n"

			if p_id == last_player:
				break

			pointers[curr_col] = (pointers[curr_col] + 1) % len(game.data[curr_col])
			curr_col = 1 - curr_col
			j += 1

		if len(black_q) < MIN_PLAYERS:
			output += f"\n Team Black needs at least {MIN_PLAYERS} members!"
		if len(white_q) < MIN_PLAYERS:
			output += f"\n Team White needs at least {MIN_PLAYERS} members!"

		await ctx.send(output)


class TeachersMode(QueueMode):
	"""Students join Team Black in a queue; authorized teachers play White freely."""

	name: str = "teachers"
	description: str = "Students join Team Black in a queue; teachers play White freely."

	async def on_new_game(self, ctx, game_key: str, *args) -> GameState:
		handicap = int(args[0]) if len(args) >= 1 and str(args[0]).isdigit() else 0
		komi = float(args[1]) if len(args) >= 2 else 6.5

		sgfengine.new_game(game_key, handicap, komi)
		game = GameState(game_key=game_key, gametype=self.name, data=[[], list(TEACHER_IDS)])
		save_game(game)

		title = "New Game Started • TEACHERS Mode"
		file, msg = format_game_message(game_key, game, title_override=title)
		msg += "\n*Students join with `$join`*"
		await ctx.send(content=msg, file=file)
		return game

	async def validate_player_turn(
		self, ctx, game: GameState, next_colour: int
	) -> tuple[bool, str | None]:
		user_id = ctx.author.id
		black_q, teachers = game.data[0], game.data[1]

		if next_colour == 0:  # Student (Black)
			if user_id not in black_q:
				return False, "Player hasn't joined yet! Join us with `$join`"
			if user_id != black_q[0]:
				return False, "It is not your turn yet!"
		else:  # Teacher (White)
			if user_id not in teachers:
				return False, "Only authorized teachers can play on White's turn!"

		return True, None

	async def after_move(self, ctx, game: GameState, colour: int, user_id: int) -> None:
		"""Students rotate after move; teachers do not rotate."""
		if colour == 0 and game.data[0] and game.data[0][0] == user_id:
			game.data[0].pop(0)
			game.data[0].append(user_id)

	async def get_next_player_info(
		self, ctx, game: GameState, next_colour: int
	) -> tuple[str | None, str | None]:
		if next_colour == 0:
			if game.data[0]:
				return await get_player_display(ctx.guild, game.data[0][0])
			return "Waiting for students", None
		return "Teachers", None

	async def on_join(self, ctx, game: GameState) -> None:
		user = ctx.author
		if user.id in game.data[0]:
			await ctx.send("Player already in this game!")
			return

		game.data[0].append(user.id)
		save_game(game)
		await ctx.send(f"{user.display_name} joined Team Black!")

	async def on_queue(self, ctx, game: GameState) -> None:
		guild = ctx.guild
		black_q = game.data[0]

		if not black_q:
			await ctx.send("Nobody yet! Students can join with `$join`")
			return

		output = f"Player list for Team Black: {BLACK_STONE_EMOJI}\n"
		for j, p_id in enumerate(black_q):
			p_name, _ = await get_player_display(guild, p_id)
			output += f"{str(j + 1).rjust(3)}. {p_name}\n"
		await ctx.send(output)
