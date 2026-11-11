"""Thin client for the EverREST API (https://everrest.educata.dev).

Products, users and carts live on EverREST. Django keeps the user's tokens in
the session and calls the API on their behalf.
"""
from concurrent.futures import ThreadPoolExecutor

import requests
from django.conf import settings
from django.core.cache import cache

TIMEOUT = 15

MESSAGES = {
    'errors.incorrect_email_or_password': 'ელფოსტა ან პაროლი არასწორია.',
    'errors.email_in_use': 'ეს ელფოსტა უკვე რეგისტრირებულია.',
    'errors.user_email_not_verified': 'ელფოსტა ჯერ არ არის დადასტურებული. გახსენით წერილში მოსული ბმული.',
    'errors.invalid_email': 'ელფოსტის ფორმატი არასწორია.',
    'errors.invalid_phone_number': 'ტელეფონის ნომერი არასწორია. გამოიყენეთ ფორმატი +995599123456.',
    'errors.invalid_zipcode': 'საფოსტო ინდექსი არასწორია.',
    'errors.invalid_avatar': 'ავატარის ბმული არასწორია.',
    'errors.invalid_age': 'ასაკი არასწორია.',
    'errors.password_too_short': 'პაროლი უნდა შეიცავდეს მინიმუმ 8 სიმბოლოს.',
    'errors.password_too_long': 'პაროლი უნდა შეიცავდეს მაქსიმუმ 30 სიმბოლოს.',
    'errors.firstname_too_short': 'სახელი ძალიან მოკლეა.',
    'errors.lastname_too_short': 'გვარი ძალიან მოკლეა.',
    'errors.not_enough_stock_to_purchase': 'საწყობში ამდენი ცალი არ არის.',
    'errors.product_out_of_stock_before_checkout': 'ზოგი ნივთი შეკვეთამდე გაიყიდა. შეამოწმეთ კალათა.',
    'errors.product_not_found': 'ნივთი ვერ მოიძებნა.',
    'errors.item_not_found_in_cart': 'ეს ნივთი კალათაში აღარ არის.',
    'errors.token_expired': 'სესიას ვადა გაუვიდა. შედით თავიდან.',
    'errors.token_invalid': 'სესია არასწორია. შედით თავიდან.',
    'errors.token_not_found': 'ამ მოქმედებისთვის საჭიროა ავტორიზაცია.',
}


class ApiError(Exception):
    def __init__(self, status, keys=None, text=''):
        self.status = status
        self.keys = keys or []
        self.text = text
        super().__init__(self.message)

    @property
    def message(self):
        for key in self.keys:
            if key in MESSAGES:
                return MESSAGES[key]
        return self.text or 'სერვერთან დაკავშირება ვერ მოხერხდა. სცადეთ თავიდან.'

    def has(self, key):
        return key in self.keys

    @property
    def auth_failed(self):
        return self.status == 401 or any(k.startswith('errors.token_') for k in self.keys)


def _send(method, path, token=None, params=None, body=None):
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    try:
        res = requests.request(
            method, settings.EVERREST_URL + path,
            params=params, json=body, headers=headers, timeout=TIMEOUT,
        )
    except requests.RequestException:
        raise ApiError(503)
    try:
        data = res.json()
    except ValueError:
        data = {}
    if not res.ok:
        keys = data.get('errorKeys') if isinstance(data, dict) else None
        text = data.get('error') if isinstance(data, dict) else ''
        raise ApiError(res.status_code, keys, text if isinstance(text, str) else '')
    return data


def _refresh(session):
    """Swap the refresh token for a new access token. Returns True on success."""
    refresh = session.get('refresh_token')
    if not refresh:
        return False
    try:
        res = requests.post(
            settings.EVERREST_URL + '/auth/refresh',
            json={'refresh_token': refresh},
            cookies={'refresh_token': refresh},
            timeout=TIMEOUT,
        )
        token = res.json().get('access_token') if res.ok else None
    except (requests.RequestException, ValueError):
        token = None
    if not token:
        return False
    session['access_token'] = token
    return True


def call(session, method, path, params=None, body=None):
    """Authorised request; retries once with a refreshed token."""
    try:
        return _send(method, path, session.get('access_token'), params, body)
    except ApiError as err:
        if err.auth_failed and _refresh(session):
            return _send(method, path, session.get('access_token'), params, body)
        raise


# ---------- catalogue (public) ----------

def search_products(params):
    return _send('GET', '/shop/products/search', params=params)


def all_products():
    """Every product on the API (used by the import command)."""
    found, page = [], 1
    while True:
        data = _send('GET', '/shop/products/all', params={'page_index': page, 'page_size': 50})
        found += data.get('products', [])
        if not data.get('products') or len(found) >= data.get('total', 0):
            return found
        page += 1


def get_product(product_id):
    return _send('GET', f'/shop/products/id/{product_id}')


def get_products(ids):
    """Fetch several products at once; missing ones come back as None."""
    def one(pid):
        try:
            return get_product(pid)
        except ApiError:
            return None
    if not ids:
        return []
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(one, ids))


def _cached(key, path):
    data = cache.get(key)
    if data is None:
        data = _send('GET', path)
        cache.set(key, data, 600)
    return data


def categories():
    return _cached('everrest:categories', '/shop/products/categories')


def brands():
    return sorted(_cached('everrest:brands', '/shop/products/brands'))


# ---------- auth ----------

def sign_in(email, password):
    return _send('POST', '/auth/sign_in', body={'email': email, 'password': password})


def sign_up(data):
    return _send('POST', '/auth/sign_up', body=data)


def send_verification(email):
    return _send('POST', '/auth/verify_email', body={'email': email})


def current_user(session):
    return call(session, 'GET', '/auth')


# ---------- cart ----------

def get_cart(session):
    """The user's cart, or None when they have not started one."""
    try:
        return call(session, 'GET', '/shop/cart')
    except ApiError as err:
        if err.has('errors.user_has_no_cart') or err.status in (404, 409):
            return None
        raise


def set_quantity(session, product_id, quantity):
    """Put a product in the cart with exactly this quantity."""
    body = {'id': product_id, 'quantity': quantity}
    try:
        return call(session, 'PATCH', '/shop/cart/product', body=body)
    except ApiError as err:
        if err.auth_failed or err.has('errors.not_enough_stock_to_purchase') \
                or err.has('errors.product_not_found'):
            raise
        # No cart yet: the first product has to be sent with POST.
        return call(session, 'POST', '/shop/cart/product', body=body)


def remove_from_cart(session, product_id):
    return call(session, 'DELETE', '/shop/cart/product', body={'id': product_id})


def checkout(session):
    return call(session, 'POST', '/shop/cart/checkout')


def rate(session, product_id, value):
    return call(session, 'POST', '/shop/products/rate',
                body={'productId': product_id, 'rate': value})
