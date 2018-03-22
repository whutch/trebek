# -*- coding: utf-8 -*-
"""WebSocket middleware for sending messages to clients."""
# Part of Trebek (https://github.com/whutch/trebek)
# :copyright: (c) 2018 Will Hutcheson
# :license: MIT (https://github.com/whutch/trebek/blob/master/LICENSE.txt)

import asyncio
import json
import os
from os.path import abspath
import sys

import django
import websockets

sys.path.insert(0, abspath("../django"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "trebek.settings")
django.setup()
from trebek.apps.trivia.models import Question, Player


HOST_URL = "0.0.0.0"
HOST_PORT = 8765


def middleware():
    displays = {}
    admins = {}
    players = {}
    async def listen(websocket, path):
        try:
            async for message in websocket:
                msg_data = json.loads(message)
                msg_type = msg_data.get("type")
                if msg_type == "register_display":
                    game_key = msg_data["game"]
                    print("Registering display for game: " + game_key + ".")
                    displays[game_key] = websocket
                elif msg_type == "pop_question":
                    game_key = msg_data["game"]
                    question_id = msg_data["id"]
                    text = Question.objects.get(id=question_id).text
                    msg = {
                        "type": "pop_question",
                        "id": question_id,
                        "text": text,
                    }
                    display = displays[game_key]
                    await display.send(json.dumps(msg))
                elif msg_type == "unpop_question":
                    game_key = msg_data["game"]
                    msg = {
                        "type": "unpop_question",
                        "answered": msg_data["answered"],
                    }
                    display = displays[game_key]
                    await display.send(json.dumps(msg))
                elif msg_type == "register_admin":
                    game_key = msg_data["game"]
                    print("Registering admin for game: " + game_key + ".")
                    admins[game_key] = websocket
                elif msg_type == "buzz":
                    game_key = msg_data["game"]
                    player_id = msg_data["player_id"]
                    player_name = msg_data["player_name"]
                    print("Player '{}' buzzed in game {}.".format(player_name, game_key))
                    msg = {
                        "type": "buzz",
                        "player_id": player_id,
                        "player_name": player_name,
                    }
                    admin = admins[game_key]
                    await admin.send(json.dumps(msg))
                elif msg_type == "register_player":
                    game_key = msg_data["game"]
                    player_id = msg_data["id"]
                    player_name = msg_data["name"]
                    if game_key not in players:
                        players[game_key] = {}
                    players[game_key][player_id] = websocket
                    print("Registering player '{}' ({}) for game {}.".format(player_name, player_id, game_key))
                elif msg_type == "add_points":
                    game_key = msg_data["game"]
                    player_id = msg_data["player"]
                    points = msg_data["points"]
                    player = Player.objects.get(id=player_id)
                    player.score += int(points)
                    print("Adjusting score of player '{}' by {} (now {}).".format(player.name, points, player.score))
                    player.save()
                elif msg_type == "can_buzz":
                    game_key = msg_data["game"]
                    for player in players[game_key].values():
                        msg = {
                            "type": "can_buzz",
                        }
                        await player.send(json.dumps(msg))
                elif msg_type == "cant_buzz":
                    game_key = msg_data["game"]
                    for player in players[game_key].values():
                        msg = {
                            "type": "cant_buzz",
                        }
                        await player.send(json.dumps(msg))
                elif msg_type == "play_sound":
                    game_key = msg_data["game"]
                    msg = {
                        "type": "play_sound",
                        "sound": msg_data["sound"],
                    }
                    display = displays[game_key]
                    await display.send(json.dumps(msg))
                else:
                    print("Unknown message:", msg_data)
        except websockets.ConnectionClosed:
            pass
    loop = asyncio.get_event_loop()
    loop.run_until_complete(websockets.serve(listen, HOST_URL, HOST_PORT))
    loop.run_forever()


if __name__ == "__main__":
    print("Middleware started.")
    middleware()
