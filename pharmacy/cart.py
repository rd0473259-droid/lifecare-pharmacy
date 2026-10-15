from decimal import Decimal
from .models import Product


def cart_lines(request):
    cart = request.session.get("cart", {})
    products = Product.objects.filter(pk__in=cart.keys()).select_related("category")
    lines = []
    for product in products:
        try:
            quantity = int(cart.get(str(product.pk), 0))
        except (TypeError, ValueError):
            continue
        if quantity > 0:
            lines.append({
                "product": product,
                "quantity": quantity,
                "unit_price": product.price,
                "line_total": product.price * quantity,
            })
    subtotal = sum((line["line_total"] for line in lines), Decimal("0.00"))
    return lines, subtotal
