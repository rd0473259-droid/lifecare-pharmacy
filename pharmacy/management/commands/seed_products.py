from decimal import Decimal

from django.core.management.base import BaseCommand

from pharmacy.models import Category, Product


class Command(BaseCommand):
    help = "Create or update fictional LifeCare Pharmacy demonstration categories and products."

    categories = [
        ("Tablets and Capsules", "Everyday over-the-counter demonstration items."),
        ("Vitamins and Supplements", "Fictional wellness products for this project demo."),
        ("First Aid", "Basic first-aid demonstration supplies."),
        ("Personal Care", "Everyday personal care essentials."),
        ("Baby Care", "Gentle fictional baby-care essentials."),
        ("Healthcare Devices", "Home health monitoring demonstration devices."),
    ]
    products = [
        ("DailyCare Paracetamol 500 mg", "Tablets and Capsules", "A fictional sample product for demonstrating medicine catalog and cart flows.", "35.00", 48, True, "products/tablets.svg"),
        ("CalmRelief Antacid Tablets", "Tablets and Capsules", "A fictional sample antacid listing. Not intended for actual use.", "62.00", 32, True, "products/tablets.svg"),
        ("Sunrise Vitamin C 500 mg", "Vitamins and Supplements", "A fictional vitamin supplement sample for this college project.", "120.00", 25, False, "products/vitamins.svg"),
        ("WellDay Multivitamin", "Vitamins and Supplements", "A fictional daily multivitamin product demonstration.", "210.00", 20, False, "products/vitamins.svg"),
        ("QuickAid Bandage Pack", "First Aid", "Fictional assorted adhesive bandage pack for catalog demonstration.", "55.00", 40, False, "products/first-aid.svg"),
        ("CleanCare Antiseptic Solution", "First Aid", "Fictional antiseptic solution listing. Demonstration only.", "89.00", 18, False, "products/first-aid.svg"),
        ("SoftTouch Hand Wash", "Personal Care", "Fictional gentle hand wash sample item.", "99.00", 28, False, "products/personal-care.svg"),
        ("PureShield Sanitizer", "Personal Care", "Fictional sanitizer listing for the LifeCare demo catalog.", "75.00", 35, False, "products/personal-care.svg"),
        ("LittleNest Baby Lotion", "Baby Care", "Fictional baby-care lotion sample product.", "165.00", 14, False, "products/baby-care.svg"),
        ("TinySteps Baby Wipes", "Baby Care", "Fictional soft baby wipes pack for demonstration.", "110.00", 24, False, "products/baby-care.svg"),
        ("HomeCheck Thermometer", "Healthcare Devices", "A fictional digital thermometer listing for the demo store.", "299.00", 12, False, "products/devices.svg"),
        ("PulsePoint Oximeter", "Healthcare Devices", "Fictional home-health device listing. Product details are for demonstration only.", "899.00", 8, False, "products/devices.svg"),
    ]

    def handle(self, *args, **options):
        category_map = {}
        for name, description in self.categories:
            category, created = Category.objects.update_or_create(
                name=name, defaults={"description": description}
            )
            category_map[name] = category
        count = 0
        for name, category, description, price, stock, prescription, image in self.products:
            Product.objects.update_or_create(
                name=name,
                defaults={
                    "category": category_map[category],
                    "description": description,
                    "price": Decimal(price),
                    "stock": stock,
                    "is_available": True,
                    "prescription_required": prescription,
                    "image": image,
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(category_map)} categories and {count} fictional demo products (safe to run again)."
        ))
