from django import template

register = template.Library()


@register.filter("get_item")
def get_item(queryset, habit_id):
    return queryset.filter(habit__id=habit_id).first()
