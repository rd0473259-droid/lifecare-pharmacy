from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


PAYMENT_METHOD_CHOICES = [
    ("Cash on Delivery", "Cash on Delivery"),
    ("Razorpay", "Online payment (UPI or debit/credit card)"),
]


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class CheckoutForm(forms.Form):
    full_name = forms.CharField(max_length=150)
    contact_number = forms.RegexField(
        regex=r"^[0-9+\-\s()]{7,20}$",
        error_messages={"invalid": "Enter a valid contact number (7–20 characters)."},
    )
    address = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), max_length=500)
    city = forms.CharField(max_length=100)
    state = forms.CharField(max_length=100)
    pin_code = forms.RegexField(
        regex=r"^[0-9]{4,10}$",
        error_messages={"invalid": "Enter a valid PIN code using 4–10 digits."},
    )
    payment_method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES,
        initial="Cash on Delivery",
        label="Payment method",
        widget=forms.Select,
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), max_length=1000)

    def __init__(self, *args, razorpay_enabled=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.razorpay_enabled = razorpay_enabled
        if not razorpay_enabled:
            self.fields["payment_method"].choices = [
                ("Cash on Delivery", "Cash on Delivery"),
                ("Razorpay", "Online payment (Razorpay credentials required to complete payment)"),
            ]

    def clean_payment_method(self):
        payment_method = self.cleaned_data["payment_method"]
        if payment_method == "Razorpay" and not self.razorpay_enabled:
            raise forms.ValidationError(
                "Online payment is unavailable until Razorpay credentials are configured."
            )
        return payment_method
