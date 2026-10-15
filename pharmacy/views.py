import uuid
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import razorpay
from requests.exceptions import RequestException
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .cart import cart_lines
from .forms import CheckoutForm, RegistrationForm
from .models import Category, Order, OrderItem, Product


def get_razorpay_client():
    key_id = getattr(settings, "RAZORPAY_KEY_ID", "")
    key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "")
    if not (key_id and key_secret):
        return None
    return razorpay.Client(auth=(key_id, key_secret))


def create_razorpay_order(total, receipt_number):
    client = get_razorpay_client()
    if client is None:
        raise RuntimeError("Razorpay is not configured.")
    amount = int((Decimal(str(total)) * Decimal("100")).to_integral_value())
    return client.order.create({
        "amount": amount,
        "currency": "INR",
        "receipt": receipt_number,
        "payment_capture": 1,
    })


RAZORPAY_API_ERRORS = (
    razorpay.errors.BadRequestError,
    razorpay.errors.GatewayError,
    razorpay.errors.ServerError,
    RequestException,
)


def home(request):
    featured = Product.objects.filter(is_available=True).select_related("category")[:6]
    categories = Category.objects.all()[:6]
    return render(request, "pharmacy/home.html", {"featured_products": featured, "categories": categories})


def product_list(request):
    products = Product.objects.filter(is_available=True).select_related("category")
    query = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "").strip()
    if query:
        products = products.filter(name__icontains=query)
    if category_id.isdigit():
        products = products.filter(category_id=int(category_id))
    return render(request, "pharmacy/product_list.html", {
        "products": products,
        "categories": Category.objects.all(),
        "query": query,
        "selected_category": category_id,
    })


def product_detail(request, pk):
    product = get_object_or_404(Product.objects.select_related("category"), pk=pk, is_available=True)
    return render(request, "pharmacy/product_detail.html", {"product": product})


def category_list(request):
    return render(request, "pharmacy/category_list.html", {"categories": Category.objects.all()})


def category_detail(request, pk):
    category = get_object_or_404(Category, pk=pk)
    products = category.products.filter(is_available=True).select_related("category")
    return render(request, "pharmacy/product_list.html", {
        "products": products, "categories": Category.objects.all(),
        "active_category": category, "selected_category": str(category.pk),
    })


def cart_view(request):
    cart = request.session.get("cart", {})
    invalid_keys = [key for key in cart if not str(key).isdigit()]
    for key in invalid_keys:
        cart.pop(key, None)
    known_ids = set(Product.objects.filter(pk__in=cart.keys()).values_list("pk", flat=True))
    stale_keys = [key for key in cart if int(key) not in known_ids]
    stale_keys.extend(invalid_keys)
    for key in stale_keys:
        cart.pop(key, None)
    if stale_keys:
        request.session["cart"] = cart
        messages.error(request, "An item that is no longer in the catalog was removed from your cart.")
    lines, subtotal = cart_lines(request)
    can_checkout = all(
        line["product"].is_available and line["product"].stock >= line["quantity"]
        for line in lines
    )
    return render(request, "pharmacy/cart.html", {
        "lines": lines, "subtotal": subtotal, "total": subtotal, "can_checkout": can_checkout,
    })


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    try:
        quantity = int(request.POST.get("quantity", "1"))
    except (TypeError, ValueError):
        quantity = 0
    if quantity < 1:
        messages.error(request, "Please choose a valid quantity.")
    elif not product.is_available or product.stock < 1:
        messages.error(request, "This product is currently unavailable.")
    else:
        cart = request.session.get("cart", {})
        try:
            current = int(cart.get(str(product.pk), 0))
        except (TypeError, ValueError):
            current = 0
        if current + quantity > product.stock:
            messages.error(request, f"Only {product.stock} unit(s) are currently in stock.")
        else:
            cart[str(product.pk)] = current + quantity
            request.session["cart"] = cart
            messages.success(request, f"{product.name} added to your cart.")
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("cart")


