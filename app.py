"""Local development server for X-O Arena."""

from __future__ import annotations

import os
import math
import re
import secrets
import string
import threading
import time
from typing import Any

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room as socket_leave_room

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "local-xo-arena-development-key")
socketio = SocketIO(app, async_mode="threading")

rooms: dict[str, dict[str, Any]] = {}
sid_to_room: dict[str, str] = {}
rooms_lock = threading.RLock()

WINNING_LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
)
ROOM_CODE_PATTERN = re.compile(r"^[A-Z0-9]{6}$")
TURN_SECONDS = 60


@app.route("/")
def index() -> str:
    return render_template("index.html")


def _new_room_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        if code not in rooms:
            return code


def _room_state(room: dict[str, Any]) -> dict[str, Any]:
    deadline = room["turn_deadline"]
    remaining = max(0, math.ceil(deadline - time.monotonic())) if deadline is not None else None
    return {
        "board": list(room["board"]),
        "turn": room["turn"],
        "players": len(room["players"]),
        "status": room["status"],
        "winner": room["winner"],
        "finishReason": room["finish_reason"],
        "remainingSeconds": remaining,
        "scores": dict(room["scores"]),
        "roundNumber": room["round_number"],
        "matchWinner": room["match_winner"],
        "roundsTotal": 3,
    }


def _record_round_result(room: dict[str, Any]) -> None:
    if room["winner"] in ("X", "O"):
        room["scores"][room["winner"]] += 1

    if room["winner"] in ("X", "O") and room["scores"][room["winner"]] >= 2:
        room["match_winner"] = room["winner"]
    elif room["round_number"] >= 3:
        x_score = room["scores"]["X"]
        o_score = room["scores"]["O"]
        room["match_winner"] = "X" if x_score > o_score else "O" if o_score > x_score else "DRAW"


def _expire_turn(room: dict[str, Any]) -> bool:
    deadline = room["turn_deadline"]
    if room["status"] != "playing" or deadline is None or time.monotonic() < deadline:
        return False
    room["winner"] = "O" if room["turn"] == "X" else "X"
    room["status"] = "finished"
    room["finish_reason"] = "timeout"
    room["turn_deadline"] = None
    _record_round_result(room)
    return True


def _room_timer_loop(code: str) -> None:
    last_sent_second: int | None = None
    while True:
        socketio.sleep(0.2)
        game_update = None
        timer_update = None
        with rooms_lock:
            room = rooms.get(code)
            if room is None:
                return
            if _expire_turn(room):
                game_update = _room_state(room)
                last_sent_second = None
            elif room["status"] == "playing":
                remaining = _room_state(room)["remainingSeconds"]
                if remaining != last_sent_second:
                    timer_update = {"turn": room["turn"], "remainingSeconds": remaining}
                    last_sent_second = remaining
            else:
                last_sent_second = None

        if timer_update is not None:
            socketio.emit("timer_update", timer_update, to=code)
        if game_update is not None:
            socketio.emit("game_update", game_update, to=code)


def _read_room_code(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    value = data.get("code")
    if not isinstance(value, str):
        return None
    code = value.strip().upper()
    return code if ROOM_CODE_PATTERN.fullmatch(code) else None


def _error(message: str) -> None:
    emit("error_message", {"message": message})


@socketio.on("create_room")
def create_room(_data: Any = None) -> None:
    sid = request.sid
    with rooms_lock:
        if sid in sid_to_room:
            _error("Leave your current room before creating another one.")
            return
        code = _new_room_code()
        room = {
            "players": {sid: "X"},
            "board": [""] * 9,
            "turn": "X",
            "starting_symbol": "X",
            "status": "waiting",
            "winner": None,
            "finish_reason": None,
            "turn_deadline": None,
            "timer_worker_started": False,
            "scores": {"X": 0, "O": 0},
            "round_number": 1,
            "match_winner": None,
        }
        rooms[code] = room
        sid_to_room[sid] = code
        join_room(code)
        emit("room_created", {"code": code, "symbol": "X"})
        emit("game_update", _room_state(room))


@socketio.on("join_room")
def handle_join(data: Any) -> None:
    sid = request.sid
    code = _read_room_code(data)
    if code is None:
        _error("Enter a valid six-character room code.")
        return

    start_timer = False
    with rooms_lock:
        if sid in sid_to_room:
            _error("Leave your current room before joining another one.")
            return
        room = rooms.get(code)
        if room is None:
            _error("That room was not found. Check the code and try again.")
            return
        if len(room["players"]) >= 2:
            _error("That room is full.")
            return

        occupied_symbols = set(room["players"].values())
        symbol = "X" if "X" not in occupied_symbols else "O"
        room["players"][sid] = symbol
        sid_to_room[sid] = code
        room["status"] = "playing"
        room["turn"] = room["starting_symbol"]
        room["turn_deadline"] = time.monotonic() + TURN_SECONDS
        if not room["timer_worker_started"]:
            room["timer_worker_started"] = True
            start_timer = True
        join_room(code)
        emit("room_joined", {"code": code, "symbol": symbol})
        socketio.emit("game_update", _room_state(room), to=code)
    if start_timer:
        socketio.start_background_task(_room_timer_loop, code)


def _remove_player(sid: str, reason: str) -> None:
    with rooms_lock:
        code = sid_to_room.pop(sid, None)
        if code is None:
            return
        room = rooms.get(code)
        if room is None:
            return
        room["players"].pop(sid, None)
        if not room["players"]:
            rooms.pop(code, None)
            return

        room["board"] = [""] * 9
        room["turn"] = room["starting_symbol"]
        room["status"] = "waiting"
        room["winner"] = None
        room["finish_reason"] = None
        room["turn_deadline"] = None
        room["scores"] = {"X": 0, "O": 0}
        room["round_number"] = 1
        room["match_winner"] = None
        room["starting_symbol"] = "X"
        notice = (
            "Your opponent left the room. Waiting for another player."
            if reason == "left"
            else "Your opponent disconnected. Waiting for another player."
        )
        socketio.emit("player_left", {"message": notice}, to=code, skip_sid=sid)
        socketio.emit("game_update", _room_state(room), to=code, skip_sid=sid)


@socketio.on("leave_room")
def handle_leave(_data: Any = None) -> None:
    sid = request.sid
    with rooms_lock:
        code = sid_to_room.get(sid)
        if code is not None:
            socket_leave_room(code)
    _remove_player(sid, "left")


@socketio.on("make_move")
def make_move(data: Any) -> None:
    sid = request.sid
    if not isinstance(data, dict):
        _error("That move could not be read. Try again.")
        return
    code = _read_room_code(data)
    index = data.get("index")
    if code is None or isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < 9:
        _error("That move is not valid.")
        return

    with rooms_lock:
        room = rooms.get(code)
        if room is None or sid_to_room.get(sid) != code or sid not in room["players"]:
            _error("You are not a player in that room.")
            return
        if room["status"] != "playing" or len(room["players"]) != 2:
            _error("The game is waiting for another player.")
            return
        if _expire_turn(room):
            socketio.emit("game_update", _room_state(room), to=code)
            return
        if room["winner"] is not None:
            _error("This round is over. Choose Restart game to play again.")
            return
        symbol = room["players"][sid]
        if symbol != room["turn"]:
            _error("It is the other player's turn.")
            return
        if room["board"][index] != "":
            _error("That square is already taken.")
            return

        room["board"][index] = symbol
        if any(all(room["board"][cell] == symbol for cell in line) for line in WINNING_LINES):
            room["winner"] = symbol
            room["status"] = "finished"
            room["finish_reason"] = "win"
            room["turn_deadline"] = None
        elif all(room["board"]):
            room["winner"] = "DRAW"
            room["status"] = "finished"
            room["finish_reason"] = "draw"
            room["turn_deadline"] = None
        else:
            room["turn"] = "O" if symbol == "X" else "X"
            room["turn_deadline"] = time.monotonic() + TURN_SECONDS
        if room["status"] == "finished":
            _record_round_result(room)
        socketio.emit("game_update", _room_state(room), to=code)


@socketio.on("restart_game")
def restart_game(_data: Any = None) -> None:
    sid = request.sid
    with rooms_lock:
        code = sid_to_room.get(sid)
        room = rooms.get(code) if code is not None else None
        if room is None or sid not in room["players"]:
            _error("Join a room before restarting a game.")
            return
        if room["status"] != "finished" or len(room["players"]) != 2:
            _error("You can restart after the game is over.")
            return

        if room["match_winner"] is None:
            room["round_number"] += 1
        else:
            room["round_number"] = 1
            room["scores"] = {"X": 0, "O": 0}
            room["match_winner"] = None
        room["starting_symbol"] = "O" if room["starting_symbol"] == "X" else "X"
        room["turn"] = room["starting_symbol"]
        room["board"] = [""] * 9
        room["winner"] = None
        room["finish_reason"] = None
        room["status"] = "playing"
        room["turn_deadline"] = time.monotonic() + TURN_SECONDS
        socketio.emit("game_update", _room_state(room), to=code)


@socketio.on("disconnect")
def handle_disconnect(_reason: str | None = None) -> None:
    _remove_player(request.sid, "disconnected")


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    socketio.run(
        app,
        host=host,
        port=port,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )
