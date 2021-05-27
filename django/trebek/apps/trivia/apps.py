# -*- coding: utf-8 -*-
"""App configuration for trivia app."""
# Part of Trebek (https://github.com/whutch/trebek)
# :copyright: (c) 2018 Will Hutcheson
# :license: MIT (https://github.com/whutch/trebek/blob/master/LICENSE.txt)

from django.apps import AppConfig


class TriviaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "trebek.apps.trivia"
