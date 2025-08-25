from icalendar import Calendar, Event
from datetime import datetime, timedelta
import pytz


def generate_ics(user, habits):
    cal = Calendar
    cal.add("prodid", "-//MoodLinker//Habit Reminders/EN")
    cal.add("version", "2.0")

    tz = pytz.timezone(user.timezone)

    for habit in habits:
        event = Event()
        event.add("summary", f"Reminder: {habit.habit}")
        event.add("dtstart", tz.localize(
            datetime.now() + timedelta(minutes=5)))
        event.add("dtend", tz.localize(datetime.now() + timedelta(minutes=35)))
        event.add("description",
                  f"Don't forget to complete your habit: {habit.habit}")
        cal.add_component(event)

    return cal.to_ical
