# Generated by Django 2.0.6 on 2018-07-25 16:57

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import re


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0018_auto_20180725_1305'),
    ]

    operations = [
        migrations.CreateModel(
            name='RepositoryEntityLabel',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('value', models.CharField(blank=True, max_length=64, validators=[django.core.validators.RegexValidator(re.compile('^[-a-z0-9_]+\\Z'), 'Enter a valid value consisting of lowercase letters, numbers, underscores or hyphens.', 'invalid')], verbose_name='label')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='created at')),
                ('repository', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='common.Repository')),
            ],
        ),
        migrations.AddField(
            model_name='repositoryentity',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now, verbose_name='created at'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='repositoryentity',
            name='label',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='entities', to='common.RepositoryEntityLabel'),
        ),
        migrations.AlterUniqueTogether(
            name='repositoryentitylabel',
            unique_together={('repository', 'value')},
        ),
    ]
