from datetime import datetime

from django import template
from django.utils.html import format_html

register = template.Library()

MONTHS = ['იანვარი', 'თებერვალი', 'მარტი', 'აპრილი', 'მაისი', 'ივნისი', 'ივლისი',
          'აგვისტო', 'სექტემბერი', 'ოქტომბერი', 'ნოემბერი', 'დეკემბერი']


@register.filter
def money(value):
    """1899 -> 1 899, 5414.05 -> 5 414.05"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    text = f'{number:,.2f}'.replace(',', ' ')
    return text[:-3] if text.endswith('.00') else text


@register.filter
def one_decimal(value):
    try:
        return f'{float(value):.1f}'
    except (TypeError, ValueError):
        return '0.0'


@register.filter
def iso_date(value):
    """ISO string from the API -> '1 დეკემბერი, 2022'"""
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return value
    return f'{d.day} {MONTHS[d.month - 1]}, {d.year}'


@register.simple_tag
def stars(value, label=True):
    """Five stars filled to the given rating (fractions allowed)."""
    try:
        rating = max(0.0, min(5.0, float(value)))
    except (TypeError, ValueError):
        rating = 0.0
    return format_html(
        '<span class="stars" role="img" aria-label="რეიტინგი {} 5-დან" style="--fill:{}%"></span>',
        f'{rating:.1f}', f'{rating * 20:.0f}',
    )


@register.simple_tag(takes_context=True)
def query(context, **changes):
    """Current query string with some parameters replaced (empty value removes)."""
    params = context['request'].GET.copy()
    for key, value in changes.items():
        if value in ('', None):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f'?{encoded}' if encoded else '?'


@register.simple_tag
def shop_stats():
    """Numbers for the admin start page."""
    from shop.models import Product, Review
    visible = Product.with_photo()
    return {
        'products': Product.objects.count(),
        'visible': visible.count(),
        'no_photo': Product.objects.count() - visible.count(),
        'sold_out': visible.filter(stock__lte=0).count(),
        'reviews': Review.objects.count(),
    }
