from io import BytesIO
from decimal import Decimal
from unittest.mock import patch
from zipfile import ZipFile

import razorpay
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Category, Order, OrderItem, Product


class LifeCareStoreTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="First Aid", description="Test category")
        self.product = Product.objects.create(
            name="Demo Bandage",
            category=self.category,
            description="Fictional product for tests.",
            price=Decimal("25.00"),
            stock=5,
            is_available=True,
        )
        self.user = User.objects.create_user(username="student", password="StrongDemoPass123!")

    def test_homepage_renders_brand_and_featured_product(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LifeCare")
        self.assertContains(response, "Your Health, Our Priority.")
        self.assertContains(response, "Demo Bandage")

    def test_products_search_and_category_filter(self):
        response = self.client.get(reverse("product_list"), {"q": "bandage", "category": self.category.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Demo Bandage")
        response = self.client.get(reverse("product_list"), {"q": "no match"})
        self.assertNotContains(response, "Demo Bandage")

    def test_register_login_and_logout(self):
        response = self.client.post(reverse("register"), {
            "username": "newstudent",
            "email": "student@example.test",
            "password1": "AnotherStrongPass234!",
            "password2": "AnotherStrongPass234!",
        })
        self.assertRedirects(response, reverse("home"))
        self.assertTrue(User.objects.filter(username="newstudent").exists())
        self.client.post(reverse("logout"))
        login_response = self.client.post(reverse("login"), {
            "username": "newstudent",
            "password": "AnotherStrongPass234!",
        })
        self.assertRedirects(login_response, reverse("home"))

    def test_registration_accepts_the_replit_preview_origin_with_csrf(self):
        client = Client(enforce_csrf_checks=True)
        host = "lifecare-demo.replit.dev:3002"
        page = client.get(reverse("register"), secure=True, HTTP_HOST=host)
        self.assertEqual(page.status_code, 200)
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            reverse("register"),
            {
                "csrfmiddlewaretoken": csrf_token,
                "username": "previewstudent",
                "email": "previewstudent@example.test",
                "password1": "PreviewStrongPass234!",
                "password2": "PreviewStrongPass234!",
            },
            secure=True,
            HTTP_HOST=host,
            HTTP_ORIGIN="https://lifecare-demo.replit.dev:3002",
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="previewstudent").exists())

    def test_cart_add_update_and_remove(self):
        add = self.client.post(reverse("cart_add", args=[self.product.pk]), {"quantity": "2"})
        self.assertRedirects(add, reverse("cart"))
        self.assertEqual(self.client.session["cart"][str(self.product.pk)], 2)
        self.client.post(reverse("cart_update", args=[self.product.pk]), {"quantity": "3"})
        self.assertEqual(self.client.session["cart"][str(self.product.pk)], 3)
        self.client.post(reverse("cart_remove", args=[self.product.pk]))
        self.assertNotIn(str(self.product.pk), self.client.session["cart"])

    def test_cart_rejects_quantity_above_stock(self):
        response = self.client.post(reverse("cart_add", args=[self.product.pk]), {"quantity": "6"})
        self.assertRedirects(response, reverse("cart"))
        self.assertNotIn(str(self.product.pk), self.client.session.get("cart", {}))

    def test_cart_shows_product_that_became_unavailable(self):
        self.client.post(reverse("cart_add", args=[self.product.pk]), {"quantity": "1"})
        self.product.is_available = False
        self.product.save()
        response = self.client.get(reverse("cart"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Demo Bandage")
        self.assertContains(response, "Please remove unavailable items")

    def test_checkout_requires_login(self):
        response = self.client.get(reverse("checkout"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('checkout')}")

    def test_checkout_allows_selecting_razorpay_without_gateway_credentials(self):
        self.client.force_login(self.user)
        self.client.post(reverse("cart_add", args=[self.product.pk]), {"quantity": "1"})

        response = self.client.get(reverse("checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cash on Delivery")
        self.assertContains(response, "Online payment (Razorpay credentials required to complete payment)")
        self.assertContains(response, 'value="Razorpay"')
        self.assertNotContains(response, 'value="Razorpay" disabled')
        self.assertContains(response, "Online payment can be selected, but requires Razorpay credentials to complete.")

    def test_checkout_rejects_razorpay_without_gateway_credentials(self):
        self.client.force_login(self.user)
        self.client.post(reverse("cart_add", args=[self.product.pk]), {"quantity": "1"})

        response = self.client.post(reverse("checkout"), {
            "full_name": "Student Example",
            "contact_number": "9876543210",
            "address": "1 College Road",
            "city": "Pune",
            "state": "Maharashtra",
            "pin_code": "411001",
            "notes": "",
            "payment_method": "Razorpay",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Online payment is unavailable")
        self.assertNotContains(response, 'value="Razorpay" disabled')
        self.assertFalse(Order.objects.exists())

    def test_checkout_saves_price_and_decrements_stock(self):
        self.client.force_login(self.user)
        self.client.post(reverse("cart_add", args=[self.product.pk]), {"quantity": "2"})
        response = self.client.post(reverse("checkout"), {
            "full_name": "Student Example",
            "contact_number": "9876543210",
            "address": "1 College Road",
            "city": "Pune",
            "state": "Maharashtra",
            "pin_code": "411001",
            "notes": "",
            "payment_method": "Cash on Delivery",
        })
        order = Order.objects.get(user=self.user)
        self.assertRedirects(response, reverse("order_detail", args=[order.order_number]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
        self.assertEqual(order.total, Decimal("50.00"))
        self.assertEqual(order.items.get().purchase_price, Decimal("25.00"))
        self.assertEqual(self.client.session["cart"], {})
        self.assertEqual(order.payment_method, "Cash on Delivery")

    def test_checkout_rechecks_stock(self):
        self.client.force_login(self.user)
        self.client.post(reverse("cart_add", args=[self.product.pk]), {"quantity": "3"})
        self.product.stock = 1
        self.product.save()
        response = self.client.post(reverse("checkout"), {
            "full_name": "Student Example",
            "contact_number": "9876543210",
            "address": "1 College Road",
            "city": "Pune",
            "state": "Maharashtra",
            "pin_code": "411001",
            "notes": "",
            "payment_method": "Cash on Delivery",
        })
        self.assertRedirects(response, reverse("cart"))
        self.assertFalse(Order.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)

    @override_settings(RAZORPAY_KEY_ID="rzp_test_123", RAZORPAY_KEY_SECRET="secret", RAZORPAY_ENABLED=True)
    @patch("razorpay.Client")
    def test_checkout_creates_razorpay_order_when_selected(self, mock_razorpay_client):
        mock_razorpay_client.return_value.order.create.return_value = {"id": "order_razorpay_123"}
        self.client.force_login(self.user)
        self.client.post(reverse("cart_add", args=[self.product.pk]), {"quantity": "2"})

        response = self.client.post(reverse("checkout"), {
            "full_name": "Student Example",
            "contact_number": "9876543210",
            "address": "1 College Road",
            "city": "Pune",
            "state": "Maharashtra",
            "pin_code": "411001",
            "notes": "",
            "payment_method": "Razorpay",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "checkout.razorpay.com")
        self.assertContains(response, "order_razorpay_123")
        self.assertContains(response, "Enter your UPI ID in secure checkout")
        self.assertContains(response, "Enter your card details in secure checkout")
        self.assertContains(response, 'instruments: [{ method }]')
        self.assertEqual(
            self.client.session["pending_razorpay_checkout"]["razorpay_order_id"],
            "order_razorpay_123",
        )

    @override_settings(RAZORPAY_KEY_ID="rzp_test_123", RAZORPAY_KEY_SECRET="secret")
    @patch("razorpay.Client")
    def test_checkout_shows_actionable_error_when_razorpay_rejects_order(self, mock_razorpay_client):
        mock_razorpay_client.return_value.order.create.side_effect = razorpay.errors.BadRequestError(
            "invalid credentials"
        )
        self.client.force_login(self.user)
        self.client.post(reverse("cart_add", args=[self.product.pk]), {"quantity": "1"})

        response = self.client.post(reverse("checkout"), {
            "full_name": "Student Example",
            "contact_number": "9876543210",
            "address": "1 College Road",
            "city": "Pune",
            "state": "Maharashtra",
            "pin_code": "411001",
            "notes": "",
            "payment_method": "Razorpay",
        })

        self.assertRedirects(response, reverse("checkout"), fetch_redirect_response=False)
        follow_up = self.client.get(response.url)
        self.assertContains(follow_up, "Check that your active test-mode key ID and secret match.")
        self.assertFalse(Order.objects.exists())

    @override_settings(RAZORPAY_KEY_ID="rzp_test_123", RAZORPAY_KEY_SECRET="secret")
    @patch("razorpay.Client")
    def test_razorpay_verification_creates_order_only_for_captured_checkout_payment(self, mock_razorpay_client):
        gateway = mock_razorpay_client.return_value
        gateway.order.create.return_value = {"id": "order_razorpay_123"}
        gateway.payment.fetch.return_value = {
            "order_id": "order_razorpay_123",
            "amount": 5000,
            "currency": "INR",
            "status": "captured",
        }
        self.client.force_login(self.user)
        self.client.post(reverse("cart_add", args=[self.product.pk]), {"quantity": "2"})
        self.client.post(reverse("checkout"), {
            "full_name": "Student Example",
            "contact_number": "9876543210",
            "address": "1 College Road",
            "city": "Pune",
            "state": "Maharashtra",
            "pin_code": "411001",
            "notes": "",
            "payment_method": "Razorpay",
        })

        response = self.client.post(reverse("razorpay_verify"), {
            "razorpay_payment_id": "pay_123",
            "razorpay_order_id": "order_razorpay_123",
            "razorpay_signature": "valid_signature",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.total, Decimal("50.00"))
        self.assertEqual(order.payment_method, "Razorpay")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
        self.assertEqual(self.client.session["cart"], {})

    @override_settings(RAZORPAY_KEY_ID="rzp_test_123", RAZORPAY_KEY_SECRET="secret")
    @patch("razorpay.Client")
    def test_razorpay_verification_rejects_another_order_id(self, mock_razorpay_client):
        mock_razorpay_client.return_value.order.create.return_value = {"id": "order_razorpay_123"}
        self.client.force_login(self.user)
        self.client.post(reverse("cart_add", args=[self.product.pk]), {"quantity": "1"})
        self.client.post(reverse("checkout"), {
            "full_name": "Student Example",
            "contact_number": "9876543210",
            "address": "1 College Road",
            "city": "Pune",
            "state": "Maharashtra",
            "pin_code": "411001",
            "notes": "",
            "payment_method": "Razorpay",
        })

        response = self.client.post(reverse("razorpay_verify"), {
            "razorpay_payment_id": "pay_123",
            "razorpay_order_id": "order_someone_else",
            "razorpay_signature": "signature",
        })

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())
        mock_razorpay_client.return_value.utility.verify_payment_signature.assert_not_called()

    @override_settings(RAZORPAY_KEY_ID="rzp_test_123", RAZORPAY_KEY_SECRET="secret")
    @patch("razorpay.Client")
    def test_razorpay_verification_reports_gateway_lookup_errors_separately(self, mock_razorpay_client):
        gateway = mock_razorpay_client.return_value
        gateway.order.create.return_value = {"id": "order_razorpay_123"}
        gateway.payment.fetch.side_effect = razorpay.errors.ServerError("temporary failure")
        self.client.force_login(self.user)
        self.client.post(reverse("cart_add", args=[self.product.pk]), {"quantity": "1"})
        self.client.post(reverse("checkout"), {
            "full_name": "Student Example",
            "contact_number": "9876543210",
            "address": "1 College Road",
            "city": "Pune",
            "state": "Maharashtra",
            "pin_code": "411001",
            "notes": "",
            "payment_method": "Razorpay",
        })

        response = self.client.post(reverse("razorpay_verify"), {
            "razorpay_payment_id": "pay_123",
            "razorpay_order_id": "order_razorpay_123",
            "razorpay_signature": "valid_signature",
        })

        self.assertEqual(response.status_code, 502)
        self.assertIn("could not confirm the payment status", response.json()["message"])
        self.assertFalse(Order.objects.exists())

    def test_user_cannot_view_another_users_order(self):
        other = User.objects.create_user(username="other", password="StrongDemoPass123!")
        order = Order.objects.create(
            user=other,
            full_name="Other User",
            contact_number="9876543210",
            address="Private address",
            city="Pune",
            state="Maharashtra",
            pin_code="411001",
            total=Decimal("25.00"),
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("order_detail", args=[order.order_number]))
        self.assertEqual(response.status_code, 404)

    def test_source_download_is_a_zip_and_omits_local_database(self):
        response = self.client.get(reverse("download_source"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("lifecare-pharmacy-source.zip", response["Content-Disposition"])
        with ZipFile(BytesIO(response.content)) as archive:
            names = archive.namelist()
            self.assertIn("lifecare-pharmacy/manage.py", names)
            self.assertIn("lifecare-pharmacy/pharmacy/migrations/0001_initial.py", names)
            self.assertNotIn("lifecare-pharmacy/db.sqlite3", names)

    def test_order_history_only_shows_current_users_orders(self):
        other = User.objects.create_user(username="other", password="StrongDemoPass123!")
        Order.objects.create(
            user=other, full_name="Other User", contact_number="9876543210",
            address="Private address", city="Pune", state="Maharashtra",
            pin_code="411001", total=Decimal("25.00"),
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("order_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Private address")

    def test_product_admin_is_available(self):
        self.client.force_login(User.objects.create_superuser("admin", "admin@example.test", "AdminPass123!"))
        response = self.client.get("/admin/pharmacy/product/")
        self.assertEqual(response.status_code, 200)


class ModelValidationTests(TestCase):
    def test_product_price_database_constraint_rejects_negative_value(self):
        category = Category.objects.create(name="Test")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Product.objects.create(
                    name="Invalid price", category=category, description="Test",
                    price=Decimal("-1.00"), stock=1,
                )

    def test_seed_command_is_repeatable(self):
        from django.core.management import call_command
        call_command("seed_products", verbosity=0)
        first_product_count = Product.objects.count()
        call_command("seed_products", verbosity=0)
        self.assertEqual(Product.objects.count(), first_product_count)
