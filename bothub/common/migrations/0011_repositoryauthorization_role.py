# Generated by Django 2.0.6 on 2018-06-21 12:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0010_auto_20180611_1123'),
    ]

    operations = [
        migrations.AddField(
            model_name='repositoryauthorization',
            name='role',
            field=models.PositiveIntegerField(choices=[(0, 'not set'), (1, 'user'), (2, 'contributor'), (3, 'admin')], default=0, verbose_name='role'),
        ),
    ]
