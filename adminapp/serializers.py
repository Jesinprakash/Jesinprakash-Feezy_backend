import random,pytz
import string
import requests
from datetime import date, timedelta,datetime,time
from django.utils import timezone
from django.db.models import Sum
from rest_framework import serializers
from adminapp.models import Client,Category,Batch,Subscription,Member,Payment,Bill,Attendance
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from adminapp.config import IS_TESTING
from adminapp.utils import send_email_async



Client = get_user_model()


class ClientCreateSerializer(serializers.ModelSerializer):
    email = serializers.EmailField()
    password = serializers.CharField(read_only=True)
    country_code = serializers.CharField(write_only=True, required=False)  # ✅ for currency API
    business_name = serializers.CharField()
    address = serializers.CharField()
    class Meta:
        model = Client
        fields = [
            'username',
            'email',
            'password',
            'business_name',
            'contact_number',
            'address',
            'payment_method',
            'country_code',            # used for currency lookup
            'subscription_amount',
            'subscription_currency',   # ✅ updated to match your model
            'subscription_start',
            'subscription_end',
            'is_active',
            'category',
            'currency_emoji',          # ✅ allow frontend to send emoji
        ]
        read_only_fields = [
            'password',
            'subscription_amount',
            'subscription_currency',
            'subscription_start',
            'subscription_end',
            'is_active',
        ]

    def create(self, validated_data):
        # 🔹 Extract and remove country code (keep currency_emoji)
        country_code = validated_data.pop('country_code', 'IN')

        # 🔹 Generate random password (10 characters)
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))

        # 🔹 Create client instance with provided data (includes emoji)
        client = Client(**validated_data)
        client.set_password(password)

        # --- Subscription setup ---
        # client.subscription_start = date.today()
        client.subscription_start = timezone.now()
        client.subscription_end = client.subscription_start + timedelta(days=365)
        client.subscription_amount = 5000.00  # base price
        client.subscription_currency = "INR"  # default

        # --- Fetch currency from API (based on country_code) ---
        try:
            api_url = f"https://restcountries.com/v3.1/alpha/{country_code}"
            response = requests.get(api_url, timeout=5)
            if response.status_code == 200:
                data = response.json()[0]
                currency_code = list(data["currencies"].keys())[0]
                client.subscription_currency = currency_code
            else:
                client.subscription_currency = "INR"
        except Exception as e:
            print("Currency fetch failed:", e)
            client.subscription_currency = "INR"

        # 🔹 Save the client (includes manually entered emoji)
        client.save()

        # Attach generated password for API response
        client.generated_password = password

        # --- Send email with credentials ---
        subject = "Your Account Credentials"
        message = (
            f"Hello {client.username},\n\n"
            f"Your account has been created successfully.\n\n"
            f"Here are your login details:\n"
            f"Username: {client.username}\n"
            f"Password: {password}\n\n"
            f"Subscription: 1 Year\n"
            f"Valid Till: {client.subscription_end}\n\n"
            f"Please change your password after your first login.\n\n"
            f"Regards,\nAdmin Team"
        )
        send_email_async(subject, message, [client.email])
        return client

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if hasattr(instance, 'generated_password'):
            data['generated_password'] = instance.generated_password
        return data
        
# -------- Login Serializer --------
class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True) 


# -------- Category Serializer --------
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = "__all__"
        read_only_fields = ["id"]

class PasswordUpdateSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = self.context['request'].user

        # Check old password
        if not user.check_password(data['old_password']):
            raise serializers.ValidationError({"old_password": "Incorrect old password"})

        # Check if new passwords match
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match"})

        # Optional: Add password strength checks
        if len(data['new_password']) < 6:
            raise serializers.ValidationError({"new_password": "Password must be at least 6 characters long"})

        return data

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not Client.objects.filter(email=value).exists():
            raise serializers.ValidationError("No user found with this email.")
        return value

    def save(self):
        email = self.validated_data['email']
        user = Client.objects.get(email=email)

        # --- Generate a random 10-character password ---
        new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        
        # --- Set the new password (hashed automatically) ---
        user.set_password(new_password)
        user.save()

        # --- Send email to the user ---
        subject = "Your New Password"
        message = f"Hello {user.username},\n\nYour new password is: {new_password}\n\nPlease log in and change it immediately."
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient_list = [email]
        send_mail(subject, message, from_email, recipient_list, fail_silently=False)
    
class BatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Batch
        fields = ['id','client','name','start_time','end_time','days']




KOLKATA = pytz.timezone("Asia/Kolkata")


def calculate_fees(subscription, include_joining=False):
    total = Decimal("0.00")
    if include_joining:
        total += Decimal(subscription.admission_fee or 0) 
        for fee in subscription.custom_fees:
            if not fee.get("recurring", False): 
                total += Decimal(fee.get("value", 0))
    for fee in subscription.custom_fees:
        if fee.get("recurring", False):
            total += Decimal(fee.get("value", 0))
    return total




class MemberSerializer(serializers.ModelSerializer):

# WRITE (accept ID)
    subscription = serializers.PrimaryKeyRelatedField(
        queryset=Subscription.objects.all()
    )
    batch_group = serializers.PrimaryKeyRelatedField(
        queryset=Batch.objects.all(),
        required=False,
        allow_null=True
    )
    
    # READ (show name)
    subscription_name = serializers.CharField(
        source='subscription.name',
        read_only=True
    )
    batch_name = serializers.CharField(
        source='batch_group.name',
        read_only=True
    )
       
    fmt = "%d-%m-%Y %H:%M" if IS_TESTING else "%d-%m-%Y"
    created_at = serializers.DateTimeField(
        format=fmt ,
        read_only=True
    )
    
    recurring_date = serializers.DateTimeField(
        input_formats=[fmt],
        format=fmt,
    )

    due_amount = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    last_paid_date = serializers.SerializerMethodField()

    
    
    class Meta:
        model = Member
        fields = "__all__"
        read_only_fields = ['client']

    def get_due_amount(self, obj):
        return obj.bills.aggregate(
            total=Sum("due_amount")
        )["total"] or 0

    def get_paid_amount(self, obj):
        return obj.bills.aggregate(
            total=Sum("paid_amount") 
        )["total"] or 0   

    def get_last_paid_date(self, obj):
        last_payment = None
        for bill in obj.bills.all():
            payment = bill.payments.order_by('-payment_date').first()
            if payment and (last_payment is None or payment.payment_date > last_payment):
                fmt = "%d-%m-%Y %H:%M" if IS_TESTING else "%d-%m-%Y"
                last_payment = payment.payment_date.strftime(fmt)
        return last_payment       
      
    def create(self, validated_data):

        member = Member.objects.create(**validated_data)

        if not member.recurring_date:
            return member
        
        if not member.is_active:
            return member

        # Convert to DATE ONLY
        RD = member.recurring_date.astimezone(KOLKATA)
        CD = member.created_at.astimezone(KOLKATA)

        if IS_TESTING:
            # In testing, we care about minutes
            RD = RD.replace(second=0, microsecond=0)
            CD = CD.replace(second=0, microsecond=0)
        else:
            # In production, we ONLY care about the day
            RD = RD.date()
            CD = CD.date()
        
        

        print("DEBUG-RD-date:", RD)
        print("DEBUG-CD-date:", CD)

        subscription = member.subscription
        duration_days = getattr(subscription, "duration_days", 30)

        # ---------------------------------------------------
        # NO BILL RULES
        # ---------------------------------------------------

        # 1️⃣ RECURRING DATE IN THE FUTURE → NO BILL
        if RD > CD:
            return member  # DO NOT CREATE FIRST BILL

        # 2️⃣ RECURRING DATE IN THE PAST → NO BILL
        if RD < CD:
            return member  # DO NOT CREATE FIRST BILL

        # 3️⃣ RECURRING DATE == CREATED DATE → ONLY CASE TO CREATE BILL
        bill_date = member.recurring_date.astimezone(KOLKATA)
        include_joining = True

        total = calculate_fees(subscription, include_joining=True)

        Bill.objects.create(
            member=member,
            subscription=subscription,
            total_amount=total,
            due_amount=total,
            bill_date=bill_date,
            recurring_date=member.recurring_date,
            is_recurring=False,  # first bill
        )

        return member
    
   







    
