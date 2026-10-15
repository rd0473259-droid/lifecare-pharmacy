# LifeCare Pharmacy

**Your Health, Our Priority.**

LifeCare Pharmacy is a beginner-friendly Django + SQLite college demonstration of an online medicine ordering system. It includes user accounts, a searchable fictional product catalog, categories, a session-based cart, demo checkout, private order history, and a Django admin.



## Requirements

- Windows 10 or 11
- Python 3.10 or newer
- VS Code (recommended)
- Internet access for the first Django package installation

This project uses Django's built-in `User` and authentication, custom HTML5 templates and CSS, and a local SQLite database. It does not use Bootstrap, Tailwind, or JavaScript frameworks. Optional online checkout uses Razorpay; Cash on Delivery remains available without gateway credentials.

## Run in VS Code on Windows

1. Download and extract the complete project ZIP. You can download the ZIP from the **Download source ZIP** link in the website footer, or use the ZIP you received with this project.
2. Open the extracted `lifecare-pharmacy` folder in VS Code.
3. Open **Terminal → New Terminal** in VS Code. Confirm the terminal is in the folder containing `manage.py`.
4. Create and activate a virtual environment in PowerShell:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation for this terminal, run:

   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\.venv\Scripts\Activate.ps1
   ```

5. Install Django and the project dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

6. Create the local SQLite database tables:

   ```powershell
   python manage.py migrate
   ```

7. Add fictional categories and products. This command can be safely run again; it updates the existing sample records instead of duplicating them:

   ```powershell
   python manage.py seed_products
   ```

8. Create your own administrator account:

   ```powershell
   python manage.py createsuperuser
   ```

9. Start the website:

   ```powershell
   python manage.py runserver
   ```

To enable online payments, set the Razorpay test credentials before starting Django in PowerShell:

```powershell
$env:RAZORPAY_KEY_ID = "rzp_test_your_key_id"
$env:RAZORPAY_KEY_SECRET = "your_test_key_secret"
python manage.py runserver
```

Use Razorpay test-mode credentials and test payment details while developing. Online checkout lets the customer choose UPI or a debit/credit card, then opens Razorpay's hosted checkout to enter the UPI ID or card details. LifeCare does not collect or store payment credentials, and payment is verified server-side before an order is confirmed. Never commit gateway credentials or use this demonstration project to accept real customer payments.

10. Open the website at **http://127.0.0.1:8000/**. The Django administrator is at **http://127.0.0.1:8000/admin/**.

To stop the local server, press **Ctrl+C** in the terminal. To resume later, open the project in VS Code, activate `.venv`, and run `python manage.py runserver`.

## Demo features

- Register, login, and logout using Django's built-in authentication and password validators.
- Browse products and categories; search by product name.
- Add products, adjust quantities, and remove cart items. Cart data is stored in the visitor's Django session.
- Checkout behind login with Cash on Delivery and optional Razorpay-hosted online payment by UPI or debit/credit card. Online payment is available only when Razorpay credentials are configured; payment details are entered in Razorpay checkout and are not stored by LifeCare.
- Review orders for the signed-in user only. Changing an order number in the URL does not expose another account's order.
- Product and order administration at `/admin/`.
- A ZIP download endpoint at `/download-source/` creates a clean project archive and omits the local SQLite database and caches.
- Prescription-required product flags are visible. Prescription uploads and automated approvals are intentionally not included.

## Django admin

Run `python manage.py createsuperuser` to create an administrator, then visit **http://127.0.0.1:8000/admin/** and log in. The admin can manage categories, product prices, stock, availability, prescription-required flags, orders, and order status. Order item snapshots are read-only from the order admin.

## Tests and project structure

Run the automated tests with:

```powershell
python manage.py test
```

The tests cover the home/catalog pages, search, account registration and login, cart quantity checks, authenticated checkout, stock revalidation, Razorpay payment verification, purchase-price snapshots, order privacy, admin access, database constraints, and repeatable demo seeding.

```text
lifecare-pharmacy/
├── manage.py
├── requirements.txt
├── README.md
├── lifecare/                 # Django project settings and root URLs
├── pharmacy/                 # Models, forms, views, admin, tests, migrations
│   └── management/commands/  # seed_products management command
├── templates/                # Django HTML templates
└── static/
    ├── css/style.css
    └── products/             # Original local SVG illustrations
```

## Project safety notes

This is a local educational demo, not a production pharmacy service. The demo `SECRET_KEY` and `DEBUG=True` are for local development only. Do not deploy this project or use it with real customers, medicine inventory, prescriptions, or payments. A real service requires professional pharmacy oversight, licensing, legal and privacy compliance, secure deployment settings, and appropriate operational safeguards.
