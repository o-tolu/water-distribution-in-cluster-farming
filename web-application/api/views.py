from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test, login_required
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.db import transaction, models
from .serializers import FlowDataSerializer, TokenHistorySerializer
from decimal import Decimal, InvalidOperation
from .models import FlowData, TokenHistory,FarmLocation
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from functools import wraps
from django.http import JsonResponse, HttpResponseForbidden
from django.db.models import Count, Sum
from datetime import datetime, timedelta
from django.shortcuts import redirect
from base.forms import AdminUserCreationForm

@api_view(['GET'])
def getRoutes(request):
    routes = [
        {
            'Endpoint': '/api/flow-data/',
            'method': 'GET, POST',
            'body': {
                'user': 'integer',
                'sensor_id': 'string',
                'distributionID': 'integer',
                'flowRate': 'float',
                'volume': 'float',
            },
            'description': 'Create or get single flow meter reading'
        },
        {
            'Endpoint': '/api/flow-data/user/',
            'method': 'GET',
            'description': 'Get all flow data for authenticated user'
        },
        {
            'Endpoint': '/api/token/recharge/',
            'method': 'POST',
            'body': {'sensor_id': 'string', 'token_amount': 'decimal'},
            'description': 'Recharge water token for a sensor'
        },
        {
            'Endpoint': '/api/token/history/',
            'method': 'GET',
            'description': 'Get token and usage history for authenticated user'
        }
    ]
    return Response(routes)

from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.cache import cache

def get_last_depleted_volume_key(user_id, sensor_id):
    return f"last_depleted_volume_user_{user_id}_sensor_{sensor_id}"


@api_view(['GET', 'POST'])
def saveSensorData(request):
    try:
        if hasattr(request.user, 'is_admin') and request.user.is_admin:
            print("\n[ACCESS DENIED] Admin tried to access farmer-specific feature.")
            return Response({
                'error': 'Administrators cannot access farmer-specific features'
            }, status=status.HTTP_403_FORBIDDEN)
        
        data = request.data if request.method == 'POST' else request.GET
    
        
        try:
            sensor_id = int(data.get('sensor_id', 0))
            flow_rate = float(data.get('flowRate', 0))
            volume = float(data.get('volume', 0))
            
            if sensor_id <= 0:
                raise ValueError("sensor_id must be positive")
                
        except (TypeError, ValueError) as e:
            print(f"\nError: Invalid data format - {str(e)}")
            return Response({
                'error': 'Invalid data format',
                'details': str(e),
                'valve_status': 'CLOSE'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        print(f"\n[SENSOR DATA RECEIVED] Sensor: {sensor_id} | FlowRate: {flow_rate} | Volume: {volume}")

        assigned_user = FlowData.objects.filter(sensor_id=str(sensor_id)).select_related('user').first()
        
        if not assigned_user or not assigned_user.user:
            print(f"[NO USER] No user assigned to sensor {sensor_id}")
            return Response({
                'error': 'No user assigned to this sensor',
                'valve_status': 'CLOSE'
            }, status=status.HTTP_400_BAD_REQUEST)

        assigned_user = assigned_user.user
        
        # Get the flow data instance first
        instance = FlowData.objects.filter(
            user=assigned_user,
            sensor_id=str(sensor_id)
        ).first()
        
        # ✅ BLOCK if valve is manually closed - Now instance is defined before use
        if instance and instance.valve_closed:
            print(f"[VALVE CLOSED] Sensor: {sensor_id} | User: {assigned_user.id} | Action: BLOCKED")
            return Response({
                'error': 'Valve is manually closed by user',
                'flowRate': 0,
                'volume': volume,
                'valve_status': 'CLOSE'
            }, status=status.HTTP_403_FORBIDDEN)

        last_depleted_key = get_last_depleted_volume_key(assigned_user.id, sensor_id)
        last_depleted_volume = cache.get(last_depleted_key)

        if last_depleted_volume is not None:
            last_depleted_volume = float(last_depleted_volume)
            if volume >= last_depleted_volume:
                print(f"[TOKEN DEPLETED] Sensor: {sensor_id} | User: {assigned_user.id} | Volume: {volume} >= {last_depleted_volume}")
                return Response({
                    'error': 'No active token or insufficient balance',
                    'remaining_volume': 0,
                    'flowRate': 0,
                    'volume': last_depleted_volume,
                    'valve_status': 'CLOSE'
                }, status=status.HTTP_400_BAD_REQUEST)

        active_token = TokenHistory.objects.filter(
            user=assigned_user,
            sensor_id=str(sensor_id),
            is_active=True,
            remaining_volume__gt=0
        ).first()

        if not active_token:
            print(f"[NO ACTIVE TOKEN] Sensor: {sensor_id} | User: {assigned_user.id}")
            if instance:
                reset_data = {
                    'user': assigned_user.id,
                    'sensor_id': str(sensor_id),
                    'flowRate': 0,
                    'volume': volume
                }
                serializer = FlowDataSerializer(instance, data=reset_data)
                if serializer.is_valid():
                    serializer.save()

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "sensor_data",
                {
                    "type": "sensor_update",
                    "data": {
                        "message": "Token depleted",
                        "sensor_id": str(sensor_id),
                        "flowRate": 0,
                        "volume": volume,
                        "valve_status": 'CLOSE',
                        "token_info": {
                            "remaining_volume": 0,
                            "is_active": False
                        }
                    }
                }
            )
            print(f"[VALVE INSTRUCTION] Sensor: {sensor_id} | Action: CLOSE (No active token)")
            return Response({
                'error': 'No active token or insufficient balance',
                'remaining_volume': 0,
                'flowRate': 0,
                'volume': volume,
                'valve_status': 'CLOSE'
            }, status=status.HTTP_400_BAD_REQUEST)

        current_volume = volume
        previous_reading = FlowData.objects.filter(
            user=assigned_user,
            sensor_id=str(sensor_id)
        ).order_by('-created').first()
        
        last_recorded_volume = 0
        if previous_reading and previous_reading.volume is not None:
            last_recorded_volume = previous_reading.volume
        else:
            last_recorded_volume = 0


        if current_volume > last_recorded_volume:
            volume_used = current_volume - last_recorded_volume
            new_remaining = active_token.remaining_volume - Decimal(str(volume_used))
            print(f"[USAGE] Sensor: {sensor_id} | User: {assigned_user.id} | Used: {volume_used} | Remaining: {new_remaining}")

            if new_remaining <= 0:
                final_volume = current_volume
                cache.set(last_depleted_key, str(final_volume), timeout=None)

                active_token.remaining_volume = Decimal('0.0')
                active_token.volume_used = active_token.volume_limit
                active_token.is_active = False
                active_token.end_date = timezone.now()
                active_token.save()

                if instance:
                    final_data = {
                        'user': assigned_user.id,
                        'sensor_id': str(sensor_id),
                        'flowRate': 0,
                        'volume': final_volume
                    }
                    serializer = FlowDataSerializer(instance, data=final_data)
                    if serializer.is_valid():
                        serializer.save()

                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    "sensor_data",
                    {
                        "type": "sensor_update",
                        "data": {
                            "message": "Token depleted",
                            "sensor_id": str(sensor_id),
                            "flowRate": 0,
                            "volume": final_volume,
                            "valve_status": 'CLOSE',
                            "token_info": {
                                "token_amount": float(active_token.token_amount),
                                "remaining_volume": 0,
                                "is_active": False,
                                "volume_limit": float(active_token.volume_limit),
                                "last_updated": timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
                                "end_date": timezone.now().strftime('%Y-%m-%d %H:%M:%S')
                            }
                        }
                    }
                )
                print(f"[TOKEN DEPLETED] Sensor: {sensor_id} | User: {assigned_user.id} | Action: CLOSE")
                
                return Response({
                    'message': 'Token depleted',
                    'remaining_volume': 0,
                    'flowRate': 0,
                    'volume': final_volume,
                    'valve_status': 'CLOSE'
                }, status=status.HTTP_200_OK)

            active_token.volume_used += Decimal(str(volume_used))
            active_token.remaining_volume = new_remaining
            active_token.last_updated = timezone.now()
            active_token.save()

        sensor_data = {
            'user': assigned_user.id,
            'sensor_id': str(sensor_id),
            'flowRate': flow_rate,
            'volume': volume
        }

        if instance:
            serializer = FlowDataSerializer(instance, data=sensor_data)
        else:
            serializer = FlowDataSerializer(data=sensor_data)

        if serializer.is_valid():
            serializer.save()
            response_data = serializer.data
            response_data.update({
                'token_info': {
                    'token_amount': float(active_token.token_amount),
                    'remaining_volume': float(active_token.remaining_volume),
                    'is_active': True,
                    'volume_limit': float(active_token.volume_limit),
                    'last_updated': active_token.last_updated.strftime('%Y-%m-%d %H:%M:%S')
                },
                'valve_status': 'OPEN'
            })

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "sensor_data",
                {
                    "type": "sensor_update",
                    "data": response_data
                }
            )
            print(f"[SENSOR UPDATE] Sensor: {sensor_id} | User: {assigned_user.id} | FlowRate: {flow_rate} | Volume: {volume} | Valve: OPEN")
            
            return Response(response_data, status=status.HTTP_201_CREATED)
        
        print(f"[VALIDATION ERROR] Sensor: {sensor_id} | Errors: {serializer.errors}")
        return Response({
            'error': 'Validation failed',
            'details': serializer.errors,
            'valve_status': 'CLOSE'
        }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        print(f"\nException occurred: {str(e)}")
        return Response({
            'error': str(e),
            'flowRate': 0,
            'volume': volume if 'volume' in locals() else 0,
            'valve_status': 'CLOSE'
        }, status=status.HTTP_400_BAD_REQUEST)
  
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rechargeToken(request):
    try:
        if request.user.is_admin:
            return Response({
                'error': 'Administrators cannot access farmer-specific features'
            }, status=status.HTTP_403_FORBIDDEN)
            
        with transaction.atomic():
            # Get user's assigned sensor
            assigned_sensor = FlowData.objects.filter(user=request.user).values_list('sensor_id', flat=True).first()
            
            if not assigned_sensor:
                return Response({
                    'error': 'No sensor assigned to user'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Clear last depleted volume on recharge
            last_depleted_key = get_last_depleted_volume_key(request.user.id, assigned_sensor)
            cache.delete(last_depleted_key)

            try:
                token_amount = Decimal(str(request.data.get('token_amount', '0')))
                # Allow any positive value greater than 0
                if token_amount <= Decimal('0'):
                    return Response({
                        'error': 'Token amount must be greater than 0'
                    }, status=status.HTTP_400_BAD_REQUEST)
            except (TypeError, ValueError, InvalidOperation):
                return Response({
                    'error': 'Invalid token amount format'
                }, status=status.HTTP_400_BAD_REQUEST)


            volume_to_add = token_amount * 10
            current_time = timezone.now()

            recent_recharge = TokenHistory.objects.filter(
                user=request.user,
                sensor_id=assigned_sensor,
                start_date__gte=current_time - timedelta(seconds=10)
            ).exists()

            if recent_recharge:
                return Response({
                    'error': 'Please wait before attempting another recharge'
                }, status=status.HTTP_429_TOO_MANY_REQUESTS)

            active_token = TokenHistory.objects.select_for_update().filter(
                user=request.user,
                sensor_id=assigned_sensor,
                is_active=True
            ).first()

            if active_token and active_token.remaining_volume > 0:
                TokenHistory.objects.create(
                    user=request.user,
                    sensor_id=assigned_sensor,
                    token_amount=active_token.token_amount,
                    volume_limit=active_token.volume_limit,
                    volume_used=active_token.volume_used,
                    remaining_volume=active_token.remaining_volume,
                    is_active=False,
                    start_date=active_token.start_date,
                    last_updated=active_token.last_updated,
                    end_date=current_time
                )

                active_token.token_amount += token_amount
                active_token.volume_limit += volume_to_add
                active_token.remaining_volume += volume_to_add
                active_token.last_updated = current_time
                active_token.save()

                current_token = active_token
                serializer = TokenHistorySerializer(active_token)
            else:
                token_data = {
                    'user': request.user.id,
                    'sensor_id': assigned_sensor,
                    'token_amount': token_amount,
                    'volume_limit': volume_to_add,
                    'remaining_volume': volume_to_add,
                    'volume_used': Decimal('0.0'),
                    'is_active': True,
                    'start_date': current_time,
                    'last_updated': current_time
                }
                serializer = TokenHistorySerializer(data=token_data)
                if serializer.is_valid():
                    current_token = serializer.save()
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            flow_data = FlowData.objects.filter(
                user=request.user, 
                sensor_id=assigned_sensor
            ).first()
            
            response_data = {
                'sensor_id': assigned_sensor,
                'token_amount': float(current_token.token_amount),
                'volume_limit': float(current_token.volume_limit),
                'remaining_volume': float(current_token.remaining_volume),
                'volume_used': float(current_token.volume_used),
                'added_token_amount': float(token_amount),
                'added_volume': float(volume_to_add),
                'is_active': current_token.is_active,
                'start_date': current_token.start_date.strftime('%Y-%m-%d %H:%M:%S') if current_token.start_date else current_time.strftime('%Y-%m-%d %H:%M:%S'),
                'last_updated': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                'flowRate': float(flow_data.flowRate or 0.0) if flow_data else 0.0,
                'volume': float(flow_data.volume or 0.0) if flow_data else 0.0
            }

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "sensor_data",
                {
                    "type": "sensor_update",
                    "data": response_data
                }
            )

            return Response(response_data, status=status.HTTP_201_CREATED)

    except Exception as e:
        print(f"\nError in rechargeToken: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)  
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def getUserFlowData(request):
    try:

        if request.user.is_admin:
            return Response({
                'error': 'Administrators cannot access farmer-specific features'
            }, status=status.HTTP_403_FORBIDDEN)
            
        # Get user's assigned sensor
        assigned_sensor = FlowData.objects.filter(user=request.user).values_list('sensor_id', flat=True).first()
        
        if not assigned_sensor:
            return Response({
                'error': 'No sensor assigned to user'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get flow and token data for user's sensor
        user_data = FlowData.objects.filter(
            user=request.user,
            sensor_id=assigned_sensor
        ).first()
        
        active_token = TokenHistory.objects.filter(
            user=request.user,
            sensor_id=assigned_sensor,
            is_active=True,
            remaining_volume__gt=0
        ).first()
        
        response_data = {}
        
        if user_data:
            reading_data = FlowDataSerializer(user_data).data
            token_info = {
                'token_amount': float(active_token.token_amount) if active_token else 0.0,
                'remaining_volume': float(active_token.remaining_volume) if active_token else 0.0,
                'is_active': bool(active_token and active_token.remaining_volume > 0),
                'start_date': active_token.start_date if active_token else None,
                'last_updated': active_token.last_updated if active_token else None,
                'end_date': active_token.end_date if active_token else None
            }
            reading_data.update(token_info)
            response_data[f'sensor{assigned_sensor}'] = reading_data
                
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"\nError in getUserFlowData: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def getTokenHistory(request):
    try:

        if request.user.is_admin:
            return Response({
                'error': 'Administrators cannot access farmer-specific features'
            }, status=status.HTTP_403_FORBIDDEN)
            
        # Get user's assigned sensor
        assigned_sensor = FlowData.objects.filter(user=request.user).values_list('sensor_id', flat=True).first()
        
        if not assigned_sensor:
            return Response({
                'error': 'No sensor assigned to user'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get token history for user's sensor
        history = TokenHistory.objects.filter(
            user=request.user,
            sensor_id=assigned_sensor
        ).order_by('-start_date')
        
        if not history.exists():
            return Response([], status=status.HTTP_200_OK)
            
        serializer = TokenHistorySerializer(history, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        print(f"\nError in getTokenHistory: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

# function to delete token history entry
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def deleteTokenHistory(request, entry_id):
    try:
        if request.user.is_admin:
            return Response({
                'error': 'Administrators cannot access farmer-specific features'
            }, status=status.HTTP_403_FORBIDDEN)
            

        token = TokenHistory.objects.get(id=entry_id, user=request.user)
        token.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    except TokenHistory.DoesNotExist:
        return Response(
            {'error': 'Token history not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_valve(request):
    try:
        sensor_id = request.data.get('sensor_id')
        valve_closed = request.data.get('valve_closed', True)

        flow = FlowData.objects.filter(user=request.user, sensor_id=sensor_id).first()
        if not flow:
            return Response({'error': 'Sensor not found'}, status=404)

        flow.valve_closed = valve_closed
        flow.save()

        return Response({
            'message': f'Valve {"closed" if valve_closed else "opened"} successfully.',
            'valve_closed': valve_closed
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)
        
def is_admin(user):
    return user.is_authenticated and user.is_admin


def admin_required(json_response=False):
    """Enforce server-side administrator authorization on admin pages and APIs."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if json_response:
                    return JsonResponse(
                        {'status': 'error', 'message': 'Authentication required'},
                        status=401
                    )
                return redirect('login')
            if not request.user.is_admin:
                if json_response:
                    return JsonResponse(
                        {'status': 'error', 'message': 'Administrator privileges required'},
                        status=403
                    )
                return HttpResponseForbidden('Administrator privileges required')
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


@api_view(['POST'])
@admin_required(json_response=True)
def admin_create_admin(request):
    """Allow only authenticated administrators to create another administrator account."""
    form = AdminUserCreationForm(request.POST or request.data)
    if form.is_valid():
        form.save()
        return JsonResponse({
            'status': 'success',
            'message': 'Admin created successfully'
        }, status=201)
    return JsonResponse({
        'status': 'error',
        'message': form.errors.as_json()
    }, status=400)


@api_view(['GET'])
@admin_required(json_response=False)
def admin_dashboard(request):
    try:
        if request.path == '/api/admin/' or request.path == '/api/admin/dashboard/':
            User = get_user_model()
            context = {
                'total_users': User.objects.filter(is_admin=False).count(),  # Only count farmers
                'total_active_sensors': FlowData.objects.values('sensor_id').distinct().count(),
                'recent_tokens': TokenHistory.objects.select_related('user').order_by('-start_date')[:5]
            }
            return render(request, 'api/admin/dashboard.html', context)
        return redirect('admin_dashboard')
    except Exception as e:
        print(f"\nError in admin_dashboard: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)

@api_view(['GET'])
@admin_required(json_response=False)
def admin_users(request):
    try:
        User = get_user_model()
        items_per_page = 6  # Number of cards per page
        
        # Modified query to only get farmers
        sensors_with_users = (
            FlowData.objects
            .select_related('user')
            .filter(user__is_admin=False)  # Only get farmers
            .values(
                'sensor_id',
                'user__id',
                'user__firstname',
                'user__lastname',
                'user__email',
                'user__mobile',
                'user__created',
                'user__is_active'
            )
            .distinct()
        )
        
        unique_sensors = {}
        for sensor in sensors_with_users:
            sensor_id = sensor['sensor_id']
            if sensor_id not in unique_sensors:
                unique_sensors[sensor_id] = sensor

        # Create paginator instance
        paginator = Paginator(list(unique_sensors.values()), items_per_page)
        page = request.GET.get('page', 1)

        try:
            sensors_page = paginator.page(page)
        except PageNotAnInteger:
            sensors_page = paginator.page(1)
        except EmptyPage:
            sensors_page = paginator.page(paginator.num_pages)

        # Calculate visible page range
        page_range = get_page_range(sensors_page.number, paginator.num_pages)

        return render(request, 'api/admin/users.html', {
            'sensors_data': sensors_page,
            'page_range': page_range,
            'total_items': paginator.count,
            'total_pages': paginator.num_pages
        })
    except Exception as e:
        print(f"\nError in admin_users: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)
    
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

@api_view(['GET'])
@admin_required(json_response=False)
def admin_token_history(request):
    try:
        search_query = request.GET.get('search', '').strip()
        status_filter = request.GET.get('status', 'all')
        items_per_page = 10

        # Start with all tokens
        tokens = TokenHistory.objects.select_related('user').order_by('-start_date')

        # Apply filters
        if search_query:
            tokens = tokens.filter(
                models.Q(sensor_id__iexact=search_query) |
                models.Q(user__user_id__icontains=search_query) |
                models.Q(user__email__icontains=search_query) |
                models.Q(user__username__icontains=search_query)
            )

        if status_filter == 'active':
            tokens = tokens.filter(is_active=True)
        elif status_filter == 'expired':
            tokens = tokens.filter(is_active=False)

        # Create paginator instance
        paginator = Paginator(tokens, items_per_page)
        page = request.GET.get('page', 1)

        try:
            tokens_page = paginator.page(page)
        except PageNotAnInteger:
            tokens_page = paginator.page(1)
        except EmptyPage:
            tokens_page = paginator.page(paginator.num_pages)

        # Calculate visible page range
        page_range = get_page_range(tokens_page.number, paginator.num_pages)

        context = {
            'tokens': tokens_page,
            'search_query': search_query,
            'status_filter': status_filter,
            'page_range': page_range,
            'total_items': paginator.count,
            'total_pages': paginator.num_pages
        }
        return render(request, 'api/admin/token_history.html', context)
    except Exception as e:
        print(f"\nError in admin_token_history: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)

def get_page_range(current_page, total_pages, window=2):
    """Helper function to calculate visible page range"""
    start = max(current_page - window, 1)
    end = min(current_page + window + 1, total_pages + 1)
    return range(start, end)

@api_view(['GET'])
@admin_required(json_response=True)
def admin_analytics_api(request):
    try:
        # Get date range from request
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        if request.GET.get('start_date') and request.GET.get('end_date'):
            try:
                start_date = timezone.datetime.strptime(request.GET.get('start_date'), '%Y-%m-%d')
                end_date = timezone.datetime.strptime(request.GET.get('end_date'), '%Y-%m-%d')
            except ValueError as e:
                return JsonResponse({'error': f'Invalid date format: {str(e)}'}, status=400)

        # Aggregate metrics with error handling
        try:
            analytics_data = calculate_analytics_metrics(start_date, end_date)
        except Exception as e:
            return JsonResponse({'error': f'Error calculating metrics: {str(e)}'}, status=500)

        return JsonResponse(analytics_data)

    except Exception as e:
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)

@admin_required(json_response=False)
def admin_analytics_view(request):
    # Initial load with latest data
    end_date = timezone.now()
    start_date = end_date - timedelta(days=30)
    analytics_data = calculate_analytics_metrics(start_date, end_date)
    
    return render(request, 'api/admin/analytics.html', {'analytics': analytics_data['metrics']})

def calculate_analytics_metrics(start_date, end_date):
    """Helper function to calculate all analytics metrics"""
    
    with transaction.atomic():
        # Basic metrics
        total_tokens = TokenHistory.objects.count()
        active_tokens = TokenHistory.objects.filter(is_active=True).count()
        monthly_tokens = TokenHistory.objects.filter(
            start_date__range=[start_date, end_date]
        ).count()
        active_users = TokenHistory.objects.filter(
            is_active=True
        ).values('user').distinct().count()
        total_volume = TokenHistory.objects.aggregate(
            total=models.Sum('volume_limit')
        )['total'] or 0
        
        # Token distribution over time
        token_distribution = (TokenHistory.objects
            .filter(start_date__range=[start_date, end_date])
            .annotate(date=models.functions.TruncDate('start_date'))
            .values('date')
            .annotate(count=models.Count('id'))
            .order_by('date'))

        # Volume usage trends
        volume_usage = (TokenHistory.objects
            .filter(start_date__range=[start_date, end_date])
            .annotate(date=models.functions.TruncDate('start_date'))
            .values('date')
            .annotate(volume=models.Sum('volume_used'))
            .order_by('date'))

        # Format the data
        return {
            'metrics': {
                'total_tokens': total_tokens,
                'active_tokens': active_tokens,
                'monthly_tokens': monthly_tokens,
                'active_users': active_users,
                'total_volume': float(total_volume),
            },
            'token_labels': [entry['date'].strftime('%Y-%m-%d') for entry in token_distribution],
            'token_data': [entry['count'] for entry in token_distribution],
            'volume_labels': [entry['date'].strftime('%Y-%m-%d') for entry in volume_usage],  # Fixed date format
            'volume_data': [float(entry['volume'] or 0) for entry in volume_usage],
            'sensor_distribution': {
                'active': active_tokens,
                'inactive': total_tokens - active_tokens
            }
        }

@login_required
def token_usage_history(request):
    user_id = request.GET.get('user_id')
    sensor_id = request.GET.get('sensor_id')

    if not sensor_id:
        return JsonResponse({'error': 'Missing sensor_id'}, status=400)

    # Enforce ownership: non-admin users may only access their own usage history.
    if request.user.is_admin:
        if not user_id:
            return JsonResponse({'error': 'Missing user_id'}, status=400)
        target_user_id = user_id
    else:
        if user_id and str(user_id) != str(request.user.id):
            return JsonResponse({'error': 'Forbidden'}, status=403)
        target_user_id = request.user.id

    try:
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)

        usage_history = TokenHistory.objects.filter(
            user_id=target_user_id,
            sensor_id=sensor_id,
            start_date__range=[start_date, end_date]
        ).order_by('start_date')  # or 'last_updated'

        labels = [entry.start_date.strftime('%Y-%m-%d %H:%M') for entry in usage_history]
        volumes = [float(entry.volume_used) for entry in usage_history]

        return JsonResponse({
            'labels': labels,
            'volumes': volumes
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
 

@api_view(['GET'])
@admin_required(json_response=False)
def admin_sensor_assignment(request):
    try:
        User = get_user_model()
        
        # Get all non-admin users
        users = User.objects.filter(is_admin=False).order_by('-created')
        
        # Get current sensor assignments
        assigned_sensors = FlowData.objects.all()
        assigned_sensor_ids = set(assigned_sensors.values_list('sensor_id', flat=True))
        
        # Get farm locations - Pass choice tuples instead of model instances
        farm_locations = [{'id': choice[0], 'name': choice[1]} for choice in FarmLocation.FARM_CHOICES]
        
        # Define all available sensors (1-3)
        all_sensors = set(['1', '2', '3'])
        available_sensors = all_sensors - assigned_sensor_ids
        
        # Add assigned sensor info to each user
        users_with_sensors = []
        for user in users:
            sensor_data = assigned_sensors.filter(user=user).first()
            user_dict = {
                'id': user.id,
                'firstname': user.firstname,
                'lastname': user.lastname,
                'email': user.email,
                'created': user.created,
                'assigned_sensor': sensor_data.sensor_id if sensor_data else None,
                'farm_location': sensor_data.farm_location if sensor_data else None,
                'rfid_number': user.rfid_number,
                'matric_number': user.matric_number
            }
            users_with_sensors.append(user_dict)
        
        context = {
            'users': users_with_sensors,
            'all_sensors': sorted(list(all_sensors)),
            'available_sensors': sorted(list(available_sensors)),
            'farm_locations': farm_locations,
            'unassigned_users_count': len([u for u in users_with_sensors if not u['assigned_sensor']]),
            'available_sensors_count': len(available_sensors),
            'total_assignments': len(assigned_sensor_ids)
        }
        
        return render(request, 'api/admin/sensor_assignment.html', context)
    except Exception as e:
        print(f"\nError in admin_sensor_assignment: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)
    

@api_view(['POST'])
@admin_required(json_response=True)
def assign_sensor(request):
    try:
        with transaction.atomic():
            user_id = request.POST.get('user_id')
            sensor_id = request.POST.get('sensor_id')
            farm_location_id = request.POST.get('farm_location')  # This will be 'A', 'B' or 'C'
            
            User = get_user_model()
            
            # Get user and verify they are not an admin
            user = User.objects.filter(id=user_id, is_admin=False).first()
            if not user:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid user or admin users cannot be assigned sensors'
                }, status=400)
            
            # Check if sensor is already assigned
            existing_assignment = FlowData.objects.filter(sensor_id=sensor_id).first()
            if existing_assignment and existing_assignment.user != user:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Sensor {sensor_id} is already assigned to another user'
                }, status=400)
            
            # Get farm location using the choice value
            try:
                farm_location = FarmLocation.objects.get(name=farm_location_id)
            except FarmLocation.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Invalid farm location choice: {farm_location_id}'
                }, status=400)
            
            # Create or update flow data for this assignment
            FlowData.objects.update_or_create(
                sensor_id=sensor_id,
                defaults={
                    'user': user,
                    'farm_location': farm_location,
                    'flowRate': 0,
                    'volume': 0
                }
            )
            
            # Update any existing token history for this user
            TokenHistory.objects.filter(user=user).update(sensor_id=sensor_id)
            
            # Notify through WebSocket
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "sensor_data",
                {
                    "type": "sensor_update",
                    "data": {
                        "message": f"Sensor {sensor_id} assigned to {user.firstname} at {farm_location.get_name_display()}",
                        "sensor_id": sensor_id,
                        "user_id": user_id,
                        "farm_location": farm_location.name
                    }
                }
            )
            
            return JsonResponse({
                'status': 'success',
                'message': f'Sensor {sensor_id} assigned to {user.firstname} at {farm_location.get_name_display()}'
            })
    except Exception as e:
        print(f"\nError in assign_sensor: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)
    
from django.views.decorators.http import require_GET

@login_required
@require_GET
def get_cumulative_volume(request):
    user = request.user
    sensor_id = request.GET.get('sensor_id')
    if not sensor_id:
        return JsonResponse({'error': 'Missing sensor_id'}, status=400)
    total_volume = TokenHistory.objects.filter(
        user=user,
        sensor_id=sensor_id
    ).aggregate(total_volume=Sum('volume_used'))['total_volume'] or 0
    return JsonResponse({'total_volume': float(total_volume)})