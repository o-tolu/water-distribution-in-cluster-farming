from django.urls import path
from django.contrib.auth import views as auth_views
from .forms import MyPasswordChangeForm, MyPasswordResetForm, MySetPasswordForm
from . import views

urlpatterns = [
  path('login/', views.CustomLoginView.as_view(), name='login'),
  path('register/', views.RegisterPage.as_view(), name='register'),
  path('logout/', views.logout_view, name='logout'),
  path('about/', views.about, name='about'),
  path('', views.landing_page, name='landing'), 
  path('waterflow/', views.Waterflow.as_view(), name='waterflow'),
  path('token-history/', views.TokenHistoryView.as_view(), name='token-history-page'),
  
  path('password-change/', auth_views.PasswordChangeView.as_view(
        template_name='base/password_management.html',
        form_class=MyPasswordChangeForm,
        success_url='/password-change/done/'
    ), name='password_change'),
  
  path('password-change/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='base/password_management.html'
    ), name='password_change_done'),
    
    
  path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='base/password_management.html',
        form_class=MyPasswordResetForm,
        success_url='/password-reset/done/',
        email_template_name='base/password_reset_email.html'
    ), name='password_reset'),

  path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='base/password_management.html'
    ), name='password_reset_done'),
    
  path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='base/password_management.html',
        form_class=MySetPasswordForm,
        success_url='/password-reset/complete/'
    ), name='password_reset_confirm'),
  
  path('password-reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='base/password_management.html'
    ), name='password_reset_complete'),
 
]
