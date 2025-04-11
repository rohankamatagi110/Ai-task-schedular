from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from allauth.socialaccount.models import SocialToken, SocialApp
from django.utils import timezone
from datetime import datetime, timedelta

def get_calendar_service(user):
    """Get a Google Calendar API service instance for the given user."""
    social_token = SocialToken.objects.get(account__user=user, account__provider='google')
    social_app = SocialApp.objects.get(provider='google')
    
    credentials = Credentials(
        token=social_token.token,
        refresh_token=social_token.token_secret,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=social_app.client_id,
        client_secret=social_app.secret
    )
    
    return build('calendar', 'v3', credentials=credentials)

def get_calendar_events(service, time_min=None, time_max=None):
    """Fetch events from Google Calendar within the specified time range."""
    if time_min is None:
        time_min = timezone.now()
    if time_max is None:
        time_max = time_min + timedelta(days=7)
    
    # Convert to RFC3339 timestamp format
    time_min_str = time_min.isoformat()
    time_max_str = time_max.isoformat()
    
    events_result = service.events().list(
        calendarId='primary',
        timeMin=time_min_str,
        timeMax=time_max_str,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    return events_result.get('items', [])

def find_available_slot(service, duration_minutes, deadline, priority, existing_events=None):
    """Find an available time slot for a task before the deadline using AI scheduling."""
    # If no existing events provided, fetch them
    if existing_events is None:
        # Fetch events from now until the deadline
        existing_events = get_calendar_events(
            service, 
            time_min=timezone.now(),
            time_max=deadline
        )
    
    # Convert duration to timedelta
    duration = timedelta(minutes=duration_minutes)
    
    # Start from current time
    current_time = timezone.now()
    
    # Define working hours (9 AM to 6 PM)
    working_start_hour = 9
    working_end_hour = 18
    
    # Create a list of busy periods
    busy_periods = []
    for event in existing_events:
        if 'dateTime' in event['start'] and 'dateTime' in event['end']:
            start = datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(event['end']['dateTime'].replace('Z', '+00:00'))
            busy_periods.append((start, end))
    
    # Sort busy periods by start time
    busy_periods.sort(key=lambda x: x[0])
    
    # Calculate time until deadline
    time_until_deadline = deadline - current_time
    days_until_deadline = time_until_deadline.days + (time_until_deadline.seconds / 86400)
    
    # Determine scheduling strategy based on priority and deadline
    if priority == 1:  # High priority
        # For high priority tasks, schedule as soon as possible
        scheduling_strategy = "asap"
    elif priority == 2:  # Medium priority
        if days_until_deadline < 2:  # If deadline is close, schedule soon
            scheduling_strategy = "asap"
        else:  # Otherwise, distribute evenly
            scheduling_strategy = "distributed"
    else:  # Low priority
        if days_until_deadline < 1:  # If deadline is very close, schedule soon
            scheduling_strategy = "asap"
        else:  # Otherwise, schedule closer to deadline
            scheduling_strategy = "deadline"
    
    # Find available slots based on strategy
    if scheduling_strategy == "asap":
        # Find the earliest available slot
        return find_earliest_slot(current_time, duration, deadline, busy_periods, working_start_hour, working_end_hour)
    elif scheduling_strategy == "deadline":
        # Find a slot closer to the deadline
        return find_deadline_slot(current_time, duration, deadline, busy_periods, working_start_hour, working_end_hour)
    else:  # distributed
        # Find a slot distributed between now and deadline
        return find_distributed_slot(current_time, duration, deadline, busy_periods, working_start_hour, working_end_hour)

def find_earliest_slot(current_time, duration, deadline, busy_periods, working_start_hour, working_end_hour):
    """Find the earliest available time slot."""
    while current_time + duration <= deadline:
        # Move to the next day if we're past working hours
        if current_time.hour >= working_end_hour:
            current_time = current_time.replace(
                hour=working_start_hour, 
                minute=0, 
                second=0, 
                microsecond=0
            ) + timedelta(days=1)
            continue
        
        # If before working hours, move to working start time
        if current_time.hour < working_start_hour:
            current_time = current_time.replace(
                hour=working_start_hour, 
                minute=0, 
                second=0, 
                microsecond=0
            )
        
        # Check if current_time falls on a weekend (5=Saturday, 6=Sunday)
        if current_time.weekday() >= 5:  # Weekend
            current_time = current_time.replace(
                hour=working_start_hour, 
                minute=0, 
                second=0, 
                microsecond=0
            ) + timedelta(days=1)
            # Skip to Monday if it's Saturday
            if current_time.weekday() == 5:
                current_time += timedelta(days=2)
            # Skip to Monday if it's Sunday
            elif current_time.weekday() == 6:
                current_time += timedelta(days=1)
            continue
        
        # Potential end time
        potential_end_time = current_time + duration
        
        # Check if this slot conflicts with any busy period
        conflict = False
        for busy_start, busy_end in busy_periods:
            # Check for overlap
            if (current_time < busy_end and potential_end_time > busy_start):
                conflict = True
                # Move current_time to the end of this busy period
                current_time = busy_end
                break
        
        # If no conflict, we found an available slot
        if not conflict:
            return current_time
        
    # If we couldn't find a slot before the deadline, return the deadline minus duration
    return deadline - duration

def find_deadline_slot(current_time, duration, deadline, busy_periods, working_start_hour, working_end_hour):
    """Find a time slot closer to the deadline."""
    # Start from deadline and work backwards
    current_time = deadline - duration
    
    while current_time >= timezone.now():
        # Check if current_time is within working hours
        if current_time.hour < working_start_hour or current_time.hour >= working_end_hour:
            # Move to the previous day's end of working hours
            current_time = current_time.replace(
                hour=working_end_hour - 1, 
                minute=0, 
                second=0, 
                microsecond=0
            )
            if current_time + duration > deadline:
                current_time = current_time - timedelta(days=1)
            continue
        
        # Check if current_time falls on a weekend (5=Saturday, 6=Sunday)
        if current_time.weekday() >= 5:  # Weekend
            # Move to Friday
            days_to_subtract = 1 if current_time.weekday() == 6 else 2
            current_time = current_time - timedelta(days=days_to_subtract)
            current_time = current_time.replace(
                hour=working_end_hour - 1, 
                minute=0, 
                second=0, 
                microsecond=0
            )
            continue
        
        # Potential end time
        potential_end_time = current_time + duration
        
        # Check if this slot conflicts with any busy period
        conflict = False
        for busy_start, busy_end in busy_periods:
            # Check for overlap
            if current_time < busy_end and potential_end_time > busy_start:
                conflict = True
                # Move current_time before the start of this busy period
                current_time = busy_start - duration
                break
        
        # If no conflict, we found an available slot
        if not conflict and potential_end_time <= deadline:
            return current_time
        
        # Move back by 30 minutes if there was a conflict
        if conflict:
            continue
        else:
            current_time = current_time - timedelta(minutes=30)
    
    # If we couldn't find a slot, fall back to earliest slot method
    return find_earliest_slot(timezone.now(), duration, deadline, busy_periods, working_start_hour, working_end_hour)

def find_distributed_slot(current_time, duration, deadline, busy_periods, working_start_hour, working_end_hour):
    """Find a time slot distributed between now and the deadline."""
    # Calculate a target time approximately halfway between now and the deadline
    time_until_deadline = deadline - current_time
    target_time = current_time + (time_until_deadline / 2)
    
    # Try to find a slot near the target time
    # First try after the target time
    search_time = target_time
    while search_time + duration <= deadline:
        # Ensure we're within working hours
        if search_time.hour < working_start_hour:
            search_time = search_time.replace(
                hour=working_start_hour, 
                minute=0, 
                second=0, 
                microsecond=0
            )
        elif search_time.hour >= working_end_hour:
            search_time = search_time.replace(
                hour=working_start_hour, 
                minute=0, 
                second=0, 
                microsecond=0
            ) + timedelta(days=1)
            continue
        
        # Check if search_time falls on a weekend
        if search_time.weekday() >= 5:  # Weekend
            days_to_add = 8 - search_time.weekday()  # Move to next Monday
            search_time = search_time.replace(
                hour=working_start_hour, 
                minute=0, 
                second=0, 
                microsecond=0
            ) + timedelta(days=days_to_add)
            continue
        
        # Potential end time
        potential_end_time = search_time + duration
        
        # Check if this slot conflicts with any busy period
        conflict = False
        for busy_start, busy_end in busy_periods:
            # Check for overlap
            if search_time < busy_end and potential_end_time > busy_start:
                conflict = True
                # Move search_time to the end of this busy period
                search_time = busy_end
                break
        
        # If no conflict, we found an available slot
        if not conflict:
            return search_time
        
        # If we had a conflict, the loop will continue with the updated search_time
    
    # If we couldn't find a slot after the target time, try before it
    search_time = target_time - duration
    while search_time >= current_time:
        # Ensure we're within working hours
        if search_time.hour < working_start_hour or search_time.hour >= working_end_hour:
            # Move to the previous day's end of working hours
            search_time = search_time.replace(
                hour=working_end_hour - 1, 
                minute=0, 
                second=0, 
                microsecond=0
            ) - timedelta(days=1)
            continue
        
        # Check if search_time falls on a weekend
        if search_time.weekday() >= 5:  # Weekend
            days_to_subtract = 1 if search_time.weekday() == 6 else 2  # Move to previous Friday
            search_time = search_time - timedelta(days=days_to_subtract)
            search_time = search_time.replace(
                hour=working_end_hour - 1, 
                minute=0, 
                second=0, 
                microsecond=0
            )
            continue
        
        # Potential end time
        potential_end_time = search_time + duration
        
        # Check if this slot conflicts with any busy period
        conflict = False
        for busy_start, busy_end in busy_periods:
            # Check for overlap
            if search_time < busy_end and potential_end_time > busy_start:
                conflict = True
                # Move search_time before the start of this busy period
                search_time = busy_start - duration
                break
        
        # If no conflict, we found an available slot
        if not conflict:
            return search_time
        
        # Move back by 30 minutes if there was a conflict
        if conflict:
            continue
        else:
            search_time = search_time - timedelta(minutes=30)
    
    # If we couldn't find a slot, fall back to earliest slot method
    return find_earliest_slot(current_time, duration, deadline, busy_periods, working_start_hour, working_end_hour)


def schedule_task(user, duration_minutes, deadline, priority):
    """Schedule a task based on availability and priority."""
    try:
        service = get_calendar_service(user)
        
        # Fetch existing events
        existing_events = get_calendar_events(
            service, 
            time_min=timezone.now(),
            time_max=deadline
        )
        
        # Find available slot
        scheduled_time = find_available_slot(
            service, 
            duration_minutes, 
            deadline, 
            priority,
            existing_events
        )
        
        return scheduled_time
    except Exception as e:
        # If there's an error (e.g., no Google account connected), 
        # just return a default time (deadline minus duration)
        return deadline - timedelta(minutes=duration_minutes)

def schedule_task_in_calendar(service, task, update=False):
    """Schedule a task in Google Calendar."""
    event = {
        'summary': task.title,
        'description': task.description,
        'start': {
            'dateTime': task.scheduled_time.isoformat(),
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': (task.scheduled_time + timedelta(minutes=task.duration)).isoformat(),
            'timeZone': 'UTC',
        },
        'colorId': '4',  # Red color for tasks
    }
    
    if task.completed:
        event['colorId'] = '9'  # Green color for completed tasks
    
    if update and task.google_event_id:
        # Update existing event
        event = service.events().update(
            calendarId='primary',
            eventId=task.google_event_id,
            body=event
        ).execute()
        return task.google_event_id
    else:
        # Create new event
        event = service.events().insert(
            calendarId='primary',
            body=event
        ).execute()
        return event['id']

def schedule_habit_in_calendar(service, habit, update=False):
    """Add or update a recurring habit in Google Calendar."""
    # Set recurrence rule based on frequency
    if habit.frequency == 'daily':
        recurrence = ['RRULE:FREQ=DAILY']
    elif habit.frequency == 'weekly':
        # Get the day of week (e.g., MO, TU, etc.)
        days = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']
        day_of_week = days[habit.start_date.weekday()]
        recurrence = [f'RRULE:FREQ=WEEKLY;BYDAY={day_of_week}']
    elif habit.frequency == 'monthly':
        # Get the day of month
        day_of_month = habit.start_date.day
        recurrence = [f'RRULE:FREQ=MONTHLY;BYMONTHDAY={day_of_month}']
    
    # Combine date and time
    start_datetime = datetime.combine(
        habit.start_date.date(),
        habit.preferred_time
    )
    end_datetime = start_datetime + timedelta(minutes=habit.duration)
    
    event = {
        'summary': f"[Habit] {habit.title}",
        'description': habit.description,
        'start': {
            'dateTime': start_datetime.isoformat(),
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': end_datetime.isoformat(),
            'timeZone': 'UTC',
        },
        'recurrence': recurrence,
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 30},
                {'method': 'popup', 'minutes': 15},
            ],
        },
        'colorId': '2',  # Green color for habits
    }
    
    if update and habit.google_event_id:
        # Update existing event
        event = service.events().update(
            calendarId='primary',
            eventId=habit.google_event_id,
            body=event
        ).execute()
        return habit.google_event_id
    else:
        # Create new event
        event = service.events().insert(
            calendarId='primary',
            body=event
        ).execute()
        return event['id']