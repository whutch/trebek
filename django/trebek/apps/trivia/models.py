# -*- coding: utf-8 -*-
"""Data models for trivia app."""
# Part of Trebek (https://github.com/whutch/trebek)
# :copyright: (c) 2018 Will Hutcheson
# :license: MIT (https://github.com/whutch/trebek/blob/master/LICENSE.txt)

from django.contrib.auth.models import User
from django.db import models


class UserData(models.Model):

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    class Meta:
        ordering = ("user",)

    def __str__(self):
        return str(self.user)


class QuestionCategory(models.Model):

    title = models.CharField(max_length=100)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("order", "title",)

    def __str__(self):
        return str(self.title)


class Question(models.Model):

    category = models.ForeignKey(
        QuestionCategory, on_delete=models.CASCADE, related_name="questions")
    text = models.CharField(max_length=200)
    answer = models.CharField(max_length=200)
    point_value = models.PositiveSmallIntegerField(default=200)

    class Meta:
        ordering = ("category", "point_value", "text")

    def __str__(self):
        return "{} ({}): {}".format(self.category, self.point_value, self.text)


class Game(models.Model):

    categories = models.ManyToManyField(
        QuestionCategory, blank=True, related_name="games")
    questions = models.ManyToManyField(
        Question, blank=True, related_name="games", through="QuestionState")
    name = models.CharField(max_length=100)
    date = models.DateField()
    key = models.CharField(max_length=4, unique=True)
    started = models.BooleanField(default=False)

    class Meta:
        ordering = ("date", "name")

    def __str__(self):
        return str(self.name)


class QuestionState(models.Model):

    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    answered = models.BooleanField(default=False)

    class Meta:
        ordering = ("game", "question")
        unique_together = ("game", "question")

    def __str__(self):
        return "{}: {}".format(self.game, self.question)


class Player(models.Model):

    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    name = models.CharField(max_length=20)
    score = models.SmallIntegerField(default=0)

    class Meta:
        ordering = ("game", "name")
        unique_together = ("game", "name")

    def __str__(self):
        return str(self.name)
