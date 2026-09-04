# Needs sgf-render and sgfmill
# https://mjw.woodcraft.me.uk/sgfmill/doc/1.1.1/properties.html?highlight=list%20properties
import os

from sgfmill import boards, sgf, sgf_moves

if "PATH" in os.environ and os.path.expanduser("~/.cargo/bin") not in os.environ["PATH"]:
	os.environ["PATH"] = (
		os.path.expanduser("~/.cargo/bin") + os.pathsep + os.environ.get("PATH", "")
	)

import subprocess

# This file only deals with the png and sgf side of things. To manage users etc go to the main file.


def render_png(channel_id, move_numbers=False, move_range=None, out_filename=None):
	base_dir = os.path.dirname(os.path.abspath(__file__))
	style_path = os.path.join(base_dir, "board_style.toml")
	style_arg = f"--custom-style {style_path}" if os.path.exists(style_path) else "--style fancy"
	sgf_path = f"{channel_id}.sgf"
	png_path = out_filename if out_filename else f"{channel_id}.png"
	svg_path = f"{channel_id}_temp.svg"

	move_num_arg = ""
	if move_numbers:
		if move_range:
			move_num_arg = f"--move-numbers={move_range}"
		else:
			move_num_arg = "--move-numbers"

	try:
		cmd = f"sgf-render -f svg {style_arg} --label-sides sw {move_num_arg} -n last {sgf_path}"
		proc = subprocess.run(
			cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
		)
		if proc.returncode == 0 and proc.stdout:
			svg_data = proc.stdout

			svg_data = svg_data.replace(
				'font-family="Inter"', 'font-family="Noto Sans, sans-serif"'
			)
			svg_data = svg_data.replace('font-size="0.45"', 'font-size="0.70"')

			# Only replace coordinates in board-labels (protect move numbers on stones)
			if 'id="board-labels"' in svg_data:
				parts = svg_data.split('id="board-labels"', 1)
				before = parts[0]
				after = parts[1]

				# Highlight special star point coordinates in solid black #000000
				for target in [">D<", ">K<", ">Q<", ">4<", ">10<", ">16<"]:
					after = after.replace(
						target, target.replace(">", ' fill="#000000" font-weight="900">')
					)

				svg_data = before + 'id="board-labels"' + after

			with open(svg_path, "w") as f:
				f.write(svg_data)

			resvg_cmd = f"resvg {svg_path} {png_path}"
			resvg_proc = subprocess.run(
				resvg_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
			)
			if os.path.exists(svg_path):
				os.remove(svg_path)
			if resvg_proc.returncode == 0 and os.path.exists(png_path):
				return
	except Exception:
		pass

	os.system(
		f"sgf-render -f png {style_arg} --label-sides sw {move_num_arg} -o {png_path} -n last {sgf_path}"
	)


def new_game(channel_id, handicap=0, komi=6.5):
	game = sgf.Sgf_game(19)
	game.root.set("KM", float(komi))
	game.root.set("RU", "AGA")
	handicap = int(handicap)
	if handicap >= 2:
		game.root.set("HA", handicap)

		handicap_dict = {
			2: [(3, 3), (15, 15)],
			3: [(3, 3), (15, 15), (15, 3)],
			4: [(3, 3), (15, 15), (15, 3), (3, 15)],
			5: [(3, 3), (15, 15), (15, 3), (3, 15), (9, 9)],
			6: [(3, 3), (15, 15), (15, 3), (3, 15), (9, 3), (9, 15)],
			7: [(3, 3), (15, 15), (15, 3), (3, 15), (9, 3), (9, 15), (9, 9)],
			8: [(3, 3), (15, 15), (15, 3), (3, 15), (9, 3), (9, 15), (3, 9), (15, 9)],
			9: [(3, 3), (15, 15), (15, 3), (3, 15), (9, 3), (9, 15), (3, 9), (15, 9), (9, 9)],
		}
		game.root.set("AB", handicap_dict[handicap])

	with open(str(channel_id) + ".sgf", "wb") as f:
		f.write(game.serialise())

	render_png(channel_id)


