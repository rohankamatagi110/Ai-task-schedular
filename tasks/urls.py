from django.urls import path
from . import views


app_name = 'tasks'

urlpatterns = [

    path('', views.home, name='home'),
    
    # Task URLs
    path('tasks/', views.task_list, name='task_list'),
    path('tasks/create/', views.task_create, name='task_create'),
    path('tasks/<int:pk>/', views.task_detail, name='task_detail'),
    path('tasks/<int:pk>/edit/', views.task_edit, name='task_edit'),
    path('tasks/<int:pk>/delete/', views.task_delete, name='task_delete'),
    path('tasks/<int:pk>/complete/', views.task_complete, name='task_complete'),
    
    # Habit URLs
    path('habits/', views.habit_list, name='habit_list'),
    path('habits/create/', views.habit_create, name='habit_create'),
    path('habits/<int:pk>/', views.habit_detail, name='habit_detail'),
    path('habits/<int:pk>/edit/', views.habit_edit, name='habit_edit'),
    path('habits/<int:pk>/delete/', views.habit_delete, name='habit_delete'),
    path('habits/<int:pk>/complete/<str:date>/', views.habit_complete, name='habit_complete'),
    
    # Calendar URLs
    path('calendar/', views.calendar_view, name='calendar'),
    path('api/calendar-data/', views.calendar_data, name='calendar_data'),
    path('api/update-task-schedule/', views.update_task_schedule, name='update_task_schedule'),
    path('chatbot/', views.chatbot_view, name='chatbot'),
    

]