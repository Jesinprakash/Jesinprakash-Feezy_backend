import os
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from adminapp.models import Member, Bill
from adminapp.billing import generate_bills_for_member
from adminapp.serializers import  KOLKATA


LOG_FILE = os.path.join(os.path.dirname(__file__), 'bill_generation.log')

class Command(BaseCommand):
    help = "Generate bills for all members (production-ready with logging and transactions)"

    def handle(self, *args, **kwargs):
        members = Member.objects.select_related('subscription').all()

        for member in members:
            try:
                with transaction.atomic():
                    bills = generate_bills_for_member(member.id)
                    self.stdout.write(f"Generated {len(bills)} bills for member {member.id}")

                    # Log to file
                    with open(LOG_FILE, 'a') as f:
                        f.write(f"{timezone.now().strftime('%d-%m-%Y %H:%M:%S')} | "
                                f"Member {member.id}: {len(bills)} bills created\n")

            except Exception as e:
                # Log the error but continue with next member
                error_message = f"{timezone.now().strftime('%d-%m-%Y %H:%M:%S')} | Member {member.id}: ERROR {str(e)}\n"
                with open(LOG_FILE, 'a') as f:
                    f.write(error_message)
                self.stderr.write(error_message)
                
                
                
                
