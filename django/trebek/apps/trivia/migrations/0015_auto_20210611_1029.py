# Generated by Django 3.2.4 on 2021-06-11 15:29

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('trivia', '0014_auto_20210611_1029'),
    ]

    operations = [
        migrations.CreateModel(
            name='QuestionState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('answered', models.BooleanField(default=False)),
                ('game_round', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='trivia.gameround')),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='trivia.question')),
            ],
            options={
                'ordering': ('game_round', 'question'),
                'unique_together': {('game_round', 'question')},
            },
        ),
        migrations.CreateModel(
            name='CategoryState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveSmallIntegerField(default=1)),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='trivia.questioncategory')),
                ('game_round', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='trivia.gameround')),
            ],
            options={
                'ordering': ('game_round', 'order'),
            },
        ),
        migrations.AddField(
            model_name='gameround',
            name='categories',
            field=models.ManyToManyField(blank=True, related_name='game_rounds', through='trivia.CategoryState', to='trivia.QuestionCategory'),
        ),
        migrations.AddField(
            model_name='gameround',
            name='questions',
            field=models.ManyToManyField(blank=True, related_name='games', through='trivia.QuestionState', to='trivia.Question'),
        ),
    ]
