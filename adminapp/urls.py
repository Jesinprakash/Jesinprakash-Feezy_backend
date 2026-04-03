from django.urls import path

from adminapp import views

urlpatterns = [

    path('category/',views.CategoryCreateApiView.as_view()),

    path('user/',views.ClientRegisterApiView.as_view()),

    path('token/',views.GetTokenApiView.as_view()),

    path('update-password/',views.PasswordUpdateApiView.as_view()),

    path('client/<int:pk>/',views.ClientUpdateRetrieveDeleteView.as_view()),

    path('clients/<int:pk>/renew/',views.ClientRenewApiView.as_view()),

    path('forgot-password/',views.ForgotPasswordApiView.as_view()),

    path('logout/',views.LogoutApiView.as_view()),

    path('batch/',views.BatchCreateListApiView.as_view()),

    path('<int:pk>/batch/',views.BatchUpdateRetriveDeleteApiView.as_view()),
    
    path('subscriptions/', views.SubscriptionListCreateView.as_view(), name='subscription-list-create'),

    path('subscriptions/<int:pk>/', views.SubscriptionDetailView.as_view(), name='subscription-detail'),

    path('members/', views.MemberListCreateApiView.as_view(), name='member-list-create'),
    #
    path('members/<int:pk>/', views.MemberRetrieveUpdateDestroyAPIView.as_view(), name='member-detail'),
    
   
     path('bills/<int:bill_id>/payments/', views.PaymentListCreateView.as_view(), name=' bill-payments'),
    path('payments/<int:pk>/', views.PaymentDetailView.as_view(), name='payment-detail'),
            
    # Get bills for selected member
    #
    path('members/<int:member_id>/bills/', views.MemberBillsView.as_view(), name='member-bills'),

    # Get fees of a particular bill
    #
    path('bills/<int:pk>/fees/', views.BillFeesView.as_view(), name='bill-fees'),
    #
    path('member-profile/<int:pk>/', views.MemberProfileView.as_view()),
    #
    path('fee-receipt/<int:pk>/',views.FeeReceiptView.as_view()),

    path('bills/<int:pk>/receipt/pdf/', views.FeeReceiptPDFView.as_view(), name='bill-receipt-pdf'),

    path('attendance/',views.AttendanceCreateAPIView.as_view()),
    #
    path('batches/<int:batch_id>/members/',views.BatchWiseMemberListAPIView.as_view(),name='batch-wise-members'),

    path('attendance/monthly/',views.MonthlyAttendanceView.as_view()),

    path('attendance/date-summary/',views.DateAttendanceSummaryAPIView.as_view()),
    #
    path('batches/<int:pk>/summary/',views.BatchSummaryView.as_view(),name='batch-summary'),
    
    path('batches/<int:member_id>/member-payments/',
        views.MemberPaymentReportAPIView.as_view(),
        name='batch-member-payment-report'),
    
    path('dashboard/', views.DashboardAPIView.as_view(), name='dashboard'),

    path('feezydashboard/',views.FeezyDashboardAPIView.as_view()),
   
    path('batch-fee-collection/', views.BatchWiseFeeCollectionAPI.as_view(), name='batch-fee-collection')

        
    



    
    

]