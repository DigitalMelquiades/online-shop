from django.urls import path

from . import views

app_name = 'shop'

urlpatterns = [
    path('', views.home, name='home'),
    path('product/<str:product_id>/', views.product, name='product'),
    path('product/<str:product_id>/review/', views.review, name='review'),
    path('cart/', views.cart, name='cart'),
    path('cart/add/', views.cart_add, name='cart_add'),
    path('cart/update/', views.cart_update, name='cart_update'),
    path('cart/remove/', views.cart_remove, name='cart_remove'),
    path('cart/checkout/', views.cart_checkout, name='cart_checkout'),
    path('sign-in/', views.sign_in, name='sign_in'),
    path('sign-up/', views.sign_up, name='sign_up'),
    path('sign-out/', views.sign_out, name='sign_out'),
]