# 0 if black to play, 1 if white to play
def next_colour(channel_id):
	with open(str(channel_id) + ".sgf", "rb") as f:
		game = sgf.Sgf_game.from_bytes(f.read())
	node = game.get_last_node()
	return 1 if ("B" in node.properties() or "AB" in node.properties()) else 0


def get_last_move_formatted(channel_id):
	if not os.path.exists(str(channel_id) + ".sgf"):
		return None
	try:
		with open(str(channel_id) + ".sgf", "rb") as f:
			game = sgf.Sgf_game.from_bytes(f.read())
		node = game.get_last_node()
		if node == game.root:
			return None
		for col_prop in ("B", "W"):
			if node.has_property(col_prop):
				move_val = node.get(col_prop)
				if move_val is None:
					return "Pass"
				row, col = move_val
				col_letter = chr(col + ord("A") + (1 if col >= 8 else 0))
				row_number = str(row + 1)
				return f"{col_letter}{row_number}"
	except Exception:
		pass
	return None


def get_game_state(channel_id):
	filename = str(channel_id) + ".sgf"
	if not os.path.exists(filename):
		return None
	with open(filename, "rb") as f:
		game = sgf.Sgf_game.from_bytes(f.read())

	board, moves = sgf_moves.get_setup_and_moves(game)

	black_captures = 0
	white_captures = 0
	consecutive_passes = 0
	last_move_str = None

	replay_board = boards.Board(19)
	if game.root.has_property("AB"):
		for r, c in game.root.get("AB"):
			replay_board.play(r, c, "b")

	for colour, move in moves:
		if move is None:
			consecutive_passes += 1
			last_move_str = "Pass"
		else:
			consecutive_passes = 0
			row, col = move
			opp_colour = "w" if colour == "b" else "b"
			opp_before = sum(
				1 for r in range(19) for c in range(19) if replay_board.get(r, c) == opp_colour
			)
			replay_board.play(row, col, colour)
			opp_after = sum(
				1 for r in range(19) for c in range(19) if replay_board.get(r, c) == opp_colour
			)
			captured = opp_before - opp_after
			if colour == "b":
				black_captures += captured
			else:
				white_captures += captured
			col_letter = chr(col + ord("A") + (1 if col >= 8 else 0))
			last_move_str = f"{col_letter}{row + 1}"

	last_node = game.get_last_node()
	last_player = last_node.get("C") if last_node.has_property("C") else None

	last_colour = None
	if last_node.has_property("B"):
		last_colour = "B"
	elif last_node.has_property("W"):
		last_colour = "W"

	next_col = (
		1
		if (last_colour == "B" or (last_node == game.root and game.root.has_property("AB")))
		else 0
	)
	next_colour_str = "W" if next_col == 1 else "B"

	handicap = game.root.get("HA") if game.root.has_property("HA") else 0
	komi = game.root.get("KM") if game.root.has_property("KM") else 6.5
	ruleset = game.root.get("RU") if game.root.has_property("RU") else "AGA"

	return {
		"move_count": len(moves),
		"last_move": last_move_str,
		"last_player": last_player,
		"last_colour": last_colour,
		"next_colour": next_colour_str,
		"captures": {"B": black_captures, "W": white_captures},
		"consecutive_passes": consecutive_passes,
		"handicap": handicap,
		"komi": komi,
		"ruleset": ruleset,
	}


