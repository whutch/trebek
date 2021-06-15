# -*- coding: utf-8 -*-
"""WebSocket middleware for sending messages to clients."""
# Part of Trebek (https://github.com/whutch/trebek)
# :copyright: (c) 2018 Will Hutcheson
# :license: MIT (https://github.com/whutch/trebek/blob/master/LICENSE.txt)

import asyncio
from collections import deque
import itertools
import json
import logging
import os
from os.path import abspath, dirname, join
import ssl
import sys
import time
import uuid

from asgiref.sync import sync_to_async
import django
import websockets

BASE_DIR = abspath(join(dirname(__file__), ".."))
DJANGO_DIR = join(BASE_DIR, "django")
sys.path.insert(0, DJANGO_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "trebek.settings")
django.setup()
from trebek import settings
from trebek.apps.trivia import models


HOST_URL = "0.0.0.0"
HOST_PORT = 8765


class MessageTypes:
    ERROR = 0
    PING = 1
    ADMIN_CONNECTED = 10
    DISPLAY_CONNECTED = 11
    PLAYER_CONNECTED = 12
    GAME_RESET = 21
    CHANGE_ROUND = 22
    POP_QUESTION = 30
    CLEAR_QUESTION = 31
    PLAYER_BUZZED = 40
    CLEAR_BUZZ = 41
    CLEAR_ALL_BUZZES = 42
    UPDATE_SCORE = 50
    PLAY_SOUND = 60
    TOGGLE_SCOREBOARD = 70


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("middleware")

GAMES = {}


async def mark_question_answered(game_key, question_id):
    try:
        game = await sync_to_async(models.Game.objects.get)(key=game_key)
    except models.Game.DoesNotExist:
        log.warning(f"Game key does not exist in database: {game_key}")
        return
    try:
        question_state = await sync_to_async(models.QuestionState.objects.get)(game_round__game=game, question__id=question_id)
    except models.Question.DoesNotExist:
        log.warning(f"Question does not have state in game: {question_id}, {game_key}")
        return
    question_state.answered = True
    await sync_to_async(question_state.save)()


def parse_message(msg):
    try:
        msg_data = json.loads(msg)
    except:
        raise
    if not "type" in msg_data:
        log.error(f"Message has no type: {msg_data}")
        return None, msg_data
    msg_type = msg_data.pop("type")
    return msg_type, msg_data


class Game:

    def __init__(self, game_key):
        self.key = game_key
        self.admins = set()
        self.displays = set()
        self.players = set()
        self.popped_question_uuid = None
        self.popped_question_real_id = None
        self.popped_question_text = None
        self.buzzes = deque()
        self._game = None
        GAMES[game_key] = self

    def get_round(self):
        if not self._game:
            self._game = models.Game.objects.get(key=self.key)
        return self._game.current_round

    def set_round(self, value):
        if not self._game:
            self._game = models.Game.objects.get(key=self.key)
        self._game.current_round = value
        self._game.save()

    def get_final_round(self):
        if not self._game:
            self._game = models.Game.objects.get(key=self.key)
        return self._game.rounds.last().round

    def reset(self):
        if not self._game:
            self._game = models.Game.objects.get(key=self.key)
        self._game.reset()

    def register_client(self, client):
        if isinstance(client, Admin):
            log.info(f"Registering admin for game {self.key}.")
            self.admins.add(client)
        elif isinstance(client, Display):
            log.info(f"Registering display for game {self.key}.")
            self.displays.add(client)
        elif isinstance(client, Player):
            log.info(f"Registering player '{client.name}' ({client.id}) for game {self.key}.")
            self.players.add(client)
        elif isinstance(client, Client):
            log.error(f"Client subclass not recognized: {client}")
        else:
            log.error(f"Tried to register {client} as a client!")


class Client:

    def __init__(self, websocket, game_key):
        self._ws = websocket
        if not game_key in GAMES:
            game = Game(game_key)
            self.game = game
        else:
            self.game = GAMES[game_key]
        self.game.register_client(self)

    def __eq__(self, other):
        return hasattr(other, "_ws") and self._ws == other._ws

    def __hash__(self):
        return hash(self._ws)

    @classmethod
    async def new(cls, *args, **kwargs):
        return cls(*args, **kwargs)

    async def handler(self):
        async for msg in self._ws:
            msg_type, msg_data = parse_message(msg)
            if not msg_type:
                continue
            await self.handle_message(msg_type, msg_data)

    async def handle_message(self, msg_type, msg_data):
        raise NotImplementedError

    async def send_message(self, msg_type, msg_data={}):
        # Building these dicts is inefficient when send_message is called in a loop with the same data,
        #  but it's fine for our small-scale purposes now.
        if not self._ws.open:
            return
        msg = {}
        msg["type"] = msg_type
        msg.update(msg_data)
        await self._ws.send(json.dumps(msg))


