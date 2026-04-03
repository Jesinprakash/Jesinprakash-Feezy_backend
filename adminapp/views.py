from django.shortcuts import render
from dateutil.relativedelta import relativedelta
from django.db import transaction

from django.db.models.functions import TruncMonth


from adminapp.serializers import (CategorySerializer,LoginSerializer,
                                  ClientCreateSerializer,PasswordUpdateSerializer,
                                  ForgotPasswordSerializer,BatchSerializer,SubscriptionSerializer,
                                  MemberSerializer,PaymentSerializer,calculate_fees,
                                  BillSerializer,BillFeeSerializer,MemberProfileSerializer,
                                  FeeRecieptSerializer,AttendanceBulkSerializer,
                                  BatchMemberSerializer,BatchSummarySerializer,MemberTransactionSerializer)
from adminapp.billing import generate_bills_for_member

import pytz,calendar,csv
import pandas as pd

from rest_framework import generics

from decimal import Decimal

from adminapp.models import Category,Client,Batch,Subscription,Member,Payment,Bill,Attendance
from rest_framework import authentication,permissions,status
from rest_framework.pagination import PageNumberPagination

from rest_framework.authtoken.models import Token
from django.shortcuts import get_object_or_404
from django.contrib.auth import authenticate

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from datetime import date, timedelta
from django.utils import timezone
from adminapp.config import IS_TESTING
from rest_framework.exceptions import ValidationError

from io import BytesIO
from django.http import HttpResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from django.db.models import Count, Q,Sum
from .utils import ( get_due_and_expired_members,get_month_date_range,
                     get_monthly_fees,get_attendance_stats,
                     get_attendance_date  
                    )


class GetTokenApiView(APIView):
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)

        if serializer.is_valid():
            username = serializer.validated_data.get("username")
            password = serializer.validated_data.get("password")

            # Authenticate user (checks hashed password)
            user = authenticate(request, username=username, password=password)

            if user is not None:
                # ✅ Check if subscription expired
                if user.subscription_end and user.subscription_end < timezone.now():
                    user.is_active = False
                    user.save()
                    return Response(
                        {"message": "Your subscription has expired. Please contact admin to renew."},
                        status=status.HTTP_403_FORBIDDEN
                    )

                # ✅ Block login for inactive users
                if not user.is_active:
                    return Response(
                        {"message": "Account is inactive. Please contact admin."},
                        status=status.HTTP_403_FORBIDDEN
                    )

                # ✅ If active and not expired → create or get token
                token, created = Token.objects.get_or_create(user=user)
                return Response(
                    {
                        "token": token.key,
                        "username": user.username,
                        "currency_emoji": user.currency_emoji,
                        "message": "Login successful",
                    },
                    status=status.HTTP_200_OK
                )

            else:
                return Response(
                    {"message": "Invalid username or password"},
                    status=status.HTTP_401_UNAUTHORIZED
                )

        # If serializer invalid
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CategoryCreateApiView(generics.ListCreateAPIView):

    serializer_class=CategorySerializer

    queryset=Category.objects.all()

    permission_classes=[permissions.IsAdminUser]

    authentication_classes=[authentication.TokenAuthentication]
    

class ClientRegisterApiView(generics.ListCreateAPIView):
    serializer_class = ClientCreateSerializer
    queryset = Client.objects.all()
    permission_classes = [permissions.IsAdminUser]  
    authentication_classes=[authentication.TokenAuthentication]
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)  

        client = serializer.save()

        return Response(
            {
                "message": "Client registered successfully",
                "client": serializer.data,
                "subscription_details": {
                    "amount": f"{client.subscription_amount}",
                    "valid_till": client.subscription_end,
                    "status": "Active" if client.is_active else "Inactive",
                }
            },
            status=status.HTTP_201_CREATED
        )

    


class LogoutApiView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # Delete the user's token (logs them out)
        request.user.auth_token.delete()
        return Response(
            {"message": "Logged out successfully"},
            status=status.HTTP_200_OK
        )


class PasswordUpdateApiView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = PasswordUpdateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Password updated successfully"}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class ClientUpdateRetrieveDeleteView(generics.RetrieveUpdateDestroyAPIView):

    queryset=Client.objects.all()

    serializer_class=ClientCreateSerializer

    authentication_classes=[authentication.TokenAuthentication]

    permission_classes=[permissions.IsAdminUser]







