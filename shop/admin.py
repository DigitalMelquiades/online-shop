from django.contrib import admin, messages
from django.utils.html import format_html

from . import everrest
from .models import Product, Review

admin.site.site_header = 'თარო — ადმინისტრირება'
admin.site.site_title = 'თარო'
admin.site.index_title = 'მაღაზიის მართვა'


class HasPhotoFilter(admin.SimpleListFilter):
    title = 'ფოტო'
    parameter_name = 'photo'

    def lookups(self, request, model_admin):
        return [('yes', 'აქვს'), ('no', 'არ აქვს')]

    def queryset(self, request, queryset):
        missing = queryset.filter(photo='', thumbnail_file='', image_files=[])
        if self.value() == 'no':
            return missing
        if self.value() == 'yes':
            return queryset.exclude(pk__in=missing)
        return queryset


class InStockFilter(admin.SimpleListFilter):
    title = 'მარაგი'
    parameter_name = 'in_stock'

    def lookups(self, request, model_admin):
        return [('yes', 'მარაგშია'), ('no', 'ამოიწურა')]

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(stock__gt=0)
        if self.value() == 'no':
            return queryset.filter(stock__lte=0)
        return queryset


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('preview', 'title', 'brand_name', 'category_name', 'price_tag', 'discount_tag',
                    'stock_tag', 'rating_tag')
    list_display_links = ('preview', 'title')
    list_filter = ('category_name', 'brand', InStockFilter, HasPhotoFilter)
    search_fields = ('title', 'brand', 'api_id')
    list_per_page = 25
    actions = ['refresh_from_api']
    readonly_fields = ('big_preview', 'api_id', 'rating', 'ratings_count', 'thumbnail_url')
    fieldsets = (
        (None, {'fields': ('title', 'description', 'brand', ('category_id', 'category_name'))}),
        ('ფასი და მარაგი', {
            'fields': (('price', 'price_before', 'discount'), 'stock', 'warranty', 'issue_date'),
            'description': 'ეს ველები API-დან მოდის. აქ შეცვლილი მნიშვნელობა ჩანს საიტზე, '
                           'მაგრამ API-დან განახლებისას თავიდან გადაიწერება.',
        }),
        ('ფოტო', {'fields': ('big_preview', 'photo')}),
        ('API', {'fields': ('api_id', 'rating', 'ratings_count', 'thumbnail_url'), 'classes': ('collapse',)}),
    )

    @admin.display(description='ფოტო')
    def preview(self, obj):
        if not obj.photo_url:
            return '—'
        return format_html('<img src="{}" alt="" style="width:48px;height:48px;object-fit:contain">',
                           obj.photo_url)

    @admin.display(description='ბრენდი', ordering='brand')
    def brand_name(self, obj):
        return obj.brand.title()

    @admin.display(description='ფასი', ordering='price')
    def price_tag(self, obj):
        amount = f'{obj.price:,.0f}'.replace(',', ' ')
        return amount + ' $'

    @admin.display(description='ფასდაკლება', ordering='discount')
    def discount_tag(self, obj):
        if not obj.discount:
            return '—'
        return format_html('<span class="tag tag--sale">−{}%</span>', f'{obj.discount:.0f}')

    @admin.display(description='მარაგი', ordering='stock')
    def stock_tag(self, obj):
        if obj.stock <= 0:
            return format_html('<span class="tag tag--out">{}</span>', 'ამოიწურა')
        return f'{obj.stock} ცალი'

    @admin.display(description='რეიტინგი', ordering='rating')
    def rating_tag(self, obj):
        return format_html('<span class="star">★</span> {} <span class="quiet">({})</span>',
                           f'{obj.rating:.1f}', obj.ratings_count)

    @admin.display(description='ამჟამინდელი ფოტო')
    def big_preview(self, obj):
        if not obj.photo_url:
            return 'ფოტო არ არის. ატვირთეთ ქვემოთ.'
        return format_html('<img src="{}" alt="" style="max-width:260px;max-height:260px;object-fit:contain">',
                           obj.photo_url)

    @admin.action(description='არჩეული ნივთების განახლება API-დან')
    def refresh_from_api(self, request, queryset):
        fresh = everrest.get_products(list(queryset.values_list('api_id', flat=True)))
        done = 0
        for data in fresh:
            if data:
                Product.sync(data)
                done += 1
        level = messages.SUCCESS if done == len(fresh) else messages.WARNING
        self.message_user(request, f'განახლდა {done} ნივთი {len(fresh)}-დან.', level)

    def has_add_permission(self, request):
        # New products come from the API (manage.py import_products); carts only know API products.
        return False


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'stars', 'product_title', 'short_text', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('full_name', 'text', 'product_id')
    date_hierarchy = 'created_at'
    readonly_fields = ('product_id', 'user_id', 'created_at')

    @admin.display(description='რეიტინგი', ordering='rating')
    def stars(self, obj):
        return '★' * obj.rating + '☆' * (5 - obj.rating)

    @admin.display(description='ნივთი')
    def product_title(self, obj):
        product = Product.objects.filter(api_id=obj.product_id).first()
        return product.title if product else obj.product_id

    @admin.display(description='ტექსტი')
    def short_text(self, obj):
        return obj.text[:80] + ('…' if len(obj.text) > 80 else '')
