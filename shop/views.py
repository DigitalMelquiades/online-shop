from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Case, IntegerField, When
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import everrest
from .everrest import ApiError
from .models import Product, Review

PAGE_SIZE = 12

SORTS = {
    'recommended': (None, 'რეკომენდებული'),
    'rating': ('-rating', 'რეიტინგი: მაღალი პირველი'),
    'price_asc': ('price', 'ფასი: ზრდადობით'),
    'price_desc': ('-price', 'ფასი: კლებადობით'),
    'newest': ('-issue_date', 'ახალი პირველი'),
}

CATEGORY_NAMES = {'laptops': 'ლეპტოპები', 'phones': 'ტელეფონები'}


# ---------- helpers ----------

def safe_next(request, fallback='shop:home'):
    target = request.POST.get('next') or request.GET.get('next') or ''
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return reverse(fallback)


def forget_user(request):
    for key in ('access_token', 'refresh_token', 'user', 'cart_count'):
        request.session.pop(key, None)


def signed_in(view):
    """Send visitors without a session to the sign-in page, then back."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('access_token'):
            back = request.POST.get('next') or request.get_full_path()
            if request.method == 'POST':
                messages.info(request, 'კალათისა და შეფასებისთვის შედით ანგარიშზე.')
            return redirect(f"{reverse('shop:sign_in')}?{urlencode({'next': back})}")
        try:
            return view(request, *args, **kwargs)
        except ApiError as err:
            if err.auth_failed:
                forget_user(request)
                messages.error(request, 'სესიას ვადა გაუვიდა. შედით თავიდან.')
                return redirect(f"{reverse('shop:sign_in')}?{urlencode({'next': safe_next(request)})}")
            messages.error(request, err.message)
            return redirect(safe_next(request))
    return wrapper


def remember_cart(request, cart):
    request.session['cart_count'] = (cart or {}).get('total', {}).get('quantity', 0)


def in_stock(product):
    return max(product.get('stock') or 0, 0)


def number(value, cast=float):
    try:
        result = cast(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


# ---------- catalogue ----------

def home(request):
    g = request.GET
    sort = g.get('sort') if g.get('sort') in SORTS else 'recommended'
    page = number(g.get('page'), int) or 1
    filters = {
        'q': g.get('q', '').strip(),
        'category': g.get('category', ''),
        'brand': g.get('brand', ''),
        'price_min': number(g.get('price_min')),
        'price_max': number(g.get('price_max')),
        'rating': number(g.get('rating'), int),
        'sort': sort,
    }
    # The catalogue comes from the local copy made by `manage.py import_products`.
    # Products without any photo are kept in the database but not shown in the shop.
    found = Product.with_photo()
    if filters['q']:
        found = found.filter(title__icontains=filters['q'])
    if filters['category']:
        found = found.filter(category_id=filters['category'])
    if filters['brand']:
        found = found.filter(brand=filters['brand'])
    if filters['price_min'] is not None:
        found = found.filter(price__gte=filters['price_min'])
    if filters['price_max'] is not None:
        found = found.filter(price__lte=filters['price_max'])
    if filters['rating']:
        found = found.filter(rating__gte=filters['rating'])
    if sort == 'recommended':
        # In stock first, then the best rated.
        found = found.annotate(
            sold_out=Case(When(stock__lte=0, then=1), default=0, output_field=IntegerField()),
        ).order_by('sold_out', '-rating', 'title')
    else:
        found = found.order_by(SORTS[sort][0], 'title')

    total = found.count()
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(page, pages)
    products = [p.as_dict() for p in found[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]]

    everything = Product.with_photo()
    categories = [
        {'id': cid, 'label': CATEGORY_NAMES.get(name, name.title())}
        for cid, name in everything.values_list('category_id', 'category_name').distinct().order_by('category_id')
    ]
    brands = list(everything.values_list('brand', flat=True).distinct().order_by('brand'))

    active = any(filters[k] not in ('', None) for k in
                 ('q', 'category', 'brand', 'price_min', 'price_max', 'rating'))
    featured = None
    if not active and page == 1:
        best = everything.filter(stock__gt=0).order_by('-discount').first()
        featured = best.as_dict() if best else None
    return render(request, 'shop/home.html', {
        'featured': featured,
        'products': products, 'total': total,
        'catalogue_empty': not everything.exists(),
        'categories': categories, 'brands': brands,
        'filters': filters, 'filters_active': active,
        'sorts': [(key, label) for key, (_, label) in SORTS.items()],
        'rating_choices': [4, 3, 2],
        'page': page, 'pages': range(1, pages + 1), 'page_count': pages,
    })


def product(request, product_id):
    local = Product.with_photo().filter(api_id=product_id).first()
    if local is None:
        raise Http404
    item = local.as_dict()
    item['category_label'] = CATEGORY_NAMES.get(local.category_name, local.category_name)
    reviews = list(Review.objects.filter(product_id=product_id))
    user = request.session.get('user')
    mine = next((r for r in reviews if user and r.user_id == user['id']), None)
    return render(request, 'shop/product.html', {
        'product': item,
        'gallery': item['images'],
        'ratings_count': local.ratings_count,
        'reviews': reviews,
        'my_review': mine,
        'default_name': mine.full_name if mine else (user or {}).get('name', ''),
        'star_values': [5, 4, 3, 2, 1],
    })



@require_POST
@signed_in
def review(request, product_id):
    back = reverse('shop:product', args=[product_id])
    value = number(request.POST.get('rating'), int)
    name = request.POST.get('full_name', '').strip()[:80]
    text = request.POST.get('text', '').strip()[:2000]
    if not value or not 1 <= value <= 5:
        messages.error(request, 'აირჩიეთ ვარსკვლავების რაოდენობა 1-დან 5-მდე.')
        return redirect(back)
    if len(name) < 2:
        messages.error(request, 'ჩაწერეთ სახელი და გვარი.')
        return redirect(back)

    updated = everrest.rate(request.session, product_id, value)
    if isinstance(updated, dict) and updated.get('_id'):
        Product.sync(updated)
    Review.objects.update_or_create(
        product_id=product_id, user_id=request.session['user']['id'],
        defaults={'full_name': name, 'rating': value, 'text': text},
    )
    messages.success(request, 'შეფასება შენახულია.')
    return redirect(back + '#review')


# ---------- cart ----------

@signed_in
def cart(request):
    data = everrest.get_cart(request.session)
    remember_cart(request, data)
    lines = []
    if data and data.get('products'):
        details = everrest.get_products([p['productId'] for p in data['products']])
        for entry, item in zip(data['products'], details):
            if not item:
                continue
            local = Product.sync(item)
            lines.append({
                'id': entry['productId'],
                'quantity': entry['quantity'],
                'unit_price': entry.get('pricePerQuantity', item['price']['current']),
                'line_total': entry.get('pricePerQuantity', item['price']['current']) * entry['quantity'],
                'product': local.as_dict(),
                'available': in_stock(item),
                'reviews': local.ratings_count,
                'can_add': entry['quantity'] < in_stock(item),
            })
    total = (data or {}).get('total', {})
    price = total.get('price', {})
    return render(request, 'shop/cart.html', {
        'lines': lines,
        'total': price.get('current', 0),
        'total_before': price.get('beforeDiscount', 0),
        'saved': max(price.get('beforeDiscount', 0) - price.get('current', 0), 0),
        'quantity': total.get('quantity', 0),
    })


@require_POST
@signed_in
def cart_add(request):
    product_id = request.POST.get('id', '')
    current = everrest.get_cart(request.session)
    have = next((p['quantity'] for p in (current or {}).get('products', [])
                 if p['productId'] == product_id), 0)
    remember_cart(request, everrest.set_quantity(request.session, product_id, have + 1))
    messages.success(request, 'ნივთი დაემატა კალათაში.')
    return redirect(safe_next(request))


@require_POST
@signed_in
def cart_update(request):
    product_id = request.POST.get('id', '')
    quantity = number(request.POST.get('quantity'), int) or 0
    if quantity < 1:
        remember_cart(request, everrest.remove_from_cart(request.session, product_id))
    else:
        remember_cart(request, everrest.set_quantity(request.session, product_id, quantity))
    return redirect('shop:cart')


@require_POST
@signed_in
def cart_remove(request):
    remember_cart(request, everrest.remove_from_cart(request.session, request.POST.get('id', '')))
    messages.success(request, 'ნივთი წაიშალა კალათიდან.')
    return redirect('shop:cart')


@require_POST
@signed_in
def cart_checkout(request):
    everrest.checkout(request.session)
    request.session['cart_count'] = 0
    messages.success(request, 'შეკვეთა გაფორმდა. კალათა დაცარიელდა.')
    return redirect('shop:cart')


# ---------- account ----------

def sign_in(request):
    next_url = safe_next(request)
    email = ''
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        try:
            tokens = everrest.sign_in(email, request.POST.get('password', ''))
            request.session['access_token'] = tokens['access_token']
            request.session['refresh_token'] = tokens.get('refresh_token')
            profile = everrest.current_user(request.session)
            request.session['user'] = {
                'id': profile['_id'],
                'name': f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip(),
                'first_name': profile.get('firstName', ''),
                'email': profile.get('email', ''),
            }
            try:
                remember_cart(request, everrest.get_cart(request.session))
            except ApiError:
                request.session['cart_count'] = 0
            return redirect(next_url)
        except ApiError as err:
            forget_user(request)
            if err.has('errors.user_email_not_verified'):
                try:
                    everrest.send_verification(email)
                except ApiError:
                    pass
                messages.error(request, 'ელფოსტა ჯერ არ არის დადასტურებული. ახალი ბმული გამოგიგზავნეთ, '
                                        'გახსენით ის და შედით თავიდან.')
            else:
                messages.error(request, err.message)
    return render(request, 'shop/sign_in.html', {'next': next_url, 'email': email})


def sign_up(request):
    next_url = safe_next(request)
    form = {'gender': 'OTHER'}
    if request.method == 'POST':
        p = request.POST
        form = {key: p.get(key, '').strip() for key in
                ('firstName', 'lastName', 'age', 'email', 'address', 'phone', 'zipcode', 'gender')}
        password = p.get('password', '')
        if password != p.get('password2', ''):
            messages.error(request, 'პაროლები ერთმანეთს არ ემთხვევა.')
        else:
            payload = dict(form, password=password, age=number(form['age'], int) or 0)
            payload['avatar'] = ('https://api.dicebear.com/7.x/initials/svg?'
                                 + urlencode({'seed': f"{form['firstName']} {form['lastName']}"}))
            try:
                everrest.sign_up(payload)
                try:
                    everrest.send_verification(form['email'])
                except ApiError:
                    pass
                messages.success(request, f"ანგარიში შეიქმნა. დადასტურების ბმული გამოგზავნილია მისამართზე "
                                          f"{form['email']}. გახსენით ის და შემდეგ შედით.")
                return redirect(f"{reverse('shop:sign_in')}?{urlencode({'next': next_url})}")
            except ApiError as err:
                messages.error(request, err.message)
    return render(request, 'shop/sign_up.html', {'next': next_url, 'form': form})


@require_POST
def sign_out(request):
    forget_user(request)
    return redirect('shop:home')
