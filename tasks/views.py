from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Task, Habit, HabitCompletion
from .forms import TaskForm, HabitForm
import json
import openai
from django.conf import settings

@login_required
def chatbot_view(request):
    if request.method == 'POST':
        try:
            # Handle both JSON and form data
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                user_message = data.get('message', '').strip()
            else:
                user_message = request.POST.get('message', '').strip()
            
            if not user_message:
                return JsonResponse({'error': 'Message cannot be empty'}, status=400)
            
            # Use the ChatbotHandler from chatbot.py
            from .chatbot import ChatbotHandler
            handler = ChatbotHandler()
            response = handler.process_message(user_message, request.user)
            return JsonResponse(response)
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return render(request, 'tasks/chatbot.html')

@login_required
def home(request):
    # Get upcoming tasks (next 7 days)
    today = timezone.now()
    week_later = today + timedelta(days=7)
    upcoming_tasks = Task.objects.filter(
        user=request.user,
        deadline__gte=today,
        deadline__lte=week_later,
        completed=False
    ).order_by('deadline')
    
    # Get today's habits
    today_date = timezone.now().date()
    habits = Habit.objects.filter(user=request.user)
    today_habits = []
    
    for habit in habits:
        # Check if habit is scheduled for today based on frequency
        if habit.frequency == 'daily':
            today_habits.append(habit)
        elif habit.frequency == 'weekly' and habit.start_date.weekday() == today_date.weekday():
            today_habits.append(habit)
        elif habit.frequency == 'monthly' and habit.start_date.day == today_date.day:
            today_habits.append(habit)
    
    # Check which habits are completed today
    for habit in today_habits:
        completion, created = HabitCompletion.objects.get_or_create(
            habit=habit,
            completed_date=today_date,
            defaults={'completed': False}
        )
        habit.is_completed_today = completion.completed
    
    context = {
        'upcoming_tasks': upcoming_tasks,
        'today_habits': today_habits,
        'now': timezone.now(),
    }
    return render(request, 'tasks/home.html', context)

@login_required
def task_list(request):
    tasks = Task.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'tasks/task_list.html', {'tasks': tasks})



@login_required
def task_create(request):
    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.user = request.user
            
            # Schedule the task based on availability
            from .utils import schedule_task
            scheduled_time = schedule_task(request.user, task.duration, task.deadline, task.priority)
            task.scheduled_time = scheduled_time
            task.save()
            
            # Add to Google Calendar if user has connected their account
            if hasattr(request.user, 'socialaccount_set') and request.user.socialaccount_set.filter(provider='google').exists():
                try:
                    from .utils import get_calendar_service, schedule_task_in_calendar
                    service = get_calendar_service(request.user)
                    event_id = schedule_task_in_calendar(service, task)
                    task.google_event_id = event_id
                    task.save()
                except Exception as e:
                    messages.warning(request, f"Could not add task to Google Calendar: {str(e)}")
            
            messages.success(request, 'Task created successfully!')
            return redirect('tasks:task_list')
    else:
        form = TaskForm()
    
    return render(request, 'tasks/task_form.html', {'form': form, 'title': 'Create Task'})

@login_required
def task_detail(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    return render(request, 'tasks/task_detail.html', {'task': task})

@login_required
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    
    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            task = form.save(commit=False)
            
            # Reschedule the task if needed
            if form.has_changed() and any(field in form.changed_data for field in ['duration', 'deadline', 'priority']):
                from .utils import schedule_task
                scheduled_time = schedule_task(request.user, task.duration, task.deadline, task.priority)
                task.scheduled_time = scheduled_time
            
            task.save()
            
            # Update Google Calendar event if it exists
            if task.google_event_id and hasattr(request.user, 'socialaccount_set') and request.user.socialaccount_set.filter(provider='google').exists():
                try:
                    from .utils import get_calendar_service, schedule_task_in_calendar
                    service = get_calendar_service(request.user)
                    schedule_task_in_calendar(service, task, update=True)
                except Exception as e:
                    messages.warning(request, f"Could not update Google Calendar: {str(e)}")
            
            messages.success(request, 'Task updated successfully!')
            return redirect('tasks:task_detail', pk=task.pk)
    else:
        form = TaskForm(instance=task)
    
    return render(request, 'tasks/task_form.html', {'form': form, 'task': task, 'title': 'Edit Task'})

@login_required
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    
    if request.method == 'POST':
        # Delete from Google Calendar if it exists
        if task.google_event_id and hasattr(request.user, 'socialaccount_set') and request.user.socialaccount_set.filter(provider='google').exists():
            try:
                from .utils import get_calendar_service
                service = get_calendar_service(request.user)
                service.events().delete(calendarId='primary', eventId=task.google_event_id).execute()
            except Exception as e:
                messages.warning(request, f"Could not delete from Google Calendar: {str(e)}")
        
        task.delete()
        messages.success(request, 'Task deleted successfully!')
        return redirect('tasks:task_list')
    
    return render(request, 'tasks/task_confirm_delete.html', {'task': task})

@login_required
def task_complete(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    
    if request.method == 'POST':
        task.completed = not task.completed  # Toggle completion status
        task.save()
        
        # Update Google Calendar event if it exists
        if task.google_event_id and hasattr(request.user, 'socialaccount_set') and request.user.socialaccount_set.filter(provider='google').exists():
            try:
                from .utils import get_calendar_service
                service = get_calendar_service(request.user)
                event = service.events().get(calendarId='primary', eventId=task.google_event_id).execute()
                
                if task.completed:
                    event['colorId'] = '9'  # Green color for completed tasks
                else:
                    event['colorId'] = '4'  # Red color for incomplete tasks
                
                service.events().update(calendarId='primary', eventId=task.google_event_id, body=event).execute()
            except Exception as e:
                messages.warning(request, f"Could not update Google Calendar: {str(e)}")
        
        status = 'completed' if task.completed else 'marked as incomplete'
        messages.success(request, f'Task {status} successfully!')
        
        # Redirect back to the referring page
        return redirect(request.META.get('HTTP_REFERER', 'tasks:task_list'))
    
    return redirect('tasks:task_detail', pk=task.pk)

@login_required
def habit_list(request):
    habits = Habit.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'tasks/habit_list.html', {'habits': habits})

@login_required
def habit_create(request):
    if request.method == 'POST':
        form = HabitForm(request.POST)
        if form.is_valid():
            habit = form.save(commit=False)
            habit.user = request.user
            habit.save()
            
            # Add to Google Calendar if user has connected their account
            if hasattr(request.user, 'socialaccount_set') and request.user.socialaccount_set.filter(provider='google').exists():
                try:
                    from .utils import get_calendar_service, schedule_habit_in_calendar
                    service = get_calendar_service(request.user)
                    event_id = schedule_habit_in_calendar(service, habit)
                    habit.google_event_id = event_id
                    habit.save()
                except Exception as e:
                    messages.warning(request, f"Could not add habit to Google Calendar: {str(e)}")
            
            messages.success(request, 'Habit created successfully!')
            return redirect('tasks:habit_list')
    else:
        form = HabitForm()
    
    return render(request, 'tasks/habit_form.html', {'form': form, 'title': 'Create Habit'})

@login_required
def habit_detail(request, pk):
    habit = get_object_or_404(Habit, pk=pk, user=request.user)
    
    # Get completion history for the last 30 days
    today = timezone.now().date()
    thirty_days_ago = today - timedelta(days=30)
    
    completions = HabitCompletion.objects.filter(
        habit=habit,
        completed_date__gte=thirty_days_ago,
        completed_date__lte=today
    ).order_by('completed_date')
    
    # Create a dictionary of dates and completion status
    completion_history = {}
    current_date = thirty_days_ago
    
    while current_date <= today:
        completion_history[current_date] = False
        current_date += timedelta(days=1)
    
    for completion in completions:
        completion_history[completion.completed_date] = completion.completed
    
    context = {
        'habit': habit,
        'completion_history': completion_history,
    }
    
    return render(request, 'tasks/habit_detail.html', context)

@login_required
def habit_edit(request, pk):
    habit = get_object_or_404(Habit, pk=pk, user=request.user)
    
    if request.method == 'POST':
        form = HabitForm(request.POST, instance=habit)
        if form.is_valid():
            habit = form.save()
            
            # Update Google Calendar event if it exists
            if habit.google_event_id and hasattr(request.user, 'socialaccount_set') and request.user.socialaccount_set.filter(provider='google').exists():
                try:
                    from .utils import get_calendar_service, schedule_habit_in_calendar
                    service = get_calendar_service(request.user)
                    schedule_habit_in_calendar(service, habit, update=True)
                except Exception as e:
                    messages.warning(request, f"Could not update Google Calendar: {str(e)}")
            
            messages.success(request, 'Habit updated successfully!')
            return redirect('tasks:habit_detail', pk=habit.pk)
    else:
        form = HabitForm(instance=habit)
    
    return render(request, 'tasks/habit_form.html', {'form': form, 'habit': habit, 'title': 'Edit Habit'})

@login_required
def habit_delete(request, pk):
    habit = get_object_or_404(Habit, pk=pk, user=request.user)
    
    if request.method == 'POST':
        # Delete from Google Calendar if it exists
        if habit.google_event_id and hasattr(request.user, 'socialaccount_set') and request.user.socialaccount_set.filter(provider='google').exists():
            try:
                from .utils import get_calendar_service
                service = get_calendar_service(request.user)
                service.events().delete(calendarId='primary', eventId=habit.google_event_id).execute()
            except Exception as e:
                messages.warning(request, f"Could not delete from Google Calendar: {str(e)}")
        
        habit.delete()
        messages.success(request, 'Habit deleted successfully!')
        return redirect('tasks:habit_list')
    
    return render(request, 'tasks/habit_confirm_delete.html', {'habit': habit})

@login_required
def habit_complete(request, pk, date):
    habit = get_object_or_404(Habit, pk=pk, user=request.user)
    completion_date = datetime.strptime(date, '%Y-%m-%d').date()
    
    # Check if the completion date is in the future
    today = timezone.now().date()
    if completion_date > today:
        messages.error(request, 'Cannot mark habits as complete for future dates!')
        return redirect(request.META.get('HTTP_REFERER', 'tasks:habit_detail'))
    
    # Get or create the completion record
    completion, created = HabitCompletion.objects.get_or_create(
        habit=habit,
        completed_date=completion_date,
        defaults={'completed': True}
    )
    
    # Toggle completion status
    if not created:
        completion.completed = not completion.completed
        completion.save()
    
    status = 'completed' if completion.completed else 'marked as incomplete'
    messages.success(request, f'Habit {status} for {date}!')
    
    # Redirect back to the referring page
    return redirect(request.META.get('HTTP_REFERER', 'tasks:habit_detail'))

@login_required
def calendar_view(request):
    return render(request, 'tasks/calendar.html')

@login_required
def calendar_data(request):
    """API endpoint to get calendar data for a specific month."""
    from django.http import JsonResponse
    
    # Get year and month from request parameters
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))
    
    # Create date range for the month
    start_date = timezone.datetime(year, month, 1, tzinfo=timezone.get_current_timezone())
    if month == 12:
        end_date = timezone.datetime(year + 1, 1, 1, tzinfo=timezone.get_current_timezone())
    else:
        end_date = timezone.datetime(year, month + 1, 1, tzinfo=timezone.get_current_timezone())
    
    # Get tasks for the month
    tasks = Task.objects.filter(
        user=request.user,
        scheduled_time__gte=start_date,
        scheduled_time__lt=end_date
    )
    
    # Get habits for the month
    habits = Habit.objects.filter(user=request.user)
    
    # Prepare events data
    events = []
    
    # Add tasks to events
    for task in tasks:
        # Format the date in YYYY-MM-DD format for consistency
        task_date = task.scheduled_time.date().isoformat()
        events.append({
            'id': task.id,
            'title': task.title,
            'date': task.scheduled_time.isoformat(),
            'date_ymd': task_date,  # Add a consistent YYYY-MM-DD format date
            'time': task.scheduled_time.strftime('%H:%M'),
            'type': 'task',
            'priority': task.priority,
            'completed': task.completed,
            'description': task.description,
            'duration': task.duration,
            'deadline': task.deadline.isoformat() if task.deadline else None
        })
    
    # Add habits to events
    for habit in habits:
        # Generate habit occurrences based on frequency
        current_date = start_date.date()
        end_date_day = end_date.date()
        
        while current_date < end_date_day:
            add_habit = False
            
            if habit.frequency == 'daily':
                add_habit = True
            elif habit.frequency == 'weekly' and habit.start_date.weekday() == current_date.weekday():
                add_habit = True
            elif habit.frequency == 'monthly' and habit.start_date.day == current_date.day:
                add_habit = True
            
            if add_habit:
                # Check if habit is completed for this date
                completion = HabitCompletion.objects.filter(
                    habit=habit,
                    completed_date=current_date
                ).first()
                
                # Create datetime combining current date with preferred time
                habit_datetime = timezone.datetime.combine(
                    current_date,
                    habit.preferred_time,
                    tzinfo=timezone.get_current_timezone()
                )
                
                events.append({
                    'id': habit.id,
                    'title': habit.title,
                    'date': habit_datetime.isoformat(),
                    'time': habit.preferred_time.strftime('%H:%M'),
                    'type': 'habit',
                    'completed': completion.completed if completion else False,
                    'description': habit.description,
                    'duration': habit.duration,
                    'frequency': habit.get_frequency_display()
                })
            
            current_date += timedelta(days=1)
    
    return JsonResponse({'events': events})


