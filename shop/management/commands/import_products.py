"""Copy the catalogue from EverREST into the local database.

    python manage.py import_products            # products + photos
    python manage.py import_products --no-images
    python manage.py import_products --force     # download photos again

Safe to run again: rows are updated in place and saved photos are kept.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from shop import everrest
from shop.models import Product

EXTENSIONS = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif'}


def download(url, folder, name, force):
    """Save one photo; returns its path relative to MEDIA_ROOT, or '' if it is gone."""
    for old in folder.glob(name + '.*'):
        if not force:
            return old.relative_to(settings.MEDIA_ROOT).as_posix()
        old.unlink()
    try:
        res = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
    except requests.RequestException:
        return ''
    kind = res.headers.get('content-type', '').split(';')[0].strip()
    # imgur answers for deleted pictures with a "removed" placeholder image
    if not res.ok or kind not in EXTENSIONS or 'removed' in res.url:
        return ''
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name + EXTENSIONS[kind])
    path.write_bytes(res.content)
    return path.relative_to(settings.MEDIA_ROOT).as_posix()


class Command(BaseCommand):
    help = 'Import products (and their photos) from the EverREST API.'

    def add_arguments(self, parser):
        parser.add_argument('--no-images', action='store_true', help='import data only')
        parser.add_argument('--force', action='store_true', help='download photos again')

    def handle(self, *args, **options):
        try:
            listed = everrest.all_products()
        except everrest.ApiError as err:
            raise CommandError(f'API error: {err.text or err.status}')
        # The list has no ratings, so each product is read once more in full.
        full = everrest.get_products([p['_id'] for p in listed])
        products = [Product.sync(detail or short) for short, detail in zip(listed, full)]
        self.stdout.write(f'Products saved: {len(products)}')

        if options['no_images']:
            return
        root = Path(settings.MEDIA_ROOT) / 'products'
        jobs = []
        for product in products:
            folder = root / product.api_id
            jobs.append((product, 'thumb', product.thumbnail_url, folder))
            jobs += [(product, str(n), url, folder) for n, url in enumerate(product.image_urls, 1)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            saved = list(pool.map(lambda j: download(j[2], j[3], j[1], options['force']) if j[2] else '', jobs))

        ok = 0
        for product in products:
            mine = [(job[1], path) for job, path in zip(jobs, saved) if job[0] is product]
            product.thumbnail_file = next((p for name, p in mine if name == 'thumb'), '')
            product.image_files = [p for name, p in mine if name != 'thumb' and p]
            product.save(update_fields=['thumbnail_file', 'image_files'])
            if product.thumbnail_file or product.image_files:
                ok += 1
            else:
                self.stdout.write(self.style.WARNING(f'  no photo available: {product.title}'))
        self.stdout.write(self.style.SUCCESS(
            f'Photos saved: {sum(1 for p in saved if p)} of {len(jobs)}; products with a photo: {ok} of {len(products)}'))
