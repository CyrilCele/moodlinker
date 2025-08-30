def generate_ics(user):
    """
    Generate ICS calendar for all active habit reminders of a user.
    """
    from icalendar import Calendar, Event
    from datetime import timedelta
    import pytz

    cal = Calendar()
    cal.add("prodid", "-//MoodLinker//Habit Reminders/EN")
    cal.add("version", "2.0")

    tz = pytz.timezone(user.timezone)

    # Get all active reminders
    reminders = user.reminders.filter(active=True).select_related("habit")

    for reminder in reminders:
        event = Event()

        event.add("summary", f"Reminder: {reminder.habit.habit}")
        event.add("dtstart", reminder.next_trigger_utc.astimezone(tz))
        # Default duration: 30 mins
        event.add("dtend", (reminder.next_trigger_utc +
                  timedelta(minutes=30)).astimezone(tz))
        event.add(
            "description", f"Don't forget to complete your habit: {reminder.habit.habit}"
        )

        cal.add_component(event)

    return cal.to_ical()
