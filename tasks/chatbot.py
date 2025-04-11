# import google.generativeai as genai
# from django.contrib.auth.decorators import login_required
# from django.http import JsonResponse
# from .models import Task, Habit
# from .forms import TaskForm, HabitForm

# class ChatbotHandler:
#     def __init__(self):
#         from django.conf import settings
#         self.gemini_api_key = settings.GEMINI_API_KEY if hasattr(settings, 'GEMINI_API_KEY') else None
#         self.system_prompt = """
#         You are an AI assistant for a task management system. Your job is to help users create, update, and manage tasks and habits.
#         When a user requests to create or modify a task/habit, you must:
#         1. Identify required fields (title, description, date/time etc.)
#         2. Check if all required fields are provided
#         3. If missing fields, politely ask for them
#         4. Validate the input format
#         5. Confirm the action with user before executing
#         """
        
#         # Configure Gemini API if key is available
#         if self.gemini_api_key:
#             genai.configure(api_key=self.gemini_api_key)

#     def process_message(self, user_message, user):
#         if not self.gemini_api_key:
#             return {'error': 'Gemini API key is not configured. Please set GEMINI_API_KEY in your settings.'}
        
#         try:
#             # Use Gemini's model for generating responses
#             model = genai.GenerativeModel('gemini-1.5-flash')
            
#             # Prepare the prompt with system instructions and user message
#             prompt = f"{self.system_prompt}\n\nUser: {user_message}"
            
#             # Generate response using Gemini
#             response = model.generate_content(prompt)
            
#             # Extract the text from the response
#             ai_response = response.text
#             return self._handle_action(ai_response, user)
#         except Exception as e:
#             import traceback
#             print(f"Gemini API Error: {str(e)}")
#             print(traceback.format_exc())
#             return {'error': f'Error communicating with Gemini: {str(e)}'}
        

#     def _handle_action(self, ai_response, user):
#         # For now, just return the AI response as a message
#         # In the future, this could be expanded to parse the response and perform actions
#         return {'message': ai_response}

# @login_required
# def chatbot_view(request):
#     if request.method == 'POST':
#         user_message = request.POST.get('message')
#         handler = ChatbotHandler()
#         response = handler.process_message(user_message, request.user)
#         return JsonResponse(response)
#     return JsonResponse({'error': 'Invalid request method'})




import google.generativeai as genai
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.cache import cache
from .models import Task, Habit
from django.conf import settings
from datetime import datetime, timedelta
import logging
import json

logger = logging.getLogger(__name__)

