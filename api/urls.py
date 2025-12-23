# api/urls.py
from django.urls import path, re_path, include
from . import views

urlpatterns = [
    path('auth/', include('dj_rest_auth.urls')),  # login, logout, password reset
    path('auth/registration/', include('dj_rest_auth.registration.urls')),  # register
    path('user_profile_view/', views.user_profile_view, name='user_profile_view'),
    path('get-csrf-token/', views.get_csrf_token, name='get-csrf-token'),
    path('get-ws-token/', views.get_ws_token, name='get_ws_token'),

    path('create_project/', views.create_project, name='create_new_project'),
    path('get_projects/', views.get_project_list, name='get_project_list'),
    path('chat/', views.chat_response, name='chat_response'),
    path('get_graph_data/', views.get_graph_data, name='get_graph_data'),

    # Subscription and Payment URLs
    path('subscription-tiers/', views.get_subscription_tiers, name='get_subscription_tiers'),
    path('create-paypal-order/', views.create_paypal_order, name='create_paypal_order'),
    path('capture-paypal-payment/', views.capture_paypal_payment, name='capture_paypal_payment'),
    
    # PayPal return URLs (for frontend routing)
    path('payment/success/', views.payment_success_view, name='payment_success'),
    path('payment/cancel/', views.payment_cancel_view, name='payment_cancel'),
]


