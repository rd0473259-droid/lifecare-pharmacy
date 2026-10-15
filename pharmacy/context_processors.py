def cart_count(request):
    cart = request.session.get("cart", {})
    count = sum(int(quantity) for quantity in cart.values() if str(quantity).isdigit())
    return {"cart_count": count}