class ChatbotHandler:
    def __init__(self):
        self.gemini_api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not self.gemini_api_key:
            logger.error("Gemini API key not configured")
            raise ValueError("Gemini API key not configured in settings")
        
        genai.configure(api_key=self.gemini_api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        
        self.system_prompt = """You are an AI assistant for a task management system. Help users:
        - Create tasks (title, description, duration, deadline, priority)
        - Create habits (title, description, frequency, duration, start_date, preferred_time)
       - List today's tasks and habits
        - Answer general questions
        Be concise and structured in your responses."""
        
        self.task_fields = {
            "title": {"question": "What's the task title?", "required": True},
            "description": {"question": "Description (optional):", "required": False, "default": ""},
            "duration": {"question": "Duration in minutes:", "required": True},
            "deadline": {"question": "Deadline (e.g., April 10 2025 14:30):", "required": True},
            "priority": {"question": "Priority? (1=High, 2=Medium, 3=Low):", "required": False, "default": 2}
        }
        
        self.habit_fields = {
            "title": {"question": "What's the habit title?", "required": True},
            "description": {"question": "Description (optional):", "required": False, "default": ""},
            "frequency": {"question": "Frequency? (daily/weekly/monthly):", "required": True},
            "duration": {"question": "Duration in minutes:", "required": True},
            "start_date": {"question": "Start date (e.g., April 10 2025):", "required": True},
            "preferred_time": {"question": "Preferred time (e.g., 09:00):", "required": True}
        }

    def _get_user_state(self, user_id):
        try:
            return cache.get(f"chatbot_state_{user_id}", {})
        except Exception as e:
            logger.error(f"Cache error: {e}")
            return {}

    def _update_user_state(self, user_id, state):
        try:
            cache.set(f"chatbot_state_{user_id}", state, timeout=300)
        except Exception as e:
            logger.error(f"Cache update error: {e}")

    def _clear_user_state(self, user_id):
        try:
            cache.delete(f"chatbot_state_{user_id}")
        except Exception as e:
            logger.error(f"Cache delete error: {e}")

    def _parse_datetime(self, datetime_str):
        try:
            return datetime.strptime(datetime_str, "%B %d %Y %H:%M")
        except ValueError:
            try:
                return datetime.strptime(datetime_str, "%B %d %Y")
            except ValueError:
                try:
                    return datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
                except ValueError:
                    try:
                        return datetime.strptime(datetime_str, "%Y-%m-%d")
                    except ValueError:
                        return None

    def _parse_time(self, time_str):
        try:
            return datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            return None

    def _create_task(self, data, user):
        try:
            # Convert and validate fields
            deadline = self._parse_datetime(data['deadline'])
            if not deadline:
                raise ValueError("Invalid deadline format")
            
            try:
                duration = int(data['duration'])
            except (ValueError, KeyError):
                raise ValueError("Duration must be a number")
            
            priority = int(data.get('priority', 2))
            if priority not in [1, 2, 3]:
                priority = 2
            
            # First schedule the task time
            scheduled_time = deadline - timedelta(minutes=duration)
            
            task = Task.objects.create(
                user=user,
                title=data['title'],
                description=data.get('description', ''),
                duration=duration,
                deadline=deadline,
                priority=priority,
                scheduled_time=scheduled_time
            )
            
            # Add to Google Calendar if user has connected their account
            if hasattr(user, 'socialaccount_set') and user.socialaccount_set.filter(provider='google').exists():
                try:
                    from .utils import get_calendar_service, schedule_task_in_calendar
                    service = get_calendar_service(user)
                    # First save the task to get an ID
                    task.save()
                    # Then schedule in calendar and update the task
                    event_id = schedule_task_in_calendar(service, task)
                    task.google_event_id = event_id
                    task.save()
                except Exception as e:
                    logger.error(f"Could not add task to Google Calendar: {str(e)}")
                    # Save the task even if calendar integration fails
                    task.save()
            
            return task
        except Exception as e:
            logger.error(f"Task creation failed: {e}")
            raise ValueError(f"Couldn't create task: {str(e)}")

    def _create_habit(self, data, user):
        try:
            # Convert and validate fields
            start_date = self._parse_datetime(data['start_date'])
            if not start_date:
                raise ValueError("Invalid start date format")
            
            preferred_time = self._parse_time(data['preferred_time'])
            if not preferred_time:
                raise ValueError("Invalid time format (use HH:MM)")
            
            try:
                duration = int(data['duration'])
            except (ValueError, KeyError):
                raise ValueError("Duration must be a number")
            
            frequency = data['frequency'].lower()
            if frequency not in ['daily', 'weekly', 'monthly']:
                frequency = 'daily'
            
            return Habit.objects.create(
                user=user,
                title=data['title'],
                description=data.get('description', ''),
                frequency=frequency,
                duration=duration,
                start_date=start_date,
                preferred_time=preferred_time
            )
        except Exception as e:
            logger.error(f"Habit creation failed: {e}")
            raise ValueError(f"Couldn't create habit: {str(e)}")

    def _get_todays_tasks(self, user):
        from django.utils import timezone
        today = timezone.now().date()
        tomorrow = today + timedelta(days=1)
        
        tasks = Task.objects.filter(
            user=user,
            deadline__gte=today,
            deadline__lt=tomorrow,
            completed=False
        ).order_by('deadline')
        
        if not tasks:
            return "You have no tasks scheduled for today."
        
        task_list = "\nToday's tasks:\n"
        for task in tasks:
            task_list += f"- {task.title} (Due: {task.deadline.strftime('%I:%M %p')})\n"
        
        return task_list
        
    def process_message(self, user_message, user):
        try:
            user_state = self._get_user_state(user.id)
            user_message = user_message.strip()
            
            # Handle confirmation
            if user_state.get('awaiting_confirmation'):
                if 'yes' in user_message.lower():
                    if user_state['current_type'] == 'task':
                        task = self._create_task(user_state['collected_data'], user)
                        self._clear_user_state(user.id)
                        return {'message': f"Task created: {task.title}"}
                    else:
                        habit = self._create_habit(user_state['collected_data'], user)
                        self._clear_user_state(user.id)
                        return {'message': f"Habit created: {habit.title}"}
                else:
                    self._clear_user_state(user.id)
                    return {'message': "Creation cancelled."}
            
            # Start new task/habit
            if not user_state:
                if 'create task' in user_message.lower():
                    user_state = {
                        'current_type': 'task',
                        'collected_data': {},
                        'current_field': 'title',
                        'awaiting_confirmation': False
                    }
                    self._update_user_state(user.id, user_state)
                    return {'message': self.task_fields['title']['question']}
                
                elif 'create habit' in user_message.lower():
                    user_state = {
                        'current_type': 'habit',
                        'collected_data': {},
                        'current_field': 'title',
                        'awaiting_confirmation': False
                    }
                    self._update_user_state(user.id, user_state)
                    return {'message': self.habit_fields['title']['question']}
                
                # Handle task listing
                elif 'today\'s tasks' in user_message.lower() or 'today\'s task' in user_message.lower():
                    tasks_info = self._get_todays_tasks(user)
                    return {'message': tasks_info}
                
                # General question
                else:
                    prompt = f"{self.system_prompt}\nUser: {user_message}"
                    response = self.model.generate_content(prompt)
                    return {'message': response.text}
            
            # Mid-creation flow
            else:
                current_type = user_state['current_type']
                current_field = user_state['current_field']
                fields = self.task_fields if current_type == 'task' else self.habit_fields
                
                # Store response
                user_state['collected_data'][current_field] = user_message
                
                # Get next field
                remaining_fields = [
                    f for f in fields.keys() 
                    if f not in user_state['collected_data'] and 
                    (fields[f]['required'] or user_message.lower() != 'skip')
                ]
                
                if remaining_fields:
                    next_field = remaining_fields[0]
                    user_state['current_field'] = next_field
                    self._update_user_state(user.id, user_state)
                    return {'message': fields[next_field]['question']}
                
                # All fields collected - confirm
                else:
                    user_state['awaiting_confirmation'] = True
                    self._update_user_state(user.id, user_state)
                    
                    summary = "\n".join(
                        f"{k}: {v}" for k, v in user_state['collected_data'].items()
                    )
                    return {
                        'message': f"Please confirm:\n{summary}\n\nReply 'yes' to confirm or 'no' to cancel."
                    }
        
        except Exception as e:
            logger.error(f"Processing error: {e}", exc_info=True)
            self._clear_user_state(user.id)
            return {'error': str(e)}

@login_required
def chatbot_view(request):
    if request.method == 'POST':
        try:
            # Get and validate input
            user_message = request.POST.get('message', '').strip()
            if not user_message:
                return JsonResponse({'error': 'Message cannot be empty'}, status=400)
            
            # Process message
            handler = ChatbotHandler()
            response = handler.process_message(user_message, request.user)
            return JsonResponse(response)
            
        except Exception as e:
            logger.error(f"View error: {e}", exc_info=True)
            return JsonResponse(
                {'error': 'Internal server error'}, 
                status=500
            )
    
    return JsonResponse(
        {'error': 'Only POST requests are supported'}, 
        status=405
    )