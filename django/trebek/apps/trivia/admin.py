# -*- coding: utf-8 -*-
"""Admin models and registration for trivia app."""
# Part of Trebek (https://github.com/whutch/trebek)
# :copyright: (c) 2018 Will Hutcheson
# :license: MIT (https://github.com/whutch/trebek/blob/master/LICENSE.txt)

from django.contrib import admin

from . import models


admin.site.register(models.UserData)
admin.site.register(models.QuestionCategory)
admin.site.register(models.Question)
admin.site.register(models.Game)
admin.site.register(models.GameRound)
admin.site.register(models.CategoryState)
admin.site.register(models.QuestionState)
admin.site.register(models.Player)
