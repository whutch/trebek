# Generated by Django 2.0.2 on 2018-03-11 00:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trivia', '0004_auto_20180310_1613'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='question',
            options={'ordering': ('category', 'point_value', 'text')},
        ),
        migrations.AlterModelOptions(
            name='questionstate',
            options={'ordering': ('game', 'question')},
        ),
        migrations.AlterField(
            model_name='question',
            name='point_value',
            field=models.PositiveSmallIntegerField(default=200),
        ),
        migrations.AlterUniqueTogether(
            name='questionstate',
            unique_together={('game', 'question')},
        ),
    ]