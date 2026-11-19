from django.urls import path
from . import views
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import path
from api.consumers import SensorDataConsumer

application = ProtocolTypeRouter({
    'websocket': AuthMiddlewareStack(
        URLRouter([
            path('ws/sensor-data/', SensorDataConsumer.as_asgi()),
        ])
    ),
})

urlpatterns = [
    path('', views.getRoutes, name="routes"),
    path('flow-data/', views.saveSensorData, name="flow-data-create"),
    path('flow-data/user/', views.getUserFlowData, name="flow-data-user"),
    path('token/recharge/', views.rechargeToken, name="token-recharge"),
    path('token/history/', views.getTokenHistory, name="token-history"),
    path('token/history/<int:entry_id>/delete/', views.deleteTokenHistory, name='delete-token-history'),
    path('valve/toggle/', views.toggle_valve, name='toggle_valve'),

    path('admin/', views.admin_dashboard, name='admin_home'),  
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/users/', views.admin_users, name='admin_users'),
    path('admin/create-admin/', views.admin_create_admin, name='admin_create_admin'),
    path('admin/token-history/', views.admin_token_history, name='admin_token_history'),
    path('admin/analytics/', views.admin_analytics_view, name='admin_analytics'),
    path('api/admin/analytics/', views.admin_analytics_api, name='admin_analytics_api'),
    path('admin/sensor-assignment/', views.admin_sensor_assignment, name='admin_sensor_assignment'),
    path('admin/assign-sensor/', views.assign_sensor, name='assign_sensor'),
    path('token/usage-history/', views.token_usage_history, name='token_usage_history'),
    path('cumulative-volume/', views.get_cumulative_volume, name='get_cumulative_volume'),
]
