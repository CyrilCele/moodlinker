"""
Template filters for form fields used in templates.

Provides:
- `add_class(field, css_class)` to add CSS classes to a form field when rendering.
- `add_disabled(field, condition)` to mark a field disabled when a condition is truthy.

Important:
- Filters are intended to be used in Django templates with BoundField objects
  (e.g. `{{ form.myfield|add_class:"form-control" }}`).
- Some operations mutate widget attributes (side effects) - see warnings in docstrings.
"""

from django import template
from django.utils.safestring import SafeString
from typing import Any

register = template.Library()


@register.filter(name="add_class")
def add_class(field: Any, css_class: str) -> Any:
    """
    Add a CSS class (or classes) to a form field's rendered widget.

    Description:
        Intended for use in templates to apply additional CSS classes to a BoundField.
        It reads any existing classes defined on the widget, appends the supplied
        `css_class`, and renders the widget with the combined `class` attribute.
        This implementation uses `field.as_widget(attrs=...)` to avoid directly mutating
        the widget attributes on the form object.

    Parameters:
        field (Any): A Django BoundField (typical usage: `form.field`) or any object
            exposing `.field.widget.attrs`. If `field` is already rendered HTML
            (SafeString) this function will still attempt to call `.as_widget`, which
            normally isn't used in this case - prefer passing a BoundField.
        css_class (str): CSS class string to append (e.g. "form-control").
            Multiple classes may be passed as a space-separated string: "a b c".

    Returns:
        Any: The rendered widget (SafeString) returned by `field.as_widget(...)`.
             In template usage this prints the HTML for the form field with the
             additional class applied.

    Raises:
        AttributeError: If `field` does not have the expected attributes (e.g. called
            with a plain string that is not a BoundField). In template contexts this
            usually doesn't occur, but be cautious in custom usage.

    Example (template):
        {{ form.email|add_class:"form-control mb-2" }}

    Notes / edge cases:
        - This function prefers **not** to mutate `field.field.widget.attrs` directly.
          Instead it passes `attrs` to `as_widget()`, which only affects the current
          render call. That reduces (but does not eliminate) risk of side effects.
        - If the widget already has the same class, the class may be duplicated.
          De-duplication is not performed here for speed/simplicity.
    """
    # Read any classes already declared on the widget. Using .get avoids KeyError.
    existing_classes = ""
    try:
        existing_classes = field.field.widget.attrs.get("class", "")
    except Exception:
        # If field is not a BoundField (e.g. None or wrong type), raise a clearer error.
        raise AttributeError(
            "add_class filter expected a BoundField-like object as the first argument."
        )

    # Combine existing and new classes, strip extra whitespace
    combined = f"{existing_classes} {css_class}".strip()

    # Use as_widget(attrs=...) which renders widget with these attrs for this render call.
    # This avoids mutating the underlying widget attrs dict (safer for repeated rendering).
    return field.as_widget(attrs={"class": combined})


@register.filter
def add_disabled(field: Any, condition: Any) -> Any:
    """
    Conditionally mark a form field widget as disabled.

    Description:
        If `condition` evaluates truthy, this filter sets the HTML `disabled` attribute
        on the field's widget so that when the field is rendered it is disabled in the form.
        If `field` is already a SafeString (i.e., already rendered HTML), the function
        returns it unchanged because you cannot modify rendered HTML safely.

    Parameters:
        field (Any): Typicall a Django BoundField (e.g. `form.field`) or a SafeString
            (already rendered HTML). If a BoundField is provided, its widget will be
            affected so that subsequent rendering includes the `disabled` attribute.
        condition (Any): A truthy/falsy value. If truthy, the field will be disabled.

    Returns:
        Any:
            - If `field` is a SafeString, returns it unchanged.
            - Otherwise returns the BoundField (which when rendered will include the disabled attribute).

    Raises:
        AttributeError: If `field` is not a BoundField and not a SafeString, attempts to
            access `field.field.widget` may raise.

    Example (template):
        {{ form.name|add_disabled:user.is_read_only }}

    Important notes / side effects:
        - THIS FUNCTION MUTATES `field.field.widget.attrs` directly when `condition` is truthy.
          That is a **side effect**: the widget instance keeps the disabled attribute for
          subsequent renders, which can be surprising if the same widget instance is reused.
        - If you prefer a pure (non-mutating) approach use:
          `field.as_widget(attrs={"disabled": "disabled"})`
          inside the template (although templates cannot call as_widget with args directly).
        - If `condition` is a string (e.g., "true") it will be treated truthy; convert as needed.
    """
    # If the field is already rendered HTML, don't try to modify it - return as is.
    if isinstance(field, SafeString):
        return field  # Already safe HTML; no modification possible

    # If condition is truthy, set the disabled attribute on the widget.
    if condition:
        try:
            # NOTE: this mutates the widget's attrs dict (side-effect). Documented above.
            field.field.widget.attrs["disabled"] = "disabled"
        except Exception:
            # If field doesn't have expected structure, raise a clearer error for debugging.
            raise AttributeError(
                "add_disabled filter expected a BoundField-like object as the first argument."
            )

    return field
