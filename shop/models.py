from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.templatetags.static import static
from django.utils.dateparse import parse_datetime


class Review(models.Model):
    """A written review.

    EverREST stores only the star value of a rating, so the reviewer's name
    and text are kept here, next to the same star value.
    """
    product_id = models.CharField('ნივთის ID', max_length=64, db_index=True)
    user_id = models.CharField('მომხმარებლის ID', max_length=64)
    full_name = models.CharField('სახელი გვარი', max_length=80)
    rating = models.PositiveSmallIntegerField('რეიტინგი')
    text = models.TextField('ტექსტი', blank=True)
    created_at = models.DateTimeField('თარიღი', auto_now=True)

    class Meta:
        verbose_name = 'შეფასება'
        verbose_name_plural = 'შეფასებები'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['product_id', 'user_id'], name='one_review_per_user'),
        ]

    def __str__(self):
        return f'{self.full_name}: {self.rating}/5'


class Product(models.Model):
    """Local copy of an EverREST product, filled by `manage.py import_products`.

    The catalogue is read from this table; photos are stored under MEDIA_ROOT.
    Carts and accounts stay on EverREST, so `api_id` is what links the two.
    """
    api_id = models.CharField('API-ის ID', max_length=64, unique=True)
    title = models.CharField('დასახელება', max_length=255)
    description = models.TextField('აღწერა', blank=True)
    brand = models.CharField('ბრენდი', max_length=60, db_index=True)
    category_id = models.CharField('კატეგორიის ID', max_length=16, db_index=True)
    category_name = models.CharField('კატეგორია', max_length=60)
    price = models.FloatField('ფასი, $')
    price_before = models.FloatField('ფასი ფასდაკლებამდე, $', default=0)
    discount = models.FloatField('ფასდაკლება, %', default=0)
    stock = models.IntegerField('მარაგი', default=0)
    rating = models.FloatField('რეიტინგი', default=0)
    ratings_count = models.PositiveIntegerField('შეფასებების რაოდენობა', default=0)
    warranty = models.PositiveSmallIntegerField('გარანტია, წელი', default=0)
    issue_date = models.DateTimeField('გამოშვების თარიღი', null=True, blank=True)
    # Original addresses on the API, and the files saved from them (relative to MEDIA_ROOT).
    thumbnail_url = models.URLField('ფოტოს ბმული API-ზე', max_length=500, blank=True)
    image_urls = models.JSONField(default=list)
    thumbnail_file = models.CharField(max_length=200, blank=True)
    image_files = models.JSONField(default=list)
    # A photo uploaded in the admin panel; shown instead of the API photo and never touched by the import.
    photo = models.FileField(
        'საკუთარი ფოტო', upload_to='products/custom/', blank=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])],
        help_text='ატვირთეთ, თუ API-ის ფოტო გატეხილია ან გსურთ მისი შეცვლა.',
    )

    class Meta:
        verbose_name = 'ნივთი'
        verbose_name_plural = 'ნივთები'
        ordering = ['title']

    def __str__(self):
        return self.title

    @classmethod
    def with_photo(cls):
        """Products the shop shows: the ones that have at least one photo."""
        return cls.objects.exclude(photo='', thumbnail_file='', image_files=[])

    @property
    def photo_url(self):
        """Best available photo: uploaded one, then the downloaded thumbnail, then the first gallery image."""
        if self.photo:
            return self.photo.url
        if self.thumbnail_file:
            return settings.MEDIA_URL + self.thumbnail_file
        if self.image_files:
            return settings.MEDIA_URL + self.image_files[0]
        return ''

    @classmethod
    def sync(cls, data):
        """Create or refresh the local row from one API product."""
        price = data.get('price') or {}
        category = data.get('category') or {}
        values = {
            'title': data.get('title', ''),
            'description': data.get('description', ''),
            'brand': (data.get('brand') or '').lower(),
            'category_id': str(category.get('id', '')),
            'category_name': category.get('name', ''),
            'price': price.get('current') or 0,
            'price_before': price.get('beforeDiscount') or 0,
            'discount': price.get('discountPercentage') or 0,
            'stock': data.get('stock') or 0,
            'rating': data.get('rating') or 0,
            'warranty': data.get('warranty') or 0,
            'issue_date': parse_datetime(data.get('issueDate') or '') if data.get('issueDate') else None,
            'thumbnail_url': data.get('thumbnail') or '',
            'image_urls': data.get('images') or [],
        }
        if 'ratings' in data:           # only the single-product endpoint lists them
            values['ratings_count'] = len(data['ratings'] or [])
        product, _ = cls.objects.update_or_create(api_id=data['_id'], defaults=values)
        return product

    def as_dict(self):
        """The shape the templates use (same field names as the API)."""
        media = settings.MEDIA_URL
        photo = self.photo_url
        images = [media + f for f in self.image_files]
        if self.photo:
            images = [photo] + images
        images = images or ([photo] if photo else [])
        return {
            'id': self.api_id,
            'title': self.title,
            'description': self.description,
            'brand': self.brand,
            'category': {'id': self.category_id, 'name': self.category_name},
            'price': {'current': self.price, 'beforeDiscount': self.price_before,
                      'discountPercentage': self.discount},
            'stock': self.stock,
            'available': max(self.stock, 0),
            'rating': self.rating,
            'ratings_count': self.ratings_count,
            'warranty': self.warranty,
            'issueDate': self.issue_date.isoformat() if self.issue_date else '',
            'thumbnail': photo or static('shop/noimage.svg'),
            'images': images or [static('shop/noimage.svg')],
        }
