# Generated by Django 2.1.3 on 2018-12-07 12:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0026_auto_20181010_1704'),
    ]

    operations = [
        migrations.AddField(
            model_name='repositorycategory',
            name='icon',
            field=models.CharField(default='botinho', max_length=16, verbose_name='icon'),
        ),
    ]
