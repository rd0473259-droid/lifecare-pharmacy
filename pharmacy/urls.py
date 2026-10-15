from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("download-source/", views.download_source, name="download_source"),
    path("medicines/", views.product_list, name="product_list"),
    path("medicines/<int:pk>/", views.product_detail, name="product_detail"),
    path("categories/", views.category_list, name="category_list"),
    path("categories/<int:pk>/", views.category_detail, name="category_detail"),
    path("cart/", views.cart_view, name="cart"),
    path("cart/add/<int:product_id>/", views.cart_add, name="cart_add"),
    path("cart/update/<int:product_id>/", views.cart_update, name="cart_update"),
    path("cart/remove/<int:product_id>/", views.cart_remove, name="cart_remove"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/razorpay/verify/", views.razorpay_verify, name="razorpay_verify"),
    path("orders/", views.order_list, name="order_list"),
    path("orders/<str:order_number>/", views.order_detail, name="order_detail"),
    path("accounts/register/", views.register, name="register"),
]
