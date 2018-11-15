# -*- coding: utf-8 -*-
"""WebSocket middleware for sending messages to clients."""
# Part of Trebek (https://github.com/whutch/trebek)
# :copyright: (c) 2018 Will Hutcheson
# :license: MIT (https://github.com/whutch/trebek/blob/master/LICENSE.txt)

import asyncio
import itertools
import json
import logging
import os
from os.path import abspath, dirname, join
import ssl
import sys
import uuid

import django
import websockets

BASE_DIR = abspath(join(dirname(__file__), ".."))
DJANGO_DIR = join(BASE_DIR, "django")
sys.path.insert(0, DJANGO_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "trebek.settings")
django.setup()
from trebek.apps.trivia import models


HOST_URL = "0.0.0.0"
HOST_PORT = 8765
ENABLE_SSL = False
SSL_CERT_PATH = ""
SSL_KEY_PATH = ""


class MessageTypes:
    ERROR = 0
    ADMIN_CONNECTED = 1
    DISPLAY_CONNECTED = 2
    PLAYER_CONNECTED = 3
    GAME_START = 4
    GAME_RESET = 5
    POP_QUESTION = 6
    CLEAR_QUESTION = 7
    PLAYER_BUZZED = 8
    CLEAR_BUZZ = 9
    UPDATE_SCORE = 10
    PLAY_SOUND = 11


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("middleware")

GAMES = {}


def mark_question_answered(game_key, question_id):
    try:
        question = models.Question.objects.get(id=question_id)
    except models.Question.DoesNotExist:
        log.warning(f"Tried to clear non-existent question: {question_id}")
        return
    try:
        game = models.Game.objects.get(key=game_key)
    except models.Game.DoesNotExist:
        log.warning(f"Game key does not exist in database: {game_key}")
        return
    try:
        state = question.questionstate_set.get(game=game)
    except models.QuestionState.DoesNotExist:
        state = models.QuestionState(question=question, game=game)
        state.answered = True
        state.save()


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
        self.started = False
        self.popped_question_uuid = None
        self.popped_question_real_id = None
        GAMES[game_key] = self

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
        # If the game has started, let the admin know.
        if admin.game.started:
            await admin.send_message(MessageTypes.GAME_START)
        return admin

    async def handle_message(self, msg_type, msg_data):
        if not msg_type:
            return
        elif msg_type == MessageTypes.GAME_START:
            if self.game.started:
                return
            log.info(f"Starting game {self.game.key}.")
            self.game.started = True
            # Pass it on to everything.
            for client in itertools.chain(self.game.admins, self.game.displays, self.game.players):
                if client is self:
                    continue
                await client.send_message(MessageTypes.GAME_START)
        elif msg_type == MessageTypes.GAME_RESET:
            self.game.started = False
            log.info(f"Reseting game {self.game.key}.")
            # Pass it on to everything.
            for client in itertools.chain(self.game.admins, self.game.displays, self.game.players):
                if client is self:
                    continue
                await client.send_message(MessageTypes.GAME_RESET)
        elif msg_type == MessageTypes.POP_QUESTION:
            # Pass it on to the displays.
            for display in self.game.displays:
                await display.send_message(MessageTypes.POP_QUESTION, msg_data)
            # Inject a question UUID before passing it on to the players.
            self.game.popped_question_real_id = msg_data["question_id"]
            question_uuid = str(uuid.uuid4())
            self.game.popped_question_uuid = question_uuid
            msg_data["question_id"] = question_uuid
            for player in self.game.players:
                await player.send_message(MessageTypes.POP_QUESTION, msg_data)
        elif msg_type == MessageTypes.CLEAR_QUESTION:
            # Mark the question as answered.
            if msg_data.get("answered"):
                question_id = msg_data["question_id"]
                mark_question_answered(self.game.key, question_id)
            # Pass it on to the displays.
            for display in self.game.displays:
                await display.send_message(MessageTypes.CLEAR_QUESTION, msg_data)
            # Strip out the question_id before passing it on to the player.
            del msg_data["question_id"]
            for player in self.game.players:
                await player.send_message(MessageTypes.CLEAR_QUESTION, msg_data)
        elif msg_type == MessageTypes.CLEAR_BUZZ:
            # Pass it on to everything.
            for client in itertools.chain(self.game.admins, self.game.displays, self.game.players):
                if client is self:
                    continue
                await client.send_message(MessageTypes.CLEAR_BUZZ)
        elif msg_type == MessageTypes.UPDATE_SCORE:
            player_id = msg_data["player_id"]
            score = msg_data["score"]
            player = models.Player.objects.get(id=player_id)
            log.info(f"Received score update for player '{player.name}' ({player.id}) of game {self.game.key}, new value is {score}.")
            player.score = score
            player.save()
        elif msg_type == MessageTypes.PLAY_SOUND:
            # Pass it on to the displays and players.
            for client in itertools.chain(self.game.displays, self.game.players):
                await client.send_message(MessageTypes.PLAY_SOUND, msg_data)
        else:
            log.warning(f"Admin sent unhandled message type '{msg_type}': {msg_data}")


class Display(Client):

    @classmethod
    async def new(cls, *args, **kwargs):
        display = cls(*args, **kwargs)
        # If the game has started, let the display know.
        if display.game.started:
            await display.send_message(MessageTypes.GAME_START)
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
        super().__init__(websocket, game_key)

    @classmethod
    async def new(cls, *args, **kwargs):
        player = cls(*args, **kwargs)
        # If there's an admin in our game already, let the player know.
        if player.game.admins:
            await player.send_message(MessageTypes.ADMIN_CONNECTED)
        # Pass the player data on to the admins.
        score = models.Player.objects.get(id=player.id).score
        for admin in player.game.admins:
            await admin.send_message(MessageTypes.PLAYER_CONNECTED, {
                "player_id": player.id,
                "player_name": player.name,
                "score": score,
            })
        # If the game has started, let the player know.
        if player.game.started:
            await player.send_message(MessageTypes.GAME_START)
        return player

    async def handle_message(self, msg_type, msg_data):
        if not msg_type:
            return
        elif msg_type == MessageTypes.PLAYER_BUZZED:
            question_id = msg_data["question_id"]
            if question_id != self.game.popped_question_uuid:
                # Only the first player to buzz a given UUID will get passed on.
                return
            log.info(f"Player '{self.name}' ({self.id}) buzzed in game {self.game.key}.")
            self.game.popped_question_real_id = None
            self.game.popped_question_uuid = None
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
    log.info("New connection.")
    try:
        client = await create_client(websocket)
        await client.handler()
    except websockets.ConnectionClosed:
        log.info("Lost connection.")
    else:
        await websocket.close()


def start_middleware():
    log.info("Middleware started.")
    if ENABLE_SSL:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(SSL_CERT_PATH, SSL_KEY_PATH)
    else:
        ssl_context = None
    server = websockets.serve(handle_websocket, HOST_URL, HOST_PORT, ssl=ssl_context)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(server)
    loop.run_forever()


if __name__ == "__main__":
    start_middleware()
