# Generated by Django 2.1.3 on 2020-11-24 23:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trivia', '0011_auto_20201124_0942'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='question',
            name='round',
        ),
        migrations.AddField(
            model_name='questioncategory',
            name='round',
            field=models.PositiveSmallIntegerField(default=1),
        ),
    ]