@require_POST
def cart_update(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    try:
        quantity = int(request.POST.get("quantity", "0"))
    except (TypeError, ValueError):
        quantity = 0
    cart = request.session.get("cart", {})
    if quantity < 1:
        messages.error(request, "Quantity must be at least one. Use Remove to delete an item.")
    elif not product.is_available or quantity > product.stock:
        messages.error(request, f"Only {product.stock} unit(s) of {product.name} are available.")
    else:
        cart[str(product.pk)] = quantity
        request.session["cart"] = cart
        messages.success(request, "Cart quantity updated.")
    return redirect("cart")


@require_POST
def cart_remove(request, product_id):
    cart = request.session.get("cart", {})
    cart.pop(str(product_id), None)
    request.session["cart"] = cart
    messages.success(request, "Item removed from your cart.")
    return redirect("cart")


@login_required
def checkout(request):
    razorpay_enabled = bool(
        getattr(settings, "RAZORPAY_KEY_ID", "")
        and getattr(settings, "RAZORPAY_KEY_SECRET", "")
    )
    lines, subtotal = cart_lines(request)
    if not lines:
        messages.error(request, "Your cart is empty. Add an item before checkout.")
        return redirect("cart")
    if any(not line["product"].is_available or line["product"].stock < line["quantity"] for line in lines):
        messages.error(request, "One or more cart items are unavailable or exceed current stock. Update your cart before checkout.")
        return redirect("cart")
    if request.method == "POST":
        form = CheckoutForm(request.POST, razorpay_enabled=razorpay_enabled)
        if form.is_valid():
            payment_method = form.cleaned_data["payment_method"]
            try:
                with transaction.atomic():
                    locked_products = {
                        product.pk: product
                        for product in Product.objects.select_for_update().filter(
                            pk__in=[line["product"].pk for line in lines]
                        )
                    }
                    checked_lines = []
                    total = Decimal("0.00")
                    for line in lines:
                        product = locked_products.get(line["product"].pk)
                        quantity = line["quantity"]
                        if product is None or not product.is_available or product.stock < quantity:
                            raise ValueError(f"{line['product'].name} no longer has enough stock. Please review your cart.")
                        total += product.price * quantity
                        checked_lines.append((product, quantity, product.price))

                    if payment_method == "Razorpay":
                        if not (getattr(settings, "RAZORPAY_KEY_ID", "") and getattr(settings, "RAZORPAY_KEY_SECRET", "")):
                            raise ValueError("Razorpay is not configured. Please add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.")
                        receipt_number = f"LC-{uuid.uuid4().hex[:8].upper()}"
                        order_data = create_razorpay_order(total, receipt_number)
                        request.session["pending_razorpay_checkout"] = {
                            "full_name": form.cleaned_data["full_name"],
                            "contact_number": form.cleaned_data["contact_number"],
                            "address": form.cleaned_data["address"],
                            "city": form.cleaned_data["city"],
                            "state": form.cleaned_data["state"],
                            "pin_code": form.cleaned_data["pin_code"],
                            "notes": form.cleaned_data["notes"],
                            "lines": [
                                {
                                    "product_id": product.pk,
                                    "quantity": quantity,
                                    "purchase_price": str(purchase_price),
                                }
                                for product, quantity, purchase_price in checked_lines
                            ],
                            "amount": str(total),
                            "amount_paise": int((total * Decimal("100")).to_integral_value()),
                            "razorpay_order_id": order_data["id"],
                            "receipt_number": receipt_number,
                        }
                        return render(request, "pharmacy/checkout_razorpay.html", {
                            "key_id": settings.RAZORPAY_KEY_ID,
                            "order_id": order_data["id"],
                            "amount": int((Decimal(str(total)) * Decimal("100")).to_integral_value()),
                            "display_amount": total,
                            "currency": "INR",
                            "receipt": receipt_number,
                            "name": "LifeCare Pharmacy",
                            "description": "Medicine order payment",
                        })

                    for product, quantity, purchase_price in checked_lines:
                        updated = Product.objects.filter(
                            pk=product.pk, is_available=True, stock__gte=quantity
                        ).update(stock=F("stock") - quantity)
                        if updated != 1:
                            raise ValueError(f"{product.name} no longer has enough stock. Please review your cart.")

                    order = Order.objects.create(
                        user=request.user,
                        full_name=form.cleaned_data["full_name"],
                        contact_number=form.cleaned_data["contact_number"],
                        address=form.cleaned_data["address"],
                        city=form.cleaned_data["city"],
                        state=form.cleaned_data["state"],
                        pin_code=form.cleaned_data["pin_code"],
                        notes=form.cleaned_data["notes"],
                        total=total,
                        payment_method=form.cleaned_data["payment_method"],
                    )
                    for product, quantity, purchase_price in checked_lines:
                        OrderItem.objects.create(
                            order=order, product=product, quantity=quantity, purchase_price=purchase_price
                        )
                request.session["cart"] = {}
                return redirect("order_detail", order_number=order.order_number)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("cart")
            except razorpay.errors.BadRequestError:
                messages.error(
                    request,
                    "Razorpay rejected the order. Check that your active test-mode key ID and secret match.",
                )
                return redirect("checkout")
            except (razorpay.errors.GatewayError, razorpay.errors.ServerError, RequestException):
                messages.error(
                    request,
                    "Razorpay could not create the payment right now. Check your internet connection and try again.",
                )
                return redirect("checkout")
    else:
        initial = {"full_name": request.user.get_full_name() or request.user.username}
        form = CheckoutForm(initial=initial, razorpay_enabled=razorpay_enabled)
    return render(request, "pharmacy/checkout.html", {
        "form": form,
        "lines": lines,
        "total": subtotal,
        "razorpay_enabled": razorpay_enabled,
    })


@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items__product")
    return render(request, "pharmacy/order_list.html", {"orders": orders})


@login_required
def order_detail(request, order_number):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__product"),
        order_number=order_number,
        user=request.user,
    )
    return render(request, "pharmacy/order_detail.html", {"order": order})


