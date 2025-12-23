import json
from channels.generic.websocket import AsyncWebsocketConsumer
from urllib.parse import parse_qs
from channels.db import database_sync_to_async


class NotificationConsumer(AsyncWebsocketConsumer):
    
    @database_sync_to_async
    def get_user_from_jwt(self, token):
        """
        Retrieve the user from a JWT access token.
        """
        from rest_framework_simplejwt.tokens import AccessToken
        from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
        from django.contrib.auth import get_user_model
        
        User = get_user_model()

        try:
            # Validate and decode the JWT token
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            
            # Get the user from the database
            user = User.objects.get(pk=user_id)
            return user
        except (TokenError, InvalidToken, User.DoesNotExist) as e:
            print(f"JWT validation error: {e}")
            return None
    
    async def connect(self):
        print(f"WebSocket connect attempt")
        
        # Try to get JWT token from query parameters
        query_string = self.scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        token = query_params.get('token', [None])[0]
        
        print(f"Token from query params: {token[:20] if token else None}...")
        
        if not token:
            print("Connection REJECTED: No token provided.")
            await self.close(code=4001)
            return
        
        # Authenticate user via JWT
        user = await self.get_user_from_jwt(token)
        
        if not user:
            print("Connection REJECTED: Invalid or expired token.")
            await self.close(code=4001)
            return
        
        # Set the authenticated user in scope
        self.scope['user'] = user
        print(f"Connection ACCEPTED for user: {user.email} (ID: {user.id})")
        
        # Create a unique group name for each user
        self.group_name = f'user_{user.id}'
        
        # Add this user's channel to the group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        print(f"WebSocket disconnected: {close_code}")
        # Remove the channel from the group when disconnected
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    # This handles incoming messages from the client, like the heartbeat.
    async def receive(self, text_data):
        """
        Handle incoming WebSocket messages (e.g., ping/pong)
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'ping':
                # Respond to ping with pong
                await self.send(text_data=json.dumps({
                    'type': 'pong'
                }))
        except json.JSONDecodeError:
            print("Received invalid JSON")

    # This method is called when a message is sent to the user's group
    async def task_notification(self, event):
        # Send the message down to the client
        await self.send(text_data=json.dumps({
            'type': event['type'],
            'message': event['message']
        }))

    # Handles the message with the full data payload
    async def task_result(self, event):
        await self.send(text_data=json.dumps({
            'type': 'result',
            'data': event['data']
        }))