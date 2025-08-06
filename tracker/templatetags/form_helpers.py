from django import template
from django.utils.safestring import SafeString

register = template.Library()


@register.filter(name="add_class")
def add_class(field, css_class):
    existing_classes = field.field.widget.attrs.get("class", "")
    return field.as_widget(attrs={"class": f"{existing_classes} {css_class}".strip()})


@register.filter
def add_disabled(field, condition):
    if isinstance(field, SafeString):
        return field  # It's already rendered HTML; can't modify
    if condition:
        field.field.widget.attrs["disabled"] = "disabled"
    return field
