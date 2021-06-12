# -*- coding: utf-8 -*-
"""Data models for trivia app."""
# Part of Trebek (https://github.com/whutch/trebek)
# :copyright: (c) 2018 Will Hutcheson
# :license: MIT (https://github.com/whutch/trebek/blob/master/LICENSE.txt)

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


class UserData(models.Model):

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    class Meta:
        ordering = ("user",)

    def __str__(self):
        return str(self.user)


class QuestionCategory(models.Model):

    title = models.CharField(max_length=100)

    class Meta:
        ordering = ("title",)
        verbose_name_plural = "question categories"

    def __str__(self):
        return str(self.title)


class Question(models.Model):

    category = models.ForeignKey(QuestionCategory, on_delete=models.CASCADE, related_name="questions")
    text = models.CharField(max_length=200)
    answer = models.CharField(max_length=200)
    point_value = models.PositiveSmallIntegerField(default=200)

    class Meta:
        ordering = ("category", "point_value", "text")

    def __str__(self):
        return "{} ({}): {}".format(self.category, self.point_value, self.text)


class Game(models.Model):

    name = models.CharField(max_length=100)
    date = models.DateField()
    key = models.CharField(max_length=4, unique=True)
    current_round = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("date", "name")

    def __str__(self):
        return str(self.name)

    def reset(self):
        for question_state in QuestionState.objects.filter(game_round__game=self):
            if question_state.answered:
                question_state.answered = False
                question_state.save()
        for player in Player.objects.filter(game=self):
            if player.score != 0:
                player.score = 0
                player.save()
        self.current_round = 0
        self.save()


class GameRound(models.Model):

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="rounds")
    categories = models.ManyToManyField(
        QuestionCategory, blank=True, related_name="game_rounds", through="CategoryState")
    questions = models.ManyToManyField(
        Question, blank=True, related_name="games", through="QuestionState")
    round = models.PositiveSmallIntegerField(default=1)
    is_final = models.BooleanField(default=False)

    class Meta:
        ordering = ("game", "round")
        unique_together = ("game", "round")

    def __str__(self):
        return "{}: Round {}{}".format(self.game, self.round, " (Final)" if self.is_final else "")


class CategoryState(models.Model):

    game_round = models.ForeignKey(GameRound, on_delete=models.CASCADE)
    category = models.ForeignKey(QuestionCategory, on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ("game_round", "order", "category")
        unique_together = ("game_round", "category")

    def __str__(self):
        return "{}: {} ({})".format(self.game_round, self.category, self.order)

    def validate_unique(self, exclude=None):
        rounds = self.game_round.game.rounds.exclude(round=self.game_round.round)
        for round in rounds:
            for category in round.categories.all():
                if category == self.category:
                    raise ValidationError("Category state with this Category already exists in Game.")
        return super().validate_unique(exclude=exclude)


class QuestionState(models.Model):

    game_round = models.ForeignKey(GameRound, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    answered = models.BooleanField(default=False)

    class Meta:
        ordering = ("game_round", "question")
        unique_together = ("game_round", "question")

    def __str__(self):
        return "{}: {}".format(self.game_round, self.question)


class Player(models.Model):

    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    name = models.CharField(max_length=20)
    score = models.SmallIntegerField(default=0)

    class Meta:
        ordering = ("game", "name")
        unique_together = ("game", "name")

    def __str__(self):
        return str(self.name)
