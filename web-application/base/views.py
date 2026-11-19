from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.contrib.auth.views import LoginView
from django.contrib.auth import login, logout
from django.views.generic import TemplateView
from django.views.generic.edit import FormView
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from .forms import CustomUserCreationForm, CustomAuthenticationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.list import ListView
import json
from api.models import FlowData, TokenHistory
from api.serializers import FlowDataSerializer, TokenHistorySerializer
from django.views.decorators.http import require_http_methods #added import
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

def get_page_range(current_page, total_pages, window=2):
    """Helper function to calculate visible page range"""
    start = max(current_page - window, 1)
    end = min(current_page + window + 1, total_pages + 1)
    return range(start, end)

class CustomLoginView(FormView):
    template_name = 'base/login.html'
    form_class = CustomAuthenticationForm

    def form_valid(self, form):
        user = form.get_user()

        if user is not None:
            login(self.request, user)

            # Redirect based on user type
            if user.is_admin:
                return redirect('admin_dashboard')  # Admin users go to admin dashboard
            return redirect('waterflow')  # Farmers go to waterflow page
        else:
            print("User authentication failed in form_valid()")

        return super().form_invalid(form)

    def form_invalid(self, form):
        return super().form_invalid(form)

    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def get_success_url(self):
        if self.request.user.is_admin:
            return reverse_lazy('admin_dashboard')
        return reverse_lazy('waterflow')
    
def landing_page(request):
    if request.user.is_authenticated:
        if request.user.is_admin:
            return redirect('admin_dashboard')
        return redirect('waterflow')
    return render(request, 'base/landing.html')
   
def about(request):
    return render(request, 'base/about.html')

class RegisterPage(FormView):
    template_name = 'base/signup.html'
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('waterflow')

    def form_valid(self, form):
        user = form.save(commit=False)
        # Enforce server-side: public registration always creates a non-admin farmer account.
        user.is_admin = False
        user.is_superuser = False
        user.save()

        login(self.request, user)
        return redirect(self.success_url)

    def form_invalid(self, form):
        return super().form_invalid(form)

    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def get(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            if self.request.user.is_admin:
                return redirect('admin_dashboard')
            return redirect('waterflow')
        return super(RegisterPage, self).get(*args, **kwargs)


def logout_view(request):
    if request.method == 'POST':
        logout(request)
        return redirect('login')  

    # GET requests also redirect to the login page
    elif request.method == 'GET':
        logout(request)
        return redirect('login')  

    # If the request method is neither GET nor POST, return an error response
    return JsonResponse({'status': 'failed'}, status=400)

import logging
from django.db.models import Sum  # Add this import
logger = logging.getLogger(__name__)

class Waterflow(LoginRequiredMixin, ListView):
    model = FlowData
    context_object_name = 'waterflows'
    template_name = 'base/waterflows.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_admin:
            return HttpResponseForbidden('Administrators cannot access farmer-specific features')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_id = self.request.user.id
        
        logger.info(f"Processing Waterflow view for user ID: {user_id}")
        
        try:
            # Get assigned sensor with farm_location
            flow_data = FlowData.objects.filter(
                user=self.request.user
            ).select_related('farm_location').first()

            if not flow_data:
                context.update({
                    'error': 'No sensor assigned',
                    'api_data': {},
                    'analytics': {'total_volume': 0}
                })
                return context

            assigned_sensor = flow_data.sensor_id
            farm_location = flow_data.farm_location

            # Calculate cumulative volume
            total_volume = TokenHistory.objects.filter(
                user=self.request.user,
                sensor_id=assigned_sensor
            ).aggregate(total_volume=Sum('volume_used'))['total_volume'] or 0

            context.update({
                'user_id': user_id,
                'sensor_id': assigned_sensor,
                'user_sensor_id': assigned_sensor,
                'farm_location': farm_location,
                'analytics': {
                    'total_volume': float(total_volume)
                }
            })

            # Get initial flow data and token info
            flow_data = FlowData.objects.filter(
                user=self.request.user,
                sensor_id=assigned_sensor
            ).first()

            active_token = TokenHistory.objects.filter(
                user=self.request.user,
                sensor_id=assigned_sensor,
                is_active=True,
                remaining_volume__gt=0
            ).first()

            # Structure data for WebSocket updates
            initial_data = {}
            if flow_data:
                flow_serializer = FlowDataSerializer(flow_data)
                sensor_data = flow_serializer.data
                if active_token:
                    sensor_data.update({
                        'token_info': {
                            'token_amount': float(active_token.token_amount),
                            'remaining_volume': float(active_token.remaining_volume),
                            'is_active': True,
                            'start_date': active_token.start_date,
                            'last_updated': active_token.last_updated
                        }
                    })
                initial_data[f'sensor{assigned_sensor}'] = sensor_data

            context['api_data'] = initial_data
            context['websocket_url'] = f"ws://{self.request.get_host()}/ws/sensor-data/"

        except Exception as e:
            print(f"\nException in Waterflow view: {str(e)}")
            context['error'] = str(e)
            context['api_data'] = {}
            context['analytics'] = {'total_volume': 0}

        return context
    
class TokenHistoryView(LoginRequiredMixin, TemplateView):
    template_name = 'base/token_history.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_admin:
            return HttpResponseForbidden('Administrators cannot access farmer-specific features')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items_per_page = 6  # Number of cards per page

        user = self.request.user
        assigned_sensor = FlowData.objects.filter(user=user).values_list('sensor_id', flat=True).first()
        has_sensor = bool(assigned_sensor)
        has_active_token = TokenHistory.objects.filter(
            user=user,
            is_active=True,
            remaining_volume__gt=0
        ).exists()
        context['has_sensor'] = has_sensor
        context['has_active_token'] = has_active_token

        if not assigned_sensor:
            context['token_history'] = []
            return context

        try:
            history = TokenHistory.objects.filter(
                user=user,
                sensor_id=assigned_sensor
            ).order_by('-start_date')
            tokens = TokenHistorySerializer(history, many=True).data

            paginator = Paginator(tokens, items_per_page)
            page = self.request.GET.get('page', 1)

            try:
                tokens_page = paginator.page(page)
            except PageNotAnInteger:
                tokens_page = paginator.page(1)
            except EmptyPage:
                tokens_page = paginator.page(paginator.num_pages)

            page_range = get_page_range(tokens_page.number, paginator.num_pages)

            context.update({
                'token_history': tokens_page,
                'page_range': page_range,
                'total_items': paginator.count,
                'total_pages': paginator.num_pages
            })
        except Exception as e:
            context['error'] = str(e)
            context['token_history'] = []

        return context

    def post(self, request, *args, **kwargs):
        try:
            entry_id = request.POST.get('token_id')
            if not entry_id:
                return JsonResponse({'error': 'Token ID required'}, status=400)

            token = TokenHistory.objects.filter(id=entry_id, user=request.user).first()
            if not token:
                return JsonResponse({'error': 'Token history not found'}, status=404)

            token.delete()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