class ClientRenewApiView(APIView):
    permission_classes = [permissions.IsAdminUser]  

    def post(self, request, pk, *args, **kwargs):
        client = get_object_or_404(Client, pk=pk)

        # Ensure subscription_end exists
        if not client.subscription_end:
            return Response(
                {"error": "Client does not have an active subscription."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if current date is within 5 days before the subscription_end
        today = timezone.now()
        days_left = (client.subscription_end - today).days

        if days_left > 5:
            return Response(
                {"error": f"Subscription can only be renewed within the last 5 days. ({days_left} days left)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Calculate previous subscription duration
        old_duration = (
            (client.subscription_end - client.subscription_start).days
            if client.subscription_start and client.subscription_end
            else 365
        )

        # Renew with same details
        client.renew_subscription(
            duration_days=old_duration,
            amount=client.subscription_amount,
            currency=client.subscription_currency
        )

        return Response({
            "message": f"{client.business_name or client.username}'s subscription renewed successfully!",
            "subscription_start": timezone.localtime(client.subscription_start).strftime("%d-%b-%Y %I:%M %p"),
            "subscription_end": timezone.localtime(client.subscription_end).strftime("%d-%b-%Y %I:%M %p"),
            "subscription_amount": client.subscription_amount,
            "subscription_currency": client.subscription_currency,
        }, status=status.HTTP_200_OK)



class ForgotPasswordApiView(APIView):
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "New password sent to your email."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class BatchCreateListApiView(generics.ListCreateAPIView):

    serializer_class = BatchSerializer

    # authentication_classes = [authentication.BasicAuthentication]
    authentication_classes = [authentication.TokenAuthentication]

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):

        return Batch.objects.filter(client=self.request.user)

    def perform_create(self, serializer):

        serializer.save(client=self.request.user)


class BatchUpdateRetriveDeleteApiView(generics.RetrieveUpdateDestroyAPIView):

    serializer_class=BatchSerializer

    authentication_classes=[authentication.TokenAuthentication]

    permission_classes=[permissions.IsAuthenticated]

    def get_queryset(self):
        
        return Batch.objects.filter(client=self.request.user)


class SubscriptionListCreateView(generics.ListCreateAPIView):
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes=[authentication.TokenAuthentication]
    
    def perform_create(self, serializer):
        serializer.save(client=self.request.user)

    def get_queryset(self):
        return Subscription.objects.filter(client=self.request.user)

    

class SubscriptionDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes=[authentication.TokenAuthentication]

    def get_queryset(self):
        return Subscription.objects.filter(client=self.request.user)
    

# class MemberPagination(PageNumberPagination):
#     page_size = 2 
    
# class MemberListCreateApiView(generics.ListCreateAPIView):
#     queryset = Member.objects.all()
#     serializer_class = MemberSerializer
#     permission_classes = [permissions.IsAuthenticated]
#     authentication_classes = [authentication.TokenAuthentication]
#     pagination_class = MemberPagination

    
#     def get_queryset(self):
#         queryset =  Member.objects.filter(client=self.request.user)
        
#         search = self.request.query_params.get("search")
        
#         if search:
#             queryset = queryset.filter(
#             Q(full_name__icontains=search) | Q(contact_number__icontains=search)
#         )
#         return queryset 

#     def perform_create(self, serializer):
#         serializer.save(client=self.request.user)








class MemberPagination(PageNumberPagination):
    page_size = 7

class MemberListCreateApiView(generics.ListCreateAPIView):

    queryset = Member.objects.all()
    serializer_class = MemberSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.TokenAuthentication]
    pagination_class = MemberPagination

    def get_queryset(self):
        queryset = Member.objects.filter(client=self.request.user)

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search) |
                Q(contact_number__icontains=search)
            )
        return queryset

    # ✅ CREATE
    def perform_create(self, serializer):
        serializer.save(client=self.request.user)

    # ✅ POST HANDLER (IMPORTANT)
    def post(self, request, *args, **kwargs):
        if "file" in request.FILES:
            return self._bulk_upload(request)  # 👈 calls method below

        return super().post(request, *args, **kwargs)

    # =====================================
    # ✅ PASTE BULK UPLOAD HERE (INSIDE CLASS)
    # =====================================
    def _bulk_upload(self, request):
        file = request.FILES.get("file")

        if not file:
            return Response(
                {"error": "No file uploaded"},
                status=status.HTTP_400_BAD_REQUEST
            )

        df = pd.read_excel(file).fillna("")

        created_members = []
        errors = []

        with transaction.atomic():
            for index, row in df.iterrows():
                serializer = self.get_serializer(
                    data={
                        "full_name": row.full_name,
                        "subscription": row.subscription,
                        "batch_group": row.batch_group or None,
                        "recurring_date": row.recurring_date or None,
                        "is_active": True,
                    }
                )

                if serializer.is_valid():
                    member = serializer.save(client=request.user)
                    created_members.append(member.id)
                else:
                    errors.append({
                        "row": index + 2,
                        "errors": serializer.errors
                    })

        return Response(
            {
                "created": len(created_members),
                "members": created_members,
                "errors": errors
            },
            status=status.HTTP_201_CREATED if created_members else status.HTTP_400_BAD_REQUEST
        )
    


class MemberRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Member.objects.all()
    serializer_class = MemberSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.TokenAuthentication]

    def get_queryset(self):
        return Member.objects.filter(client=self.request.user)
 
 
# bills of a particular member    
class MemberBillsView(generics.ListAPIView):
    serializer_class = BillSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.TokenAuthentication]

    def get_queryset(self):
        member = get_object_or_404(
            Member,
            id=self.kwargs['member_id'],
            client=self.request.user
        )

        return Bill.objects.filter(
            member=member
        ).order_by('bill_date')

# fees of  a particular bill
class BillFeesView(generics.RetrieveAPIView):
    queryset = Bill.objects.all()
    serializer_class = BillFeeSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.TokenAuthentication]



    def get_queryset(self):
        return Bill.objects.filter(member__client=self.request.user)
    
 
    
class PaymentListCreateView(generics.ListCreateAPIView):
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.TokenAuthentication]

    def get_queryset(self):
        bill_id = self.kwargs.get('bill_id')
        return Payment.objects.filter(
            bill_id=bill_id,
            bill__member__client=self.request.user
        )

    def perform_create(self, serializer):
        bill_id = self.kwargs.get('bill_id')

        bill = get_object_or_404(
            Bill,
            id=bill_id,
            member__client=self.request.user
        )

        amount = serializer.validated_data.get('amount')

        if amount > bill.due_amount:
            raise ValidationError({
                "amount": "Payment exceeds due amount"
            })

        serializer.save(bill=bill)

        
    

class PaymentDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.TokenAuthentication]

    def get_queryset(self):
        return Payment.objects.filter(
            bill__member__client=self.request.user
        )


class MemberProfileView(generics.RetrieveAPIView):
    queryset = Member.objects.all()
    serializer_class = MemberProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.TokenAuthentication]
    
    def get_queryset(self):
        return Member.objects.filter(client=self.request.user)
    

class FeeReceiptView(generics.RetrieveAPIView):
    queryset = Bill.objects.all()
    serializer_class = FeeRecieptSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.TokenAuthentication]
    
    def get_queryset(self):
        return Bill.objects.filter(member__client=self.request.user)
    


class FeeReceiptPDFView(APIView):

    def get(self, request, pk):
        try:
            bill = Bill.objects.get(pk=pk, member__client=request.user)
        except Bill.DoesNotExist:
            return Response({"error": "Bill not found"}, status=404)

        serializer = FeeRecieptSerializer(bill)
        data = serializer.data

        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # ---------------- HEADER ----------------
        p.setFont("Helvetica-Bold", 20)
        p.drawCentredString(width / 2, height - 50, "FEE PAYMENT RECEIPT")

        p.setFont("Helvetica", 10)
        p.drawRightString(width - 50, height - 80, f"Receipt ID: {data['receipt_id']}")
        p.drawRightString(width - 50, height - 95, f"Bill Date: {data['bill_date']}")

        # Line
        p.line(40, height - 110, width - 40, height - 110)

        # ---------------- MEMBER DETAILS ----------------
        y = height - 150
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y, "Member Details")

        y -= 20
        p.setFont("Helvetica", 11)
        p.drawString(50, y, f"Name: {data['member_name']}")
        y -= 18
        p.drawString(50, y, f"Email: {data['email']}")
        y -= 18
        p.drawString(50, y, f"Contact: {data['contact_number']}")

        # ---------------- PAYMENT DETAILS ----------------
        y -= 30
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y, "Payment Details")

        y -= 20
        p.setFont("Helvetica", 11)
        p.drawString(50, y, f"Total Amount: ₹ {data['total_amount']}")
        y -= 18
        p.drawString(50, y, f"Paid Amount: ₹ {data['paid_amount']}")
        y -= 18
        p.drawString(50, y, f"Payment Mode: {data['payment_mode']}")

        # ---------------- FOOTER ----------------
        p.line(40, 120, width - 40, 120)

        p.setFont("Helvetica-Oblique", 9)
        p.drawCentredString(
            width / 2,
            100,
            "This is a system generated receipt. No signature required."
        )

        p.showPage()
        p.save()

        buffer.seek(0)

        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="receipt_{bill.id}.pdf"'
        return response





class AttendanceCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes=[authentication.TokenAuthentication]

    def post(self, request):
        client = request.user

        serializer = AttendanceBulkSerializer(
            data=request.data,
            many=True   # 🔥 THIS IS IMPORTANT
        )
        serializer.is_valid(raise_exception=True)

        for item in serializer.validated_data:
            batch = item['batch']
            member = item['member']
            date = item['date']

            # 🔐 SECURITY CHECKS
            if batch.client != client:
                return Response({"error": "Invalid batch"}, status=400)

            if member.client != client:
                return Response({"error": "Invalid member"}, status=400)

            Attendance.objects.update_or_create(
                client=client,
                batch=batch,
                member=member,
                date=date,
                defaults={
                    "present": item['present'],
                    "remarks": item.get('remarks', "")
                }
            )

        return Response({
            "message": "Attendance marked successfully"
        })








class BatchWiseMemberListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes=[authentication.TokenAuthentication]

    def get(self, request, batch_id):
        client = request.user  # ✅ logged-in client

        # Ensure batch belongs to this client
        try:
            batch = Batch.objects.get(id=batch_id, client=client)
        except Batch.DoesNotExist:
            return Response(
                {"detail": "Batch not found"},
                status=404
            )

        members = Member.objects.filter(
            batch_group=batch,
            client=client
        )

        serializer = BatchMemberSerializer(members, many=True)
        return Response(serializer.data)








class MonthlyAttendanceView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.TokenAuthentication]

    def get(self, request):
        client = request.user

        batch_id = request.query_params.get('batch')
        month = request.query_params.get('month')
        year = request.query_params.get('year')

        if not batch_id or not month or not year:
            return Response(
                {"error": "batch, month and year are required"},
                status=400
            )

        month = int(month)
        year = int(year)

        # 🔐 Ensure batch belongs to client
        batch = get_object_or_404(
            Batch,
            id=batch_id,
            client=client
        )

        # Get attendance for that month
        qs = Attendance.objects.filter(
            client=client,
            batch=batch,
            date__month=month,
            date__year=year
        )

        report = qs.values(
            'member__id',
            'member__full_name',
            'member__contact_number',
        ).annotate(
            total_days=Count('id'),
            present_days=Count('id', filter=Q(present=True)),
            absent_days=Count('id', filter=Q(present=False)),
        ).order_by('member__full_name')

        # Format response exactly like UI
        response_data = []
        for row in report:
            response_data.append({
                "member_id": row['member__id'],
                "member_name": row['member__full_name'],
                "contact_number": row['member__contact_number'],
                "group": batch.name,
                "month": calendar.month_name[month],
                "year": year,
                "total_days": row['total_days'],
                "present": row['present_days'],
                "absent": row['absent_days'],
            })

        return Response({
            "batch": batch.name,
            "month": calendar.month_name[month],
            "year": year,
            "report": response_data
        })

class DateAttendanceSummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.TokenAuthentication]

    def get(self, request):
        client = request.user

        batch_id = request.query_params.get('batch')
        date = request.query_params.get('date')

        if not batch_id or not date:
            return Response(
                {"error": "batch and date are required"},
                status=400
            )

        batch = get_object_or_404(
            Batch,
            id=batch_id,
            client=client
        )

        attendances = Attendance.objects.filter(
            client=client,
            batch=batch,
            date=date
        ).select_related('member')

        total = attendances.count()
        present = attendances.filter(present=True).count()
        absent = attendances.filter(present=False).count()

        members = [
            {
                "member_id": att.member.id,
                "member_name": att.member.full_name,
                "present": att.present,
                "remarks": att.remarks
            }
            for att in attendances
        ]

        return Response({
            "batch": batch.name,
            "date": date,
            "summary": {
                "total_members": total,
                "present": present,
                "absent": absent
            },
            "members": members
        })
    

class BatchSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.TokenAuthentication]

    def get(self, request, pk):
        """
        Only allow the batch owner (client) to view summary
        """
        batch = get_object_or_404(
            Batch,
            pk=pk,
            client=request.user
        )

        serializer = BatchSummarySerializer(batch)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    
    
    
    


class MemberPaymentReportAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.TokenAuthentication]

    def get(self, request, member_id):
        client = request.user

        payments = Payment.objects.filter(
            bill__member__id=member_id,
            bill__member__client=client
        ).select_related('bill', 'bill__member').order_by('payment_date')

        if not payments.exists():
            return Response({"detail": "No payments found"}, status=404)

        member = payments.first().bill.member

        total_paid = sum(
            p.amount
            for bill in member.bills.all()
            for p in bill.payments.all()
        )

        total_pending = sum(
            bill.due_amount for bill in member.bills.all()
        )

        return Response({
            "member_summary": {
                "member_id": member.id,
                "member_name": member.full_name,
                "batch_id": member.batch_group.id if member.batch_group else None,
                "total_paid": total_paid,
                "total_pending": total_pending
            },
            "transactions": MemberTransactionSerializer(payments, many=True).data
        })



        
        
        
class DashboardAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.TokenAuthentication]

    def get(self, request):
        client = request.user
        today = timezone.now().date()

        # ---- query params ----
        year = int(request.query_params.get("year", today.year))
        month = int(request.query_params.get("month", today.month))
        attendance_date_str = request.query_params.get("attendance_date")

        # ---- helpers ----
        start_date, end_date = get_month_date_range(year, month)
        attendance_date = get_attendance_date(attendance_date_str, today)

        # ---- members ----
        member_stats = Member.objects.filter(client=client).aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
            inactive=Count('id', filter=Q(is_active=False)),
        )

        # ---- due / expired ----
        due_count, expired_count, total_outstanding = get_due_and_expired_members(client)

        # ---- fees ----
        fees_stats = Payment.objects.filter(
            bill__member__client=client
        ).aggregate(total_revenue=Sum('amount'))

        amount_collected_month, amount_due_month = get_monthly_fees(
            client, start_date, end_date
        )

        # ---- attendance ----
        attendance_today = get_attendance_stats(client, attendance_date)

        return Response({
            "members": {
                "total": member_stats['total'] or 0,
                "active": member_stats['active'] or 0,
                "inactive": member_stats['inactive'] or 0,
                "expired": expired_count,
                "due": due_count
            },
            "fees": {
                "total_revenue": fees_stats['total_revenue'] or 0,
                "total_outstanding": total_outstanding,
                "amount_collected_month": amount_collected_month,
                "amount_due_month": amount_due_month
            },
            "attendance_today": {
                "present": attendance_today['present_count'] or 0,
                "absent": attendance_today['absent_count'] or 0
            }
        })









class FeezyDashboardAPIView(APIView):
    def get(self, request):
        now = timezone.now()

        # -------- Summary --------
        total_clients = Client.objects.count()
        active_clients = Client.objects.filter(subscription_end__gte=now).count()
        expired_clients = Client.objects.filter(subscription_end__lt=now).count()

        total_revenue = (
            Payment.objects.aggregate(total=Sum('amount'))['total'] or 0
        )

        # -------- Monthly Revenue --------
        monthly_qs = (
            Payment.objects
            .annotate(month=TruncMonth('payment_date'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )

        monthly_revenue = [
            {
                "month": item['month'].strftime('%b'),
                "total": float(item['total'])
            }
            for item in monthly_qs
        ]

        # -------- Client Outstanding --------
        client_outstanding_list = []
        total_client_outstanding = 0

        clients = Client.objects.all()

        for client in clients:
            paid_amount = (
                Payment.objects.filter(
                    bill__member__client=client
                ).aggregate(total=Sum('amount'))['total'] or 0
            )

            outstanding = client.subscription_amount - paid_amount

            if outstanding > 0:
                client_outstanding_list.append({
                    "client_id": client.id,
                    "business_name": client.business_name,
                    "outstanding_amount": float(outstanding),
                    "currency": client.subscription_currency,
                    "currency_emoji": client.currency_emoji,
                })
                total_client_outstanding += outstanding

        return Response({
            "summary": {
                "total_clients": total_clients,
                "active_clients": active_clients,
                "expired_clients": expired_clients,
                "total_revenue": float(total_revenue),
            },
            "monthly_revenue": monthly_revenue,
            "outstanding": {
                "total_outstanding": float(total_client_outstanding),
                
            }
        })





class BatchWiseFeeCollectionAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.BasicAuthentication]
    def get(self, request, *args, **kwargs):
        client = request.user  # assuming logged-in client

        batches = Batch.objects.filter(client=client)

        data = []

        for batch in batches:
            members = batch.members.all()

            bills = Bill.objects.filter(member__in=members)

            total_amount = bills.aggregate(
                total=Sum('total_amount')
            )['total'] or Decimal('0.00')

            total_paid = bills.aggregate(
                total=Sum('paid_amount')
            )['total'] or Decimal('0.00')

            total_due = bills.aggregate(
                total=Sum('due_amount')
            )['total'] or Decimal('0.00')

            data.append({
                "batch_id": batch.id,
                "batch_name": batch.name,
                "total_amount": total_amount,
                "total_paid": total_paid,
                "total_due": total_due,
            })

        return Response(data)