from django import template
from typing import Any, Iterable, Optional

register = template.Library()


@register.filter("get_item")
def get_item(queryset: Iterable[Any], habit_id: Any) -> Optional[Any]:
    """
    Template filter: return the first object from `queryset` whose related id matches `habit_id`.

    Description:
        Used in Django templates to find a single object (commonly a HabitCompletion or similar)
        from a collection by matching `habit__id` against `habit_id`. When given a Django QuerySet,
        this uses a DB-level `.filter(...).first()` for efficiency. When given a plain iterable
        (list, queryset already evaluated, etc.) it falls back to Python iteration.

    Parameters:
        queryset (Iterable[Any]):
            A Django QuerySet or any iterable of model instances or dict-like items.
            Expected items usually have a `.habit` attribute (FK) or a dict key "habit".
        habit_id (Any):
            The habit primary key to match (int, str, UUID, etc.). Strings and ints are
            compared flexibly (stringified comparison) to reduce template crashes.

    Returns:
        Optional[Any]:
            - The first matching item from `queryset` (model instance or dict).
            - `None` if no matching item is found or if `quetryset` is falsy.

    Exceptions:
        - The function is defensive by design and aims *not* to raise inside templates.
          However, if `queryset` is not iterable, Python will raise `TypeError`.
        - If an unexpected error occurs during filter/iteration, the function will skip the
          problematic item and continue. Only fatal errors (non-iterable `queryset`) will bubble.

    Example (template usage):
        {% load custom_filters %}
        {% for habit in habits %}
            {% with completion = compltetions|get_item:habit.id %}
                {% if completion %}
                    Completed: {{ completion.completed }}
                {% else %}
                    Not completed
                {% endif %}
            {% endwith %}
        {% endfor %}

    Notes / edge cases:
        - Prefer passing a Django QuerySet: it will perform DB filtering (fast, lazy).
        - If habit_id is None, the filter returns None.
        - If items are dict-like, filter attempts to inspect keys like "habit" or nested {"habit": {"id": ...}}.
        - Designed to fail gracefully inside templates rather than raise.
    """
    # Defensive: None or empty input -> nothing to do
    if not queryset:
        return None

    # If this is a Django QuerySet (or any object providing .filter), DB-level lookup:
    try:
        filter_fn = getattr(queryset, "filter", None)
        if callable(filter_fn):
            # Try to coerce numeric-looking habit_id to int to match DB PK types when appropriate.
            try:
                coerced = int(habit_id)
            except Exception:
                coerced = habit_id
            # Use a DB filter for performance; .first() returns None if no match
            return queryset.filter(habit__id=coerced).first()
    except Exception:
        # If anything goes wrong with .filter (rare), fall back to iterating the iterable.
        # We intentionally swallow exceptions here to avoid crashing templates.
        pass

    # Fallback: iterate through the iterable (list, evaluated queryset, etc.)
    for item in queryset:
        # Try attribute access first (typical for model instances)
        try:
            habit_obj = getattr(item, "habit", None)
            if habit_obj is not None:
                # habit object may be an FK object or directly an id
                item_habit_id = getattr(
                    habit_obj,
                    "id",
                    getattr(
                        habit_obj,
                        "pk",
                        habit_obj
                    )
                )
                # Compare robustly by stringifying both sides
                if str(item_habit_id) == str(habit_id):
                    return item
        except Exception:
            # If attribute access fails, try dict-like access below
            pass

        # Try dict-like patterns (e.g., item is {"habit": 3} or {"habit": {"id": 3}})
        try:
            if isinstance(item, dict):
                habit_val = item.get("habit")
                if isinstance(habit_val, (int, str)):
                    if str(habit_val) == str(habit_id):
                        return item
                elif isinstance(habit_val, dict):
                    hid = habit_val.get("id") or habit_val.get("pk")
                    if hid and str(hid) == str(habit_id):
                        return item
        except Exception:
            # If this item can't be inspected, skip it (don't crush the template).
            continue

    # No match found
    return None
