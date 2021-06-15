# -*- coding: utf-8 -*-
"""View functions for trivia app."""
# Part of Trebek (https://github.com/whutch/trebek)
# :copyright: (c) 2018 Will Hutcheson
# :license: MIT (https://github.com/whutch/trebek/blob/master/LICENSE.txt)

import asyncio
import json
import re
import ssl

from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
import websockets

from .models import Game, Player


if settings.ENABLE_SSL:
    WS_URI = "wss://{}:8765"
else:
    WS_URI = "ws://{}:8765"


def msg(msg_type, msg_data):
    """Send a message to the middleware server."""
    async def send():
        uri = WS_URI.format("localhost")
        ssl_context = True if settings.ENABLE_SSL else None
        async with websockets.connect(uri, ssl=ssl_context) as ws:
            msg_data["type"] = msg_type
            await ws.send(json.dumps(msg_data))
        asyncio.get_event_loop().run_until_complete(send())


def one_up_player_name(game, name):
    players = Player.objects.filter(game=game, name__startswith=name)
    pattern = re.compile(r"{}( \(\d+\))?$".format(name))
    names = [player.name for player in players if pattern.match(player.name)]
    if not names:
        return name
    elif len(names) == 1:
        return f"{name} (2)"
    else:
        match = re.match(r"{} \((\d+)\)".format(name), names[-1])
        if not match:
            raise ValueError("could not find count in last player name")
        count = int(match.groups()[0])
        count += 1
        return f"{name} ({count})"


def trivia_home(request):
    template = "trivia/trivia_home.html"
    if request.method == "GET":
        return render(request, template)
    error = None
    player_name = request.POST.get("player_name")
    if not player_name or player_name.strip() == "":
        error = "Please enter a player name."
    try:
        key = request.POST["game_key"].upper()
        game = Game.objects.get(key=key)
    except (KeyError, Game.DoesNotExist):
        error = "Game not found."
    else:
        try:
            player = Player.objects.get(game=game, name=player_name)
        except (KeyError, Player.DoesNotExist):
            player = None
        else:
            if player and request.session.get("player_id") != player.id:
                player = None
                player_name = one_up_player_name(game, player_name)
    if error:
        return render(request, template, {
            "error_message": error,
        })
    if not player:
        player = Player.objects.create(game=game, name=player_name)
    msg("register_player", {
        "game": game.key,
        "id": player.id,
        "name": player_name,
    })
    request.session["player_id"] = player.id
    return HttpResponseRedirect(reverse("buzzer", args=(game.key,)))


def game_home(request, game_key):
    game = get_object_or_404(Game, key=game_key)
    context = {
        "game": game
    }
    return render(request, "trivia/game_home.html", context)


def admin(request, game_key):
    game = get_object_or_404(Game, key=game_key)
    context = {
        "game": game,
        "players": Player.objects.filter(game=game),
        "ws_uri": WS_URI.format(request.META["HTTP_HOST"].split(":")[0]),
    }
    if game.current_round == 0:
        return render(request, "trivia/admin_landing.html", context)
    game_round = game.rounds.get(round=game.current_round)
    categories = []
    for category_state in game_round.categorystate_set.all():
        questions = []
        for question_state in game_round.questionstate_set.filter(question__category=category_state.category):
            question = question_state.question
            question_data = {
                "id": question.id,
                "text": question.text,
                "answer": question.answer,
                "point_value": question_state.get_modified_point_value(),
                "answered": question_state.answered,
                "requires_wager": question_state.requires_wager,
            }
            questions.append(question_data)
        categories.append([category_state.category, questions])
    context["categories"] = categories
    return render(request, "trivia/admin_round.html", context)


def display(request, game_key):
    game = get_object_or_404(Game, key=game_key)
    context = {
        "game": game,
        "players": Player.objects.filter(game=game),
        "ws_uri": WS_URI.format(request.META["HTTP_HOST"].split(":")[0]),
    }
    if game.current_round == 0:
        context["host_url"] = request.META["HTTP_HOST"]
        return render(request, "trivia/display_landing.html", context)
    game_round = game.rounds.get(round=game.current_round)
    categories = []
    for category_state in game_round.categorystate_set.all():
        questions = []
        for question_state in game_round.questionstate_set.filter(question__category=category_state.category):
            question = question_state.question
            question_data = {
                "id": question.id,
                "point_value": question_state.get_modified_point_value(),
                "answered": question_state.answered,
            }
            questions.append(question_data)
        categories.append([category_state.category, questions])
    context["categories"] = categories
    return render(request, "trivia/display_round.html", context)


def buzzer(request, game_key):
    player_id = request.session.get("player_id")
    if not player_id:
        return redirect("trivia_home")
    try:
        player = Player.objects.get(id=player_id)
    except (KeyError, Player.DoesNotExist):
        return redirect("trivia_home")
    game = get_object_or_404(Game, key=game_key)
    context = {
        "game": game,
        "player": player,
        "ws_uri": WS_URI.format(request.META["HTTP_HOST"].split(":")[0]),
        "max_wager": max(player.score, game.current_round * 1000),
    }
    if game.current_round == 0:
        return render(request, "trivia/buzzer_landing.html", context)
    return render(request, "trivia/buzzer_round.html", context)
