# Generated by Django 3.2.4 on 2021-06-13 22:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trivia', '0018_auto_20210612_1700'),
    ]

    operations = [
        migrations.AddField(
            model_name='questionstate',
            name='requires_bid',
            field=models.BooleanField(default=False),
        ),
    ]