class Admin(Client):

    @classmethod
    async def new(cls, *args, **kwargs):
        admin = cls(*args, **kwargs)
        # Forward admin connections to all players.
        for player in admin.game.players:
            await player.send_message(MessageTypes.ADMIN_CONNECTED)
        # If there is a question popped, let the admin know.
        if admin.game.popped_question_real_id:
            await admin.send_message(MessageTypes.POP_QUESTION, {
                "question_id": admin.game.popped_question_real_id,
            })
        # If players have buzzed, let the admin know.
        for buzz in admin.game.buzzes:
            msg_data = {
                "player_id": buzz.id,
                "player_name": buzz.name,
                "no_sound": True,
            }
            await admin.send_message(MessageTypes.PLAYER_BUZZED, msg_data)
        return admin

    async def handle_message(self, msg_type, msg_data):
        if not msg_type:
            return
        elif msg_type == MessageTypes.GAME_RESET:
            log.info(f"Reseting game {self.game.key}.")
            self.game.popped_question_real_id = None
            self.game.popped_question_uuid = None
            self.game.popped_question_text = None
            self.game.buzzes.clear()
            await sync_to_async(self.game.reset)()
            # Pass it on to everything.
            for client in itertools.chain(self.game.admins, self.game.displays, self.game.players):
                await client.send_message(MessageTypes.GAME_RESET)
        elif msg_type == MessageTypes.CHANGE_ROUND:
            new_round = msg_data["round"]
            if new_round < 1:
                return
            round = await sync_to_async(self.game.get_round)()
            final_round = await sync_to_async(self.game.get_final_round)()
            if round == new_round or new_round > final_round:
                return
            log.info(f"Changing to round {new_round} in game {self.game.key}.")
            self.game.popped_question_real_id = None
            self.game.popped_question_uuid = None
            self.game.popped_question_text = None
            self.game.buzzes.clear()
            await sync_to_async(self.game.set_round)(new_round)
            # Pass it on to everything.
            for client in itertools.chain(self.game.admins, self.game.displays, self.game.players):
                await client.send_message(MessageTypes.CHANGE_ROUND, msg_data)
        elif msg_type == MessageTypes.POP_QUESTION:
            # Update pings first.
            for player in self.game.players:
                await player.send_message(MessageTypes.PING, {
                    "start_time": time.time(),
                })
            self.game.popped_question_real_id = msg_data["question_id"]
            self.game.popped_question_text = msg_data["question_text"]
            self.game.buzzes.clear()
            # Pass it on to the displays.
            for display in self.game.displays:
                await display.send_message(MessageTypes.POP_QUESTION, msg_data)
            # Inject a question UUID before passing it on to the players.
            question_uuid = str(uuid.uuid4())
            self.game.popped_question_uuid = question_uuid
            msg_data["question_id"] = question_uuid
            for player in self.game.players:
                await player.send_message(MessageTypes.POP_QUESTION, msg_data)
        elif msg_type == MessageTypes.CLEAR_QUESTION:
            self.game.popped_question_real_id = None
            self.game.popped_question_uuid = None
            self.game.popped_question_text = None
            self.game.buzzes.clear()
            # Mark the question as answered.
            if msg_data.get("answered"):
                question_id = msg_data["question_id"]
                await mark_question_answered(self.game.key, question_id)
            # Pass it on to the displays.
            for display in self.game.displays:
                await display.send_message(MessageTypes.CLEAR_QUESTION, msg_data)
            # Strip out the question_id before passing it on to the players.
            del msg_data["question_id"]
            for player in self.game.players:
                await player.send_message(MessageTypes.CLEAR_QUESTION, msg_data)
        elif msg_type == MessageTypes.CLEAR_BUZZ:
            self.game.buzzes.popleft()
            # Pass it on to other admins.
            for admin in self.game.admins:
                if admin is self:
                    continue
                await admin.send_message(MessageTypes.CLEAR_BUZZ)
        elif msg_type == MessageTypes.CLEAR_ALL_BUZZES:
            self.game.buzzes.clear()
            # Pass it on to other admins.
            for admin in self.game.admins:
                if admin is self:
                    continue
                await admin.send_message(MessageTypes.CLEAR_ALL_BUZZES)
        elif msg_type == MessageTypes.UPDATE_SCORE:
            player_id = msg_data["player_id"]
            score = msg_data["score"]
            player_object = await sync_to_async(models.Player.objects.get)(id=player_id)
            log.info(f"Received score update for player '{player_object.name}' ({player_object.id})"
                     f" of game {self.game.key}, new value is {score}.")
            player_object.score = score
            await sync_to_async(player_object.save)()
            # Pass it on to the displays.
            for display in self.game.displays:
                await display.send_message(MessageTypes.UPDATE_SCORE, msg_data)
        elif msg_type == MessageTypes.PLAY_SOUND:
            # Pass it on to the displays and players.
            for client in itertools.chain(self.game.displays, self.game.players):
                await client.send_message(MessageTypes.PLAY_SOUND, msg_data)
        elif msg_type == MessageTypes.TOGGLE_SCOREBOARD:
            # Pass it on to the displays.
            for display in self.game.displays:
                await display.send_message(MessageTypes.TOGGLE_SCOREBOARD)
        else:
            log.warning(f"Admin sent unhandled message type '{msg_type}': {msg_data}")