class BillFeeSerializer(serializers.ModelSerializer):
    fees_status = serializers.SerializerMethodField()
    fmt = "%d-%m-%Y %H:%M" if IS_TESTING else "%d-%m-%Y"
    bill_date = serializers.DateTimeField(format=fmt,read_only=True)

    class Meta:
        model = Bill
        fields = ['id', 'bill_date', 'due_amount', 'fees_status']

    def get_fees_status(self, bill):
        subscription = bill.subscription
        member = bill.member
        status = []

        # collect paid fee names
        paid_fees = set()

        for payment in bill.payments.all():
            for p in payment.partial_payments:
                paid_fees.add(p.get("fee_name"))

         # 1️⃣ Outstanding Fee (MEMBER LEVEL)
        if member.outstanding_fee and member.outstanding_fee > 0:
            status.append({
                "name": "Outstanding Fee",
                "value": member.outstanding_fee,
                "is_paid": "Outstanding Fee" in paid_fees
            })


        # Admission Fee
        if not bill.is_recurring and subscription.admission_fee > 0:
            status.append({
                "name": "Admission Fee",
                "value": subscription.admission_fee,
                "is_paid": "Admission Fee" in paid_fees
            })

        # Custom Fees
        for fee in subscription.custom_fees:
            fee_name = fee.get("field")
            recurring = fee.get("recurring", False)

            if recurring or (not recurring and not bill.is_recurring):
                status.append({
                    "name": fee_name,
                    "value": Decimal(fee.get("value", 0)),
                    "is_paid": fee_name in paid_fees
                })

        return status
    

class FeeRecieptSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source='member.full_name')
    
    email = serializers.CharField(source='member.email')
    
    contact_number = serializers.CharField(source='member.contact_number')
    
    receipt_id = serializers.SerializerMethodField()
    
    payment_mode = serializers.SerializerMethodField()
    
    fmt = "%d-%m-%Y %H:%M" if IS_TESTING else "%d-%m-%Y"
    bill_date = serializers.DateTimeField(format=fmt,read_only=True)
    
    class Meta:
        model = Bill
        fields = [
            'id','member_name','email','contact_number','due_amount','paid_amount','receipt_id','payment_mode','bill_date'
        ]
       
    
    def get_receipt_id(self,obj):
        return ''.join(random.choices(string.digits+string.ascii_lowercase,k=10))
    
    def get_payment_mode(self, obj):
        latest_payment = obj.payments.order_by('-id').first()
        return latest_payment.payment_method if latest_payment else None




class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta: 
        model = Subscription
        fields = '__all__'
        read_only_fields = ['client']


class BillSerializer(serializers.ModelSerializer):
    fmt = "%d-%m-%Y %H:%M" if IS_TESTING else "%d-%m-%Y"
    bill_date = serializers.DateTimeField(format=fmt,read_only=True)
    recurring_date = serializers.DateTimeField(format=fmt,read_only=True)
    total_amount = serializers.SerializerMethodField()
  
    class Meta:
        model = Bill
        # optionally, you can exclude fields or set read_only_fields
        fields = '__all__'
        read_only_fields = ('paid_amount', 'due_amount', 'bill_date','recurring_date','total_amount')

    def get_total_amount(self,obj):
        total_amount = obj.total_amount  + obj.member.outstanding_fee
        return total_amount

    # Optionally, if you want to show member details nested:
    # member = serializers.StringRelatedField(read_only=True)
    # subscription = SubscriptionSerializer(read_only=True)
 



