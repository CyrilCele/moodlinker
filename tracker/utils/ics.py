def generate_ics(user):
    """
    Generate an iCalendar (ICS) file containing events for a user's active habit reminders.

    This function builds a mininmal, standards-compatible ICS (RFC 5545) binary payload
    representing one VEVENT per active `HabitReminder` related to the provided `user`.
    Each event uses `reminder.next_trigger_utc` as the start (converted to the user's
    local timezone) and allocates a default 30-minute duration.

    Args:
        user (django.contrib.auth.models.User):
            A Django User-like instance that:
                - has a string attribute `timezone` (IANA name, e.g. "Africa/Johannesburg"),
                - exposes a related manager `reminders` returning HabitReminder rows with:
                    * `habit` (FK to Habit, with `.habit` as the habit text),
                    * `next_trigger_utc` (a datetime representing the UTC instant to trigger).

    Returns:
        bytes:
            The ICS document serialized to bytes (the ruturn value of `Calendar.to_ical()`).
            This is ready to be returned from a Django view as `HttpResponse(ics, content_type="text/calendar")`.

    Raises:
        ImportError:
            If the `icalender` package is not installed.
        pytz.UnknownTimeZoneError:
            If `User.timezone` is not a recognized timezone name (unless handled by the fallback).
        AttributeError:
            If the `user` object does not provide required attributes/relations (e.g., `.timezone` or `.reminders`).
        Exception:
            Other exceptions from model access or datetime operations may bubble up.
    
    Example:
        >>> ics_bytes = generate_ics(request.user)
        >>> response = HttpResponse(ics_bytes, content_type="text/calendar")
        >>> repsonse["Content-Disposition"] = "attachment; filename=habits.ics"
        >>> return response

    Important notes / edge cases:
        - The function expects `reminder.next_trigger_utc` to be a timezone-aware UTC datetime.
          If a reminder contains a naive datetime, the function will assume UTC (to avoid crashes),
          but it's better to ensure `next_trigger_utc` is timezone-aware at write time.
        - The calendar uses the user's timezone when setting DTSTART/DTEND so the event appears at the
          correct local time in calendar clients. However, some clients (Outlook) prefer an embedded
          VTIMEZONE component for full interoperability; this function does not currently emit VTIMEZONE.
        - Very large numbers of reminders will create a large ICS; consider pagination or streaming.
    """
    from icalendar import Calendar, Event
    from datetime import timedelta
    import pytz

    # Create the calendar wrapper
    cal = Calendar()
    cal.add("prodid", "-//MoodLinker//Habit Reminders/EN")
    cal.add("version", "2.0")

    # Resolve user's timezone safely; fall back to UTC if resolution fails
    try:
        tz = pytz.timezone(user.timezone)
    except Exception:
        # If the user's timezone string is invalid, default to UTC rather than raising.
        # This keeps calendar generation resilient; callers may choose to log this condition.
        tz = pytz.UTC

    # Query the user's active reminders; select_related('habit') avoids an extra query per reminder
    reminders = user.reminders.filter(active=True).select_related("habit")

    for reminder in reminders:
        event = Event()

        # Human-readable summary
        event.add("summary", f"Reminder: {reminder.habit.habit}")

        # Ensure `next_trigger_utc` is timezone-aware; if naive, assume UTC (defensive fallback)
        dt_utc = reminder.next_trigger_utc
        if dt_utc.tzinfo is None:
            # localize naive datetime as UTC (this is a safe fallback but indicates a data quality issue)
            dt_utc = pytz.UTC.localize(dt_utc)
        
        # Convert the UTC instant to the user's local timezone for DTSTART and DTEND
        local_start = dt_utc.astimezone(tz)
        # Default duration: 30 minutes
        local_end = (dt_utc + timedelta(minutes=30)).astimezone(tz)

        # Add start and end time to the VEVENT
        event.add("dtstart", local_start)
        event.add("dtend", local_end)

        # Short description to help users identify the habit
        event.add(
            "description", f"Don't forget to complete your habit: {reminder.habit.habit}"
        )

        # Attach the event to the calendar
        cal.add_component(event)

    # Serialize to bytes for HTTP response
    return cal.to_ical()
