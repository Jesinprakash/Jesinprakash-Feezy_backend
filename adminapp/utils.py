# adminapp/utils.py

### imports ###
from decimal import Decimal
from datetime import date,datetime
from django.db.models import Sum, Count, Q
from .models import Payment, Bill, Attendance, Member


#----   for automatic billing -----


def normalize(dt):
    """
    Normalize datetime to minute precision.
    Works for both minute-based testing and day-based billing.
    """
    return dt.replace(second=0, microsecond=0)


# -----  Due and expired members ----
def get_due_and_expired_members(client):
    due_count = 0
    total_outstanding = Decimal(0)

    active_members = client.members.filter(
        is_active=True
    ).prefetch_related('bills')

    for member in active_members:
        member_due = sum(
            bill.due_amount for bill in member.bills.all()
        )

        if member_due > 0:
            due_count += 1
            total_outstanding += member_due

    expired_count = due_count
    return due_count, expired_count, total_outstanding


# ---------------- DATE HELPERS ----------------

def get_month_date_range(year, month):
    start_date = date(year, month, 1)

    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)

    return start_date, end_date


# ---------------- FEES ----------------

def get_monthly_fees(client, start_date, end_date):
    collected = Payment.objects.filter(
        bill__member__client=client,
        payment_date__gte=start_date,
        payment_date__lt=end_date
    ).aggregate(total=Sum('amount'))['total'] or 0

    due = Bill.objects.filter(
        member__client=client,
        bill_date__gte=start_date,
        bill_date__lt=end_date
    ).aggregate(total=Sum('due_amount'))['total'] or 0

    return collected, due


# ---------------- ATTENDANCE ----------------

def get_attendance_stats(client, attendance_date):
    return Attendance.objects.filter(
        client=client,
        date=attendance_date
    ).aggregate(
        present_count=Count('id', filter=Q(present=True)),
        absent_count=Count('id', filter=Q(present=False))
    )


def get_attendance_date(attendance_date_str, today):
    if attendance_date_str:
        # return date.fromisoformat(attendance_date_str)
        return datetime.strptime(attendance_date_str, "%d-%m-%Y").date()

    return today
