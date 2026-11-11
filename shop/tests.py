"""Signed-in flows, with EverREST replaced by a small in-memory fake."""
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from . import everrest
from .models import Product, Review

PRODUCT = {
    '_id': 'p1', 'title': 'Test Phone', 'description': 'A phone.', 'brand': 'apple',
    'price': {'current': 100, 'currency': 'USD', 'beforeDiscount': 120, 'discountPercentage': 17},
    'category': {'id': '2', 'name': 'phones', 'image': ''}, 'issueDate': '2023-07-31T00:00:00.000Z',
    'thumbnail': 'https://example.com/a.jpg', 'images': ['https://example.com/a.jpg'],
    'stock': 3, 'rating': 4.2, 'warranty': 2, 'ratings': [{'userId': 'u9', 'value': 4}],
}


class FakeApi:
    def __init__(self):
        self.cart = None
        self.rated = []

    def _cart(self):
        qty = sum(p['quantity'] for p in self.cart['products'])
        self.cart['total'] = {'price': {'current': 100 * qty, 'beforeDiscount': 120 * qty},
                              'quantity': qty, 'products': len(self.cart['products'])}
        return self.cart

    def send(self, method, path, token=None, params=None, body=None):
        if path == '/auth/sign_in':
            if body['password'] != 'right-password':
                raise everrest.ApiError(400, ['errors.incorrect_email_or_password'])
            return {'access_token': 'tok', 'refresh_token': 'ref'}
        if path.startswith('/shop/products/id/'):
            return dict(PRODUCT)
        if token != 'tok':
            raise everrest.ApiError(401, ['errors.token_not_found'])
        if path == '/auth':
            return {'_id': 'u1', 'firstName': 'Nino', 'lastName': 'Beridze', 'email': 'n@example.com'}
        if path == '/shop/products/rate':
            self.rated.append(body)
            return dict(PRODUCT)
        if path == '/shop/cart' and method == 'GET':
            if self.cart is None:
                raise everrest.ApiError(409, ['errors.user_has_no_cart'])
            return self._cart()
        if path == '/shop/cart/checkout':
            self.cart = None
            return {'success': True}
        if path == '/shop/cart/product':
            if method == 'POST':
                if self.cart is not None:
                    raise everrest.ApiError(409, ['errors.user_already_has_cart'])
                self.cart = {'products': []}
            elif self.cart is None:
                raise everrest.ApiError(409, ['errors.user_has_no_cart'])
            items = [p for p in self.cart['products'] if p['productId'] != body['id']]
            if method != 'DELETE':
                if body['quantity'] > PRODUCT['stock']:
                    raise everrest.ApiError(400, ['errors.not_enough_stock_to_purchase'])
                items.append({'productId': body['id'], 'quantity': body['quantity'], 'pricePerQuantity': 100})
            self.cart['products'] = items
            return self._cart()
        raise AssertionError(f'unexpected call {method} {path}')


