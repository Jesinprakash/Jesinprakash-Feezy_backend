from django.utils import timezone
from adminapp.models import Member, Bill
from adminapp.serializers import calculate_fees, KOLKATA, IS_TESTING
from adminapp.utils import normalize
from datetime import timedelta

def generate_bills_for_member(member_id):
    member = Member.objects.get(id=member_id,is_active=True)

    today = normalize(timezone.now().astimezone(KOLKATA))
    RD = normalize(member.recurring_date.astimezone(KOLKATA))   # Recurring Date (anchor)
    CD = normalize(member.created_at.astimezone(KOLKATA))       # Created At (tense reference)

    subscription = member.subscription
    duration_days = getattr(subscription, "duration_days", 30)
    # step = timedelta(minutes=duration_days) if IS_TESTING else timedelta(days=duration_days)
    step = timedelta(minutes=5) if IS_TESTING else timedelta(days=duration_days)
    is_day_mode = not IS_TESTING


    created_bills = []

    print(f"[DEBUG] Member {member.id} - RD: {RD}, CD: {CD}, today: {today}")
    print(f"[DEBUG] Duration: {duration_days}, Step: {step}")

    # -------------------------------------------------------------------
    # 1. FIRST BILL (RD)
    # - Always includes recurring + non-recurring fees
    # - Present (CD == RD) or Future (CD < RD): generate at RD once RD arrives
    # - Past (CD > RD): conceptually preserved but ignored in generation
    # -------------------------------------------------------------------
    if not Bill.objects.filter(member=member, is_recurring=False).exists():
        if RD >= CD and today >= RD:
            total = calculate_fees(subscription, include_joining=True)
            bill = Bill.objects.create(
                member=member,
                subscription=subscription,
                total_amount=total,
                due_amount=total,
                bill_date=RD,
                recurring_date=RD,
                is_recurring=False,
            )
            created_bills.append(bill)
            print(f"[DEBUG] First bill created at system time {today}, scheduled bill_date {RD}")
        else:
            print(f"[DEBUG] First bill at RD={RD} preserved conceptually but ignored (CD={CD})")

    # -------------------------------------------------------------------
    # 2. RECURRING SERIES
    # - Always follow RD + multiples of duration
    # - Past tense: fast-forward to first eligible bill ≥ CD
    # - Present/Future: start at RD + step
    # -------------------------------------------------------------------
    last_bill = Bill.objects.filter(member=member, is_recurring=True).order_by("-bill_date").first()

    if last_bill:
        next_bill_date = normalize(last_bill.bill_date + step)
        print(f"[DEBUG] Last recurring bill found on {last_bill.bill_date}, next bill date: {next_bill_date}")
    else:
        next_bill_date = normalize(RD + step)

        if CD > RD: 
            
            while (
                (next_bill_date.date() if is_day_mode else next_bill_date)
                <
                (CD.date() if is_day_mode else CD)
            ):

                print(f"[DEBUG] Advancing recurring date {next_bill_date} by {step}")
                next_bill_date += step
            print(f"[DEBUG] First eligible recurring bill after CD={CD} is {next_bill_date}")
        else:
            print(f"[DEBUG] Starting recurring series at {next_bill_date} (RD + step)")

    # -------------------------------------------------------------------
    # 3. CATCH-UP BEHAVIOR
    # - Generate all missed bills between CD and today
    # -------------------------------------------------------------------
    while next_bill_date <= today:
        if not Bill.objects.filter(member=member, bill_date=next_bill_date, is_recurring=True).exists():
            total = calculate_fees(subscription, include_joining=False)
            bill = Bill.objects.create(
                member=member,
                subscription=subscription,
                total_amount=total,
                due_amount=total,
                bill_date=next_bill_date,
                recurring_date=next_bill_date,
                is_recurring=True,
            )
            created_bills.append(bill)
            print(f"[DEBUG] Recurring bill created at system time {today}, scheduled bill_date {next_bill_date}")

        next_bill_date = normalize(next_bill_date + step)
        print(f"[DEBUG] Next bill date updated to {next_bill_date}")

    # -------------------------------------------------------------------
    # 4. SUMMARY
    # -------------------------------------------------------------------
    print(f"[DEBUG] Total bills created for member {member.id}: {len(created_bills)}")
    return created_bills