@login_required
def update_task_schedule(request):
    """API endpoint to update a task's scheduled time via drag and drop."""
    from django.http import JsonResponse
    import json
    from datetime import datetime
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            task_id = data.get('task_id')
            new_date = data.get('new_date')
            new_time = data.get('new_time', '00:00')
            
            print(f"Updating task {task_id} to date {new_date} and time {new_time}")
            
            # Get the task
            task = get_object_or_404(Task, id=task_id, user=request.user)
            
            # Parse the new date and time
            try:
                date_obj = datetime.strptime(new_date, '%Y-%m-%d').date()
                time_obj = datetime.strptime(new_time, '%H:%M').time()
                
                # Combine date and time into a datetime object
                new_scheduled_time = timezone.make_aware(
                    datetime.combine(date_obj, time_obj)
                )
                
                # Calculate the time difference between old and new scheduled times
                time_difference = new_scheduled_time - task.scheduled_time
                
                # Update the task's scheduled time
                task.scheduled_time = new_scheduled_time
                
                # Update the deadline by the same time difference
                if task.deadline:
                    task.deadline = task.deadline + time_difference
                
                task.save()
                
                # Update Google Calendar if connected
                if task.google_event_id and hasattr(request.user, 'socialaccount_set') and request.user.socialaccount_set.filter(provider='google').exists():
                    try:
                        from .utils import get_calendar_service, schedule_task_in_calendar
                        service = get_calendar_service(request.user)
                        schedule_task_in_calendar(service, task, update=True)
                    except Exception as e:
                        # Log the error but don't fail the request
                        print(f"Could not update Google Calendar: {str(e)}")
                
                return JsonResponse({'status': 'success'})
            except ValueError as e:
                error_msg = f"Invalid date or time format: {str(e)}"
                print(error_msg)
                return JsonResponse({'status': 'error', 'message': error_msg}, status=400)
        except Exception as e:
            print(f"Error updating task schedule: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
    return JsonResponse({'status': 'error', 'message': 'Only POST requests are allowed'}, status=405)