class ShopFlowTests(TestCase):
    def setUp(self):
        self.api = FakeApi()
        Product.sync(PRODUCT)
        Product.objects.update(thumbnail_file='products/p1/thumb.jpg')
        patcher = patch.object(everrest, '_send', side_effect=self.api.send)
        patcher.start()
        self.addCleanup(patcher.stop)

    def login(self):
        return self.client.post(reverse('shop:sign_in'),
                                {'email': 'n@example.com', 'password': 'right-password', 'next': '/cart/'})

    def test_cart_needs_sign_in(self):
        self.assertRedirects(self.client.get('/cart/'), '/sign-in/?next=%2Fcart%2F')
        res = self.client.post(reverse('shop:cart_add'), {'id': 'p1', 'next': '/'})
        self.assertEqual(res.status_code, 302)
        self.assertIsNone(self.api.cart)

    def test_wrong_password_shows_error(self):
        res = self.client.post(reverse('shop:sign_in'), {'email': 'n@example.com', 'password': 'nope'})
        self.assertContains(res, 'ელფოსტა ან პაროლი არასწორია')
        self.assertNotIn('access_token', self.client.session)

    def test_cart_add_change_remove(self):
        self.assertRedirects(self.login(), '/cart/')
        self.assertContains(self.client.get('/cart/'), 'კალათა ცარიელია')

        self.client.post(reverse('shop:cart_add'), {'id': 'p1', 'next': '/'})   # creates cart
        self.client.post(reverse('shop:cart_add'), {'id': 'p1', 'next': '/'})   # 1 -> 2
        self.assertEqual(self.api.cart['products'][0]['quantity'], 2)
        self.assertEqual(self.client.session['cart_count'], 2)

        page = self.client.get('/cart/')
        self.assertContains(page, 'Test Phone')
        self.assertEqual(page.context['total'], 200)
        self.assertEqual(page.context['lines'][0]['reviews'], 1)

        self.client.post(reverse('shop:cart_update'), {'id': 'p1', 'quantity': 3})
        self.assertEqual(self.client.get('/cart/').context['total'], 300)
        self.assertFalse(self.client.get('/cart/').context['lines'][0]['can_add'])

        res = self.client.post(reverse('shop:cart_update'), {'id': 'p1', 'quantity': 4}, follow=True)
        self.assertContains(res, 'საწყობში ამდენი ცალი არ არის')

        self.client.post(reverse('shop:cart_remove'), {'id': 'p1'})
        self.assertContains(self.client.get('/cart/'), 'კალათა ცარიელია')
        self.assertEqual(self.client.session['cart_count'], 0)

    def test_review_is_saved_and_shown(self):
        self.login()
        url = reverse('shop:review', args=['p1'])
        self.client.post(url, {'rating': 5, 'full_name': 'ნინო ბერიძე', 'text': 'კარგი ტელეფონია'})
        self.client.post(url, {'rating': 4, 'full_name': 'ნინო ბერიძე', 'text': 'შევცვალე'})
        self.assertEqual([r['rate'] for r in self.api.rated], [5, 4])
        self.assertEqual(Review.objects.count(), 1)
        page = self.client.get(reverse('shop:product', args=['p1']))
        self.assertContains(page, 'ნინო ბერიძე')
        self.assertContains(page, 'შევცვალე')

    def test_expired_session_goes_back_to_sign_in(self):
        self.login()
        session = self.client.session
        session['access_token'] = 'stale'
        session.pop('refresh_token')
        session.save()
        res = self.client.get('/cart/')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/sign-in/', res['Location'])
        self.assertNotIn('user', self.client.session)



class CatalogueTests(TestCase):
    def setUp(self):
        Product.sync(PRODUCT)
        Product.objects.update(thumbnail_file='products/p1/thumb.jpg')
        Product.sync(dict(PRODUCT, _id='p2', title='Work Laptop', brand='lenovo', rating=3.1, stock=0,
                          price={'current': 900, 'beforeDiscount': 900, 'discountPercentage': 0},
                          category={'id': '1', 'name': 'laptops'}))
        Product.sync(dict(PRODUCT, _id='p3', title='No Photo Phone'))
        Product.objects.exclude(api_id='p3').update(thumbnail_file='products/x/thumb.jpg')

    def titles(self, query=''):
        return [p['title'] for p in self.client.get('/' + query).context['products']]

    def test_filters_and_sorting(self):
        self.assertEqual(self.titles('?sort=rating'), ['Test Phone', 'Work Laptop'])
        self.assertEqual(self.titles(), ['Test Phone', 'Work Laptop'])          # in stock first
        self.assertEqual(self.titles('?sort=price_desc'), ['Work Laptop', 'Test Phone'])
        self.assertEqual(self.titles('?q=laptop'), ['Work Laptop'])
        self.assertEqual(self.titles('?category=2'), ['Test Phone'])
        self.assertEqual(self.titles('?brand=lenovo'), ['Work Laptop'])
        self.assertEqual(self.titles('?price_min=500'), ['Work Laptop'])
        self.assertEqual(self.titles('?price_max=500'), ['Test Phone'])
        self.assertEqual(self.titles('?rating=4'), ['Test Phone'])
        self.assertEqual(self.titles('?brand=asus'), [])

    def test_product_page_and_missing_product(self):
        self.assertContains(self.client.get('/product/p1/'), 'Test Phone')
        self.assertEqual(self.client.get('/product/unknown/').status_code, 404)

    def test_products_without_photo_are_hidden(self):
        self.assertNotIn('No Photo Phone', self.titles())
        self.assertEqual(self.client.get('/product/p3/').status_code, 404)
        Product.objects.filter(api_id='p3').update(photo='products/custom/new.jpg')
        self.assertIn('No Photo Phone', self.titles())
