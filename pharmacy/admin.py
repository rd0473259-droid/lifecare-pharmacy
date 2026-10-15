from django.contrib import admin
from .models import Category, Order, OrderItem, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "stock", "is_available", "prescription_required")
    list_filter = ("category", "is_available", "prescription_required")
    search_fields = ("name", "description")
    list_editable = ("price", "stock", "is_available", "prescription_required")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "quantity", "purchase_price")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "user", "full_name", "total", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("order_number", "full_name", "contact_number", "user__username")
    readonly_fields = ("order_number", "user", "total", "created_at", "payment_method")
    inlines = (OrderItemInline,)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "quantity", "purchase_price")
    search_fields = ("order__order_number", "product__name")
