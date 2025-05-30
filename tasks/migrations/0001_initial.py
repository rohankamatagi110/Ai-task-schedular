# Generated by Django 5.1.7 on 2025-03-16 19:50

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Habit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('frequency', models.CharField(choices=[('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly')], max_length=50)),
                ('duration', models.IntegerField(help_text='Duration in minutes')),
                ('start_date', models.DateTimeField()),
                ('preferred_time', models.TimeField(help_text='Preferred time of day for this habit')),
                ('google_event_id', models.CharField(blank=True, max_length=255, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='habits', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Task',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('duration', models.IntegerField(help_text='Duration in minutes')),
                ('deadline', models.DateTimeField()),
                ('priority', models.IntegerField(choices=[(1, 'High'), (2, 'Medium'), (3, 'Low')], default=2)),
                ('scheduled_time', models.DateTimeField(blank=True, null=True)),
                ('completed', models.BooleanField(default=False)),
                ('google_event_id', models.CharField(blank=True, max_length=255, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tasks', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='HabitCompletion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('completed_date', models.DateField()),
                ('completed', models.BooleanField(default=True)),
                ('habit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='completions', to='tasks.habit')),
            ],
            options={
                'unique_together': {('habit', 'completed_date')},
            },
        ),
    ]
