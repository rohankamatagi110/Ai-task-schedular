from django.db import models
from django.contrib.auth.models import User

class Task(models.Model):
    PRIORITY_CHOICES = [
        (1, 'High'),
        (2, 'Medium'),
        (3, 'Low'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    duration = models.IntegerField(help_text='Duration in minutes')  # Duration in minutes
    deadline = models.DateTimeField()
    priority = models.IntegerField(choices=PRIORITY_CHOICES, default=2)  # 1 = High, 2 = Medium, 3 = Low
    scheduled_time = models.DateTimeField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    google_event_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.title

class Habit(models.Model):
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='habits')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    frequency = models.CharField(max_length=50, choices=FREQUENCY_CHOICES)  # e.g., "daily", "weekly"
    duration = models.IntegerField(help_text='Duration in minutes')  # Duration in minutes
    start_date = models.DateTimeField()
    preferred_time = models.TimeField(help_text='Preferred time of day for this habit')
    google_event_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.title

class HabitCompletion(models.Model):
    habit = models.ForeignKey(Habit, on_delete=models.CASCADE, related_name='completions')
    completed_date = models.DateField()
    completed = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ('habit', 'completed_date')
        
    def __str__(self):
        return f"{self.habit.title} - {self.completed_date}"
