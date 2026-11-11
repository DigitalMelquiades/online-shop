def shop(request):
    """Values every page needs: who is signed in and how full the cart is."""
    return {
        'shopper': request.session.get('user'),
        'cart_count': request.session.get('cart_count', 0),
        'nav_categories': [('1', 'ლეპტოპები'), ('2', 'ტელეფონები')],
    }
