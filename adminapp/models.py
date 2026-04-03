from datetime import date, timedelta
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from django.core.exceptions import ValidationError
# -------- Category --------
class Category(models.Model):
    name = models.CharField(max_length=150) # helps react dev to show only required fees related to a category
  
    def __str__(self):
        return self.name

class Client(AbstractUser):
    business_name = models.CharField(max_length=200, null=True, blank=True, unique=True)
    contact_number = models.PositiveIntegerField(null=True, blank=True, unique=True)
    email = models.EmailField(unique=True, null=True, blank=True)  # ✅ unique email field
    address = models.CharField(max_length=255, null=True, blank=True)
    payment_method = models.CharField(
        max_length=255,
        choices=[('Cash', 'Cash'), ('Upi', 'Upi'), ('Card', 'Card')],
        null=True,
        blank=True
    )
    category = models.ForeignKey(
        'Category',
        on_delete=models.CASCADE,
        related_name='clients',
        null=True,
        blank=True
    )

    # -------- Subscription details --------
    subscription_start = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    subscription_end = models.DateTimeField(null=True, blank=True)
    subscription_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=5000.00,
        help_text="Subscription amount in INR"
    )
    subscription_currency = models.CharField(
        max_length=10,
        default='INR',
        help_text="Currency code for the subscription (e.g., INR, USD, AED)"
    )
    currency_emoji = models.CharField(  
        max_length=5,
        null=True,
        blank=True,
        help_text="Emoji representation of the currency (e.g., ₹, 💵, 💶)"
    )
    is_active = models.BooleanField(default=True)

    # -------- Save Method --------
    def save(self, *args, **kwargs):
        if not self.subscription_start:
            self.subscription_start = timezone.now()
        if not self.subscription_end:
            self.subscription_end = self.subscription_start + timedelta(days=365)
        if not self.subscription_amount:
            self.subscription_amount = 5000.00
        self.is_active = self.subscription_end >= timezone.now()
        super().save(*args, **kwargs)

    # -------- Remaining Days --------
    @property
    def remaining_days(self):
        if self.subscription_end:
            remaining = (self.subscription_end - timezone.now()).days
            return max(remaining, 0)
        return 0

    # -------- Expiry Message --------
   
    def expiry_message(self):
        days_left = self.remaining_days
        if days_left < 0:
            self.is_active = False
            self.save(update_fields=["is_active"])
            return "Your subscription has expired."
        elif days_left == 0:
            return "Your subscription expires today!"
        elif days_left <= 5:
            return f"Your subscription expires in {days_left} days."
        return None

    # -------- Renewal --------
    def renew_subscription(self, duration_days=365, amount=5000.00, currency='INR'):
        self.subscription_start = timezone.now()
        self.subscription_end = self.subscription_start + timedelta(days=duration_days)
        self.subscription_amount = amount
        self.subscription_currency = currency
        self.is_active = True
        self.save()

    def __str__(self):
        return self.business_name or self.username

# -------- Batch --------
class Batch(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='batches',null=True,blank=True)
    name = models.CharField(max_length=100)  # e.g. Morning Batch, Evening Batch
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    days = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. Mon-Fri")

    def __str__(self):
        return f"{self.name} ({self.client.business_name})"




class Subscription(models.Model):
    client = models.ForeignKey('Client', on_delete=models.CASCADE)
    name = models.CharField(max_length=200, null=True, blank=True)
    admission_fee = models.PositiveIntegerField(default=0)
    # [{"name":"Tuition","value":2000,"recurring":True}, ...]
    custom_fees = models.JSONField(default=list, blank=True)
    duration_days = models.PositiveIntegerField(default=30)  # determines cycle length in days

    def __str__(self):
        return self.name or "Subscription"


class Member(models.Model):
    client = models.ForeignKey('Client', on_delete=models.CASCADE, related_name='members')

    full_name = models.CharField(max_length=255)
    date_of_birth = models.DateField(null=True, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    place = models.CharField(max_length=202, null=True, blank=True)
    gender = models.CharField(
        max_length=1,
        choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')],
        null=True,
        blank=True
    )
    nationality = models.CharField(max_length=100, null=True, blank=True)

    # Contact Details
    contact_number = models.CharField(max_length=20, null=True, blank=True)
    whatsapp_number = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    parent_name = models.CharField(max_length=255, null=True, blank=True)

    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name='members')

    outstanding_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # IMPORTANT: use DateTimeField so minutes testing works properly.
    recurring_date = models.DateTimeField(null=True, blank=True)  # next scheduled billing datetime
    is_active = models.BooleanField(default=True)
    batch_group = models.ForeignKey(
        Batch, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='members'
    )

    created_at = models.DateTimeField(auto_now_add=True)  # record creation time

    def __str__(self):
        return self.full_name

class Bill(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='bills')
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT)

    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    due_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    bill_date = models.DateTimeField(default=timezone.now)
    recurring_date = models.DateTimeField(null=True, blank=True)
    is_recurring = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # Ensure Decimal arithmetic
        self.total_amount = Decimal(self.total_amount)
        self.paid_amount = Decimal(self.paid_amount)

        member_outstanding = Decimal(self.member.outstanding_fee or 0)

        self.due_amount = (self.total_amount - self.paid_amount) + member_outstanding
        super().save(*args, **kwargs)


class Payment(models.Model):
    PAYMENT_METHODS = [
        ('CASH', 'Cash'),
        ('CARD', 'Card'),
    ]

    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS)
    partial_payments=models.JSONField(default=list, blank=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    remarks = models.TextField(null=True,blank=True)

    def save(self, *args, **kwargs):
        self.amount = Decimal(self.amount)
        super().save(*args, **kwargs)

        # Update the related bill
        bill = self.bill
        if self.amount<=bill.due_amount:  # 2600<=2500
            bill.paid_amount += self.amount
        else:
            raise ValidationError("Payment cannot exceed bill due amount")
        bill.save()

    def __str__(self):
        return f"{self.amount} via {self.payment_method} for {self.bill}"


class Attendance(models.Model):
    client = models.ForeignKey(
        'Client', 
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    batch = models.ForeignKey(
        'Batch',
        on_delete=models.CASCADE,
        related_name='attendances',
    null=True)
    member = models.ForeignKey(
        'Member',
        on_delete=models.CASCADE,
        related_name='attendances'
    )

    # Attendance details
    date = models.DateField(default=timezone.now)
    present = models.BooleanField(default=False)

 
    # Notes or remarks (optional)
    remarks = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ('batch', 'member', 'date')  # Prevent duplicate attendance for same day

    def __str__(self):
        return f"{self.member.full_name} - {self.batch.name} on {self.date} ({'Present' if self.present else 'Absent'})"
   