def validate_move(channel_id, messagestr):
	if messagestr.strip().upper() == "PASS":
		return True, None
	messagestr = messagestr.strip()
	try:
		thecol = ord(messagestr[0].lower()) - ord("a")
		if thecol > 8:
			thecol -= 1
		therow = int(messagestr[1:]) - 1
	except Exception:
		return False, "I don't understand the move! Please use format like Q16 or Pass."

	if not (0 <= thecol < 19 and 0 <= therow < 19):
		return False, "Move coordinate is out of bounds!"

	filename = str(channel_id) + ".sgf"
	if not os.path.exists(filename):
		return False, "No active game in this channel!"

	with open(filename, "rb") as f:
		game = sgf.Sgf_game.from_bytes(f.read())

	koban = None
	node = game.get_last_node()
	board, moves = sgf_moves.get_setup_and_moves(game)

	for colour, (row, col) in moves:
		if (row, col) is not None:
			koban = board.play(row, col, colour)

	if (therow, thecol) == koban:
		return False, "Ko banned move!"

	colour = "w" if ("B" in node.properties() or "AB" in node.properties()) else "b"

	board2 = board.copy()
	try:
		board2.play(therow, thecol, colour)
	except ValueError:
		return False, "Illegal move! There is a stone there."

	if board2.get(therow, thecol) is None:
		return False, "Illegal move! No self-captures allowed."

	return True, None


# outputs to <channel_id>.png
def play_move(channel_id, messagestr, player, overwrite=False):

	thecol = ord(messagestr[0].lower()) - ord("a")
	if thecol > 8:
		thecol -= 1  # Go boards don't have an I column!!
	therow = int(messagestr[1:]) - 1

	with open(str(channel_id) + ".sgf", "rb") as f:
		game = sgf.Sgf_game.from_bytes(f.read())

	koban = None
	node = game.get_last_node()
	board, moves = sgf_moves.get_setup_and_moves(game)
	if overwrite:
		node2 = node.parent
		node.delete()
		node = node2
		moves = moves[:-1]

	for colour, (row, col) in moves:
		if (row, col) is not None:
			koban = board.play(row, col, colour)

	if (therow, thecol) == koban:
		raise ValueError("Ko banned move!")

	colour = "w" if ("B" in node.properties() or "AB" in node.properties()) else "b"

	board2 = board.copy()
	try:
		koban2 = board2.play(therow, thecol, colour)
	except ValueError:
		raise ValueError("Illegal move! There is a stone there.")

	if board2.get(therow, thecol) is None:
		raise ValueError("Illegal move! No self-captures allowed.")

	node2 = node.new_child()
	node2.set(("B" if colour == "b" else "W"), (therow, thecol))
	if koban2 is not None:
		node2.set("SQ", [koban2])
	node2.set("CR", [(therow, thecol)])
	node2.set("C", player)  # I think this would be fun for the review
	if node.has_property("CR"):
		node.unset("CR")
	if node.has_property("SQ"):
		node.unset("SQ")

	with open(str(channel_id) + ".sgf", "wb") as f:
		f.write(game.serialise())

	render_png(channel_id)


def play_pass(channel_id, player):
	with open(str(channel_id) + ".sgf", "rb") as f:
		game = sgf.Sgf_game.from_bytes(f.read())

	node = game.get_last_node()
	colour = "w" if ("B" in node.properties() or "AB" in node.properties()) else "b"

	node2 = node.new_child()
	node2.set(("B" if colour == "b" else "W"), None)
	node2.set("C", player)
	if node.has_property("CR"):
		node.unset("CR")
	if node.has_property("SQ"):
		node.unset("SQ")

	with open(str(channel_id) + ".sgf", "wb") as f:
		f.write(game.serialise())

	render_png(channel_id)


# colour is "B" if black resigns, "W" if white resigns
def resign(channel_id, colour, file_name):
	with open(str(channel_id) + ".sgf", "rb") as f:
		game = sgf.Sgf_game.from_bytes(f.read())

	node = game.root
	node.set("RE", ("B" if colour == "W" else "W") + "+R")

	with open(file_name, "wb") as f:
		f.write(game.serialise())

	if os.path.exists(str(channel_id) + ".sgf"):
		os.remove(str(channel_id) + ".sgf")
	if os.path.exists(str(channel_id) + ".png"):
		os.remove(str(channel_id) + ".png")