class Display(Client):

    @classmethod
    async def new(cls, *args, **kwargs):
        display = cls(*args, **kwargs)
        # If there is a question popped, let the display know.
        if display.game.popped_question_real_id:
            await display.send_message(MessageTypes.POP_QUESTION, {
                "question_id": display.game.popped_question_real_id,
                "question_text": display.game.popped_question_text,
            })
        return display

    async def handle_message(self, msg_type, msg_data):
        if not msg_type:
            return
        else:
            # We don't currently handle any messages from displays.
            log.warning(f"Display sent unhandled message type '{msg_type}': {msg_data}")


class Player(Client):

    def __init__(self, websocket, game_key, player_id, player_name):
        self.id = player_id
        self.name = player_name
        self.ping = -1
        super().__init__(websocket, game_key)

    @classmethod
    async def new(cls, *args, **kwargs):
        player = cls(*args, **kwargs)
        # If there's an admin in our game already, let the player know.
        if player.game.admins:
            await player.send_message(MessageTypes.ADMIN_CONNECTED)
        # Pass the player data on to the admins and displays.
        player_object = await sync_to_async(models.Player.objects.get)(id=player.id)
        for client in itertools.chain(player.game.admins, player.game.displays):
            await client.send_message(MessageTypes.PLAYER_CONNECTED, {
                "player_id": player.id,
                "player_name": player.name,
                "score": player_object.score,
            })
        # If there is a question popped, let the player know.
        if player.game.popped_question_real_id:
            await player.send_message(MessageTypes.POP_QUESTION, {
                "question_id": player.game.popped_question_uuid,
                "question_text": player.game.popped_question_text,
            })
        return player

    async def handle_message(self, msg_type, msg_data):
        if not msg_type:
            return
        elif msg_type == MessageTypes.PING:
            delta = time.time() - msg_data["start_time"]
            self.ping = delta
        elif msg_type == MessageTypes.PLAYER_BUZZED:
            question_id = msg_data["question_id"]
            if question_id != self.game.popped_question_uuid:
                return
            if self in self.game.buzzes:
                return
            log.info(f"Player '{self.name}' ({self.id}) buzzed in game {self.game.key}.")
            self.game.buzzes.append(self)
            # Pass it on to everything.
            for client in itertools.chain(self.game.admins, self.game.displays, self.game.players):
                await client.send_message(MessageTypes.PLAYER_BUZZED, msg_data)
        else:
            log.warning(f"Player sent unhandled message type '{msg_type}': {msg_data}")


async def create_client(websocket):
    async for msg in websocket:
        msg_type, msg_data = parse_message(msg)
        if not msg_type:
            continue
        if not "game_key" in msg_data:
            log.error(f"Message has no game key: {msg_data}")
            continue
        game_key = msg_data.pop("game_key")
        if msg_type == MessageTypes.ADMIN_CONNECTED:
            return await Admin.new(websocket, game_key)
        elif msg_type == MessageTypes.DISPLAY_CONNECTED:
            return await Display.new(websocket, game_key)
        elif msg_type == MessageTypes.PLAYER_CONNECTED:
            player_id = msg_data["player_id"]
            player_name = msg_data["player_name"]
            return await Player.new(websocket, game_key, player_id, player_name)
        else:
            log.warning(f"Received message of type {msg_type} before detecting client type: {msg_data}")


async def handle_websocket(websocket, path):
    host = websocket.remote_address[0]
    log.info(f"New connection from {host}.")
    try:
        client = await create_client(websocket)
        await client.handler()
    except websockets.ConnectionClosed:
        log.info(f"Lost connection from {host}.")
    else:
        await websocket.close()


def start_middleware():
    log.info("Middleware started.")
    if settings.ENABLE_SSL:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile=settings.SSL_CERT_PATH, keyfile=settings.SSL_KEY_PATH)
    else:
        ssl_context = None
    server = websockets.serve(handle_websocket, HOST_URL, HOST_PORT, ssl=ssl_context)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(server)
    loop.run_forever()


if __name__ == "__main__":
    start_middleware()
