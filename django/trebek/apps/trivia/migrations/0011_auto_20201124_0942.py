# Generated by Django 3.1.3 on 2020-11-24 15:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trivia', '0010_game_started'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='game',
            name='started',
        ),
        migrations.AddField(
            model_name='game',
            name='current_round',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='game',
            name='final_round',
            field=models.PositiveSmallIntegerField(default=3),
        ),
        migrations.AddField(
            model_name='question',
            name='round',
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
