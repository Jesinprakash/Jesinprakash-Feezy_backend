from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.core.management import call_command
from django.conf import settings

def start_scheduler():
    scheduler = BackgroundScheduler(
        timezone=settings.TIME_ZONE
    )

    scheduler.add_job(
        lambda: call_command("generate_bills"),
        trigger=CronTrigger(hour=0, minute=0),  # daily at 12:00 AM
        # CronTrigger(minute="*/1"),
        id="daily_billing_job",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