@login_required
@require_POST
def razorpay_verify(request):
    pending = request.session.get("pending_razorpay_checkout")
    if not pending:
        return JsonResponse({"status": "error", "message": "Checkout session expired."}, status=400)

    razorpay_payment_id = request.POST.get("razorpay_payment_id")
    razorpay_order_id = request.POST.get("razorpay_order_id")
    razorpay_signature = request.POST.get("razorpay_signature")
    if not all([razorpay_payment_id, razorpay_order_id, razorpay_signature]):
        return JsonResponse({"status": "error", "message": "Payment verification failed."}, status=400)
    if razorpay_order_id != pending.get("razorpay_order_id"):
        return JsonResponse({"status": "error", "message": "Payment does not match this checkout."}, status=400)

    client = get_razorpay_client()
    if client is None:
        return JsonResponse({"status": "error", "message": "Razorpay is not configured."}, status=400)

    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        return JsonResponse({"status": "error", "message": "Invalid Razorpay signature."}, status=400)
    try:
        payment = client.payment.fetch(razorpay_payment_id)
    except RAZORPAY_API_ERRORS:
        return JsonResponse({
            "status": "error",
            "message": "Razorpay could not confirm the payment status. Check your test-mode credentials and try again.",
        }, status=502)

    if (
        payment.get("order_id") != pending["razorpay_order_id"]
        or payment.get("amount") != pending["amount_paise"]
        or payment.get("currency") != "INR"
        or payment.get("status") != "captured"
    ):
        return JsonResponse({"status": "error", "message": "Payment was not captured for the expected amount."}, status=400)

    try:
        with transaction.atomic():
            product_ids = [item["product_id"] for item in pending["lines"]]
            products = {
                product.pk: product
                for product in Product.objects.select_for_update().filter(pk__in=product_ids)
            }
            checked_lines = []
            for item in pending["lines"]:
                product = products.get(item["product_id"])
                quantity = item["quantity"]
                if product is None or not product.is_available or product.stock < quantity:
                    raise ValueError(
                        f"{product.name if product else 'One item'} is no longer available."
                    )
                updated = Product.objects.filter(
                    pk=product.pk, is_available=True, stock__gte=quantity
                ).update(stock=F("stock") - quantity)
                if updated != 1:
                    raise ValueError(f"{product.name} no longer has enough stock.")
                checked_lines.append((
                    product,
                    quantity,
                    Decimal(item["purchase_price"]),
                ))

            order = Order.objects.create(
                user=request.user,
                full_name=pending["full_name"],
                contact_number=pending["contact_number"],
                address=pending["address"],
                city=pending["city"],
                state=pending["state"],
                pin_code=pending["pin_code"],
                notes=pending["notes"],
                total=Decimal(pending["amount"]),
                payment_method="Razorpay",
            )
            for product, quantity, purchase_price in checked_lines:
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    purchase_price=purchase_price,
                )
    except ValueError as exc:
        return JsonResponse({"status": "error", "message": str(exc)}, status=400)

    request.session.pop("pending_razorpay_checkout", None)
    request.session["cart"] = {}
    return JsonResponse({
        "status": "success",
        "order_number": order.order_number,
        "redirect_url": reverse("order_detail", args=[order.order_number]),
    })


def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Your LifeCare account is ready.")
            return redirect("home")
    else:
        form = RegistrationForm()
    return render(request, "registration/register.html", {"form": form})


def download_source(request):
    """Create a clean source archive on demand, excluding local DB and cache files."""
    root = Path(settings.BASE_DIR)
    buffer = BytesIO()
    excluded_parts = {".venv", "__pycache__", ".git", "staticfiles", "media"}
    excluded_names = {"db.sqlite3", "lifecare-pharmacy-source.zip"}
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if not path.is_file() or path.name in excluded_names:
                continue
            if any(part in excluded_parts for part in path.relative_to(root).parts):
                continue
            archive.write(path, Path("lifecare-pharmacy") / path.relative_to(root))
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="lifecare-pharmacy-source.zip"'
    return response
