from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from app.models.models import User
import os

def create_calendar_event(user: User, task_title: str, task_description: str | None, deadline_iso: str) -> str | None:
    """creates event in google calendar and returns event_id"""
    if not user.google_access_token or not user.google_refresh_token:
        return None

    creds = Credentials(
        token=user.google_access_token,
        refresh_token=user.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    )

    service = build('calendar', 'v3', credentials=creds)

    clean_iso = deadline_iso.replace('Z', '+00:00')
    start_time = datetime.fromisoformat(clean_iso)
    end_time = start_time + timedelta(minutes=30)

    event = {
        'summary': f'📌 {task_title}',
        'description': task_description or 'Создано через TMA Task Manager',
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'Europe/Moscow',
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'Europe/Moscow',
        },
    }

    created_event = service.events().insert(calendarId='primary', body=event).execute()
    
    return created_event.get('id')


def update_calendar_event(event_id: str, user: User, task_title: str, task_description: str | None, deadline_iso: str | None):
    """update existing event in google calendar"""
    if not user.google_access_token or not user.google_refresh_token or not event_id:
        return

    creds = Credentials(
        token=user.google_access_token,
        refresh_token=user.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    )

    service = build('calendar', 'v3', credentials=creds)

    event = service.events().get(calendarId='primary', eventId=event_id).execute()

    event['summary'] = f'📌 {task_title}'
    event['description'] = task_description or 'Создано через TMA Task Manager'

    if deadline_iso:
        clean_iso = deadline_iso.replace('Z', '+00:00')
        start_time = datetime.fromisoformat(clean_iso)
        end_time = start_time + timedelta(minutes=30)
        event['start']['dateTime'] = start_time.isoformat()
        event['end']['dateTime'] = end_time.isoformat()

    service.events().update(calendarId='primary', eventId=event_id, body=event).execute()