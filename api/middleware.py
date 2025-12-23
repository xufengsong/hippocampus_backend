class DebugUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._jwt_authenticator = None

    @property
    def jwt_authenticator(self):
        """Lazy load JWT authenticator only when needed"""
        if self._jwt_authenticator is None:
            # Import here, not at module level
            from rest_framework_simplejwt.authentication import JWTAuthentication
            self._jwt_authenticator = JWTAuthentication()
        return self._jwt_authenticator

    def __call__(self, request):
        # Try to authenticate with JWT if Authorization header exists
        auth_header = request.headers.get('Authorization')
        
        if auth_header and auth_header.startswith('Bearer '):
            try:
                from rest_framework.exceptions import AuthenticationFailed
                
                # Manually authenticate the user using JWT
                user_auth_tuple = self.jwt_authenticator.authenticate(request)
                if user_auth_tuple is not None:
                    user, token = user_auth_tuple
                    # Attach the authenticated user to the request
                    request.user = user
                    print(f"✅ Path: {request.path}, User: {user.email} (JWT)")
                else:
                    print(f"⚠️  Path: {request.path}, User: AnonymousUser (No JWT found)")
            except AuthenticationFailed as e:
                print(f"❌ Path: {request.path}, JWT Auth Failed: {e}")
            except Exception as e:
                print(f"❌ Path: {request.path}, JWT Error: {e}")
        else:
            # No JWT token, user remains AnonymousUser
            print(f"🔓 Path: {request.path}, User: {request.user} (No Authorization header)")
        
        response = self.get_response(request)
        return response

class WebSocketScopeLogger:
    """
    Middleware for logging WebSocket connection scope details.
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            print(f"WebSocket connection from: {scope.get('client', 'Unknown')}")
            print(f"Path: {scope.get('path', 'Unknown')}")
            print(f"Headers: {scope.get('headers', [])}")
            
            # Check for JWT token in query string
            query_string = scope.get('query_string', b'').decode('utf-8')
            if 'token=' in query_string:
                print(f"JWT token present in query string")
            else:
                print(f"⚠️  No JWT token in query string")
        
        return await self.inner(scope, receive, send)