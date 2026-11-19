from channels.generic.websocket import AsyncWebsocketConsumer
import json

class SensorDataConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            await self.channel_layer.group_add("sensor_data", self.channel_name)
            await self.accept()
            print("WebSocket connected")
        except Exception as e:
            print(f"WebSocket connect error: {str(e)}")
            await self.close()

    async def disconnect(self, close_code):
        try:
            await self.channel_layer.group_discard("sensor_data", self.channel_name)
            print(f"WebSocket disconnected with code: {close_code}")
        except Exception as e:
            print(f"WebSocket disconnect error: {str(e)}")

    async def sensor_update(self, event):
        try:
            data = event.get('data', {})
            nested_token = data.get('token_info') if isinstance(data.get('token_info'), dict) else {}

            # Support both nested `token_info` (from saveSensorData) and top-level fields (from rechargeToken)
            await self.send(text_data=json.dumps({
                'sensor_id': data.get('sensor_id'),
                'flowRate': data.get('flowRate', 0.0),
                'volume': data.get('volume', 0.0),
                'valve_status': data.get('valve_status'),
                'message': data.get('message'),
                'error': data.get('error'),
                'token_info': {
                    'token_amount': nested_token.get('token_amount', data.get('token_amount', 0.0)),
                    'remaining_volume': nested_token.get('remaining_volume', data.get('remaining_volume', 0.0)),
                    'is_active': nested_token.get('is_active', data.get('is_active', False)),
                    'last_updated': nested_token.get('last_updated', data.get('last_updated')),
                    'volume_limit': nested_token.get('volume_limit', data.get('volume_limit', 0.0)),
                }
            }))
        except Exception as e:
            print(f"Error sending update: {str(e)}")