class PaymentSerializer(serializers.ModelSerializer):
    fmt = "%d-%m-%Y %H:%M" if IS_TESTING else "%d-%m-%Y"
    payment_date = serializers.DateTimeField(format=fmt,read_only=True)
   
    class Meta:
        model = Payment
        fields = ['id','bill','amount','payment_method','payment_date','partial_payments','remarks']
        read_only_fields = ['bill']
        
   
    
    
class MemberProfileSerializer(serializers.ModelSerializer):
    total_paid_amount = serializers.SerializerMethodField()
    total_due_amount = serializers.SerializerMethodField()
    next_renewal_date = serializers.SerializerMethodField()

    subscription_name = serializers.CharField(source='subscription.name',read_only=True)
    # subscription_amount = serializers.CharField(source='outstanding_fee',read_only=True)
    subscription_amount = serializers.SerializerMethodField()
    remaining_days = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()
    
    class Meta:
        model = Member
        fields = [
            'id',
            'full_name',
            'contact_number',
            'email',
            'total_paid_amount',
            'total_due_amount',
            'created_at',
            'next_renewal_date',
            'subscription_name',
            'subscription_amount',
            'remaining_days',
            'is_active'
        ]
        read_only_fields=[
            'created_at'
        ]

    def get_total_paid_amount(self, obj):
        result = obj.bills.aggregate(
            total_paid=Sum('paid_amount')
        )['total_paid']
        return result or 0
    
    def get_total_due_amount(self, obj):
        result = obj.bills.aggregate(
            total_due=Sum('due_amount')
        )['total_due']
        return result or 0
    
    def get_created_at(self, obj):
        dt = obj.created_at.astimezone(KOLKATA).replace(second=0, microsecond=0)
        fmt = "%d-%m-%Y %H:%M" if IS_TESTING else "%d-%m-%Y"
        return dt.strftime(fmt)

    
    def get_next_renewal_date(self, obj):
        last_bill = obj.bills.order_by("-bill_date").first()
        if not last_bill:
            return None

        duration = getattr(obj.subscription, "duration_days", 30)
        step = timedelta(minutes=duration) if IS_TESTING else timedelta(days=duration)

        last_dt = last_bill.bill_date.astimezone(KOLKATA).replace(second=0, microsecond=0)
        next_dt = (last_dt + step).astimezone(KOLKATA)
        fmt = "%d-%m-%Y %H:%M" if IS_TESTING else "%d-%m-%Y"
        return next_dt.strftime(fmt)
    
    
    def get_remaining_days(self, obj):
        last_bill = obj.bills.order_by("-bill_date").first()
        if not last_bill:
            return None

        duration = getattr(obj.subscription, "duration_days", 30)
        step = timedelta(minutes=duration) if IS_TESTING else timedelta(days=duration)

        last_dt = last_bill.bill_date.astimezone(KOLKATA).replace(second=0, microsecond=0)
        next_dt = (last_dt + step).astimezone(KOLKATA)
        now_ist = timezone.now().astimezone(KOLKATA).replace(second=0, microsecond=0)

        if IS_TESTING:
            diff_minutes = int((next_dt - now_ist).total_seconds() // 60)
            return max(diff_minutes, 0)
        else:
            diff_days = (next_dt.date() - now_ist.date()).days
            return max(diff_days, 0)
        
    def get_subscription_amount(self, obj):
        subscription = obj.subscription
        admission = Decimal(subscription.admission_fee or 0)

        # Sum all custom fee values
        custom_total = sum(
            Decimal(fee.get("value", 0)) for fee in subscription.custom_fees
        )

        total = admission + custom_total
        return total



    

class AttendanceBulkSerializer(serializers.Serializer):
    batch = serializers.PrimaryKeyRelatedField(queryset=Batch.objects.all())
    member = serializers.PrimaryKeyRelatedField(queryset=Member.objects.all())
    date = serializers.DateField()
    present = serializers.BooleanField()
    remarks = serializers.CharField(required=False, allow_blank=True)



class BatchMemberSerializer(serializers.ModelSerializer):
    subscription_name = serializers.CharField(source='subscription.name', read_only=True)
    total_paid = serializers.SerializerMethodField()
    pending_amount = serializers.SerializerMethodField()
    last_paid_date = serializers.SerializerMethodField()
    class Meta:
        model = Member
        fields = [
            'id',
            'full_name',
            'contact_number',
            'email',
            'is_active',
            'subscription_name',
            'batch_group',
            'total_paid',
            'pending_amount',
            'last_paid_date'

        ]

    def get_total_paid(self, obj):
            total = Decimal(0)

            for bill in obj.bills.all():
                for payment in bill.payments.all():
                    total += payment.amount

            return total

    def get_pending_amount(self, obj):
        return sum(bill.due_amount for bill in obj.bills.all())

    
    def get_last_paid_date(self, obj):
        last_payment = None
        for bill in obj.bills.all():
            payment = bill.payments.order_by('-payment_date').first()
            if payment and (last_payment is None or payment.payment_date > last_payment):
                fmt = "%d-%m-%Y %H:%M" if IS_TESTING else "%d-%m-%Y"
                last_payment = payment.payment_date.strftime(fmt)
        return last_payment



class BatchSummarySerializer(serializers.ModelSerializer):
    total_members = serializers.SerializerMethodField()
    active_members = serializers.SerializerMethodField()
    total_collected = serializers.SerializerMethodField()
    total_due = serializers.SerializerMethodField()
    members_summary = serializers.SerializerMethodField()

    class Meta:
        model = Batch
        fields = [
            'id',
            'name',
            'total_members',
            'active_members',
            'total_collected',
            'total_due',
            'members_summary',
        ]

    def get_total_members(self, batch):
        return batch.members.count()

    def get_active_members(self, batch):
        return batch.members.filter(is_active=True).count()

    def get_total_collected(self, batch):
       
        total = Decimal(0)

        for member in batch.members.filter(is_active=True):
            for bill in member.bills.all():
                for payment in bill.payments.all():
                    total += payment.amount

        return total

    def get_total_due(self, batch):
        total = Decimal(0)

        for member in batch.members.filter(is_active=True):
            for bill in member.bills.all():
                total += bill.due_amount

        return total


    def get_members_summary(self, batch):
        
        data = []

        for member in batch.members.filter(is_active=True):
            paid_total = Decimal(0)
            due_total = Decimal(0)

            for bill in member.bills.all():
                paid_total += sum(p.amount for p in bill.payments.all())
                due_total += bill.due_amount

            data.append({
                "member_id": member.id,
                "member_name": member.full_name,
                "amount_paid": paid_total,
                "amount_due": due_total
            })

        return data

    
 



class MemberTransactionSerializer(serializers.ModelSerializer):

    paid_amount = serializers.DecimalField(
        source='amount', max_digits=10, decimal_places=2, read_only=True
    )

    pending_amount = serializers.SerializerMethodField()
    fmt = "%d-%m-%Y %H:%M" if IS_TESTING else "%d-%m-%Y"
    date = serializers.DateTimeField(
        source='payment_date', format=fmt, read_only=True
    )

    payment_type = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'date',
            'payment_type',
            'payment_method',
            'paid_amount',
            'pending_amount',
        ]

    def get_payment_type(self, obj):
        return ", ".join(
            p.get("fee_name")
            for p in obj.partial_payments
            if p.get("fee_name")
        )

    def get_pending_amount(self, obj):
        paid_till_now = sum(
            p.amount
            for p in obj.bill.payments.filter(
                payment_date__lte=obj.payment_date
            )
        )
        return max(obj.bill.total_amount  + obj.bill.member.outstanding_fee - paid_till_now, 0)




class BatchFeeCollectionSerializer(serializers.Serializer):
    batch_id = serializers.IntegerField()
    batch_name = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_paid = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_due = serializers.DecimalField(max_digits=12, decimal_places=2)

