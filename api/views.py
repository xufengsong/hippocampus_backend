from .models import User, SubscriptionTier, PaymentTransaction, Project
# Create your views here.
import logging
# api/views.py
from django.http import JsonResponse
from django.http import StreamingHttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db import transaction
from django.utils.text import slugify
from django.utils.crypto import get_random_string
import uuid
from .serializers import UserSerializer, ProjectSerializer

from adrf.decorators import api_view as async_api_view
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import NotFound
from .forms import CustomUserCreationForm

from celery.result import AsyncResult

from langchain_ollama import ChatOllama
import textwrap

import json
import openai
from openai import OpenAI
import requests
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from django.utils import timezone
from pgvector.django import L2Distance

from cognee.infrastructure.databases.graph import get_graph_engine


# Load environment variables from .env file
load_dotenv()

# Get the API key from environment variables
openai.api_key = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


# PayPal setup
PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID')
PAYPAL_CLIENT_SECRET = os.getenv('PAYPAL_CLIENT_SECRET')
PAYPAL_BASE_URL = os.getenv('PAYPAL_BASE_URL', 'https://api.sandbox.paypal.com')  # Use sandbox for testing


@api_view(['GET']) # Use DRF's decorator
@permission_classes([AllowAny]) # Make this view public
@ensure_csrf_cookie
def get_csrf_token(request):
    """
    This view sends the CSRF token as a cookie.
    The frontend calls this once to get the cookie set.
    """
    return JsonResponse({"detail": "CSRF cookie set"})


@api_view(['GET'])
@login_required
def get_ws_token(request):
    """
    Returns the session key as a token for WebSocket authentication.
    """
    return JsonResponse({
        'token': request.session.session_key
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_project(request):
    user = request.user
    topic = request.data.get("topic")

    if not topic:
        return Response({"error": "Topic is required"}, status=400)
    
    safe_topic = slugify(topic)
    unique_suffix = get_random_string(4)
    nodeset_name = f"user_{user.id}-{safe_topic}-{unique_suffix}"
    
    newProject = Project.objects.create(
        user = user,
        project_name = topic,
        project_id = uuid.uuid4(),
        cognee_nodeset_name = nodeset_name,
    )

    return Response({
        "new_project_id": newProject.project_id,
        "nodeset_name": newProject.cognee_nodeset_name
    })



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_project_list(request):
    user = request.user

    projects = Project.objects.filter(user=user).order_by("updated_at")

    reverse_projects = projects.reverse()

    serializer = ProjectSerializer(reverse_projects, many=True)

    return Response({
        "projects": serializer.data
    })


@async_api_view(['GET'])
@permission_classes([IsAuthenticated])
async def get_graph_data(request):
    project_id = request.GET.get("projectId")

    if not project_id:
        return Response({"error": "project_id is required"}, status=400)

    try:
        project = await Project.objects.aget(project_id=project_id, user=request.user)
        logging.info(project.project_id)
        logging.info(project.project_name)
        logging.info(project.cognee_nodeset_name)
    except Project.DoesNotExist:
        raise NotFound("Project not found or you do not have permission.")

    graph_engine = await get_graph_engine()

    try:
        # graph_data = await graph_engine.get_nodeset_subgraph(node_name=project.cognee_nodeset_name, node_type=object)
        graph_data = await graph_engine.get_graph_data()
        logging.info(f"!!!!!Succeed extracting node_set from {project.cognee_nodeset_name}")
    except:
        graph_data = await graph_engine.get_graph_data()
        logging.info("Sadly graph_data won't come from the sub graph")

    nodes_data, edges_data = graph_data

    return Response({
        'nodes_data': nodes_data,
        'edges_data': edges_data
    })



@async_api_view(['GET'])
@permission_classes([IsAuthenticated])
async def chat_response(request):
    """
    Returns LLM response to chat as a streaming HTTP response.
    """
    
    # 1. robustly get the message (assuming it's a query param since this is a GET)
    user_message = request.query_params.get('message', '')

    INSTRUCTIONS = textwrap.dedent("""
        PROMPT="You are a very strong reasoner and planner. Use these critical instructions to structure your plans, thoughts, and responses.

        Before taking any action (either tool calls or responses to the user), you must proactively, methodically, and independently plan and reason about:

        1) Logical dependencies and constraints:

        Analyze the intended action against the following factors. Resolve conflicts in order of importance:
        1.1) Policy-based rules, mandatory prerequisites, and constraints.
        1.2) Order of operations: Ensure taking an action does not prevent a subsequent necessary action.

        1.2.1) The user may request actions in a random order, but you may need to reorder operations to maximize successful completion of the task.
        1.3) Other prerequisites (information and/or actions needed).
        1.4) Explicit user constraints or preferences.

        2) Risk assessment:

        What are the consequences of taking the action? Will the new state cause any future issues?
        2.1) For exploratory tasks (like searches), missing optional parameters is a LOW risk.
        Prefer calling the tool with the available information over asking the user, unless your Rule 1 (Logical Dependencies) reasoning determines that optional information is required for a later step in your plan.

        3) Abductive reasoning and hypothesis exploration:

        At each step, identify the most logical and likely reason for any problem encountered.
        3.1) Look beyond immediate or obvious causes. The most likely reason may not be the simplest and may require deeper inference.
        3.2) Hypotheses may require additional research. Each hypothesis may take multiple steps to test.
        3.3) Prioritize hypotheses based on likelihood, but do not discard less likely ones prematurely. A low-probability event may still be the root cause.

        4) Outcome evaluation and adaptability:

        Does the previous observation require any changes to your plan?
        4.1) If your initial hypotheses are disproven, actively generate new ones based on gathered information.

        5) Information availability:

        Incorporate all applicable and alternative sources of information, including:
        5.1) Using available tools and their capabilities
        5.2) All policies, rules, checklists, and constraints
        5.3) Previous observations and conversation history
        5.4) Information only available by asking the user

        6) Precision and Grounding:

        Ensure your reasoning is extremely precise and relevant to each exact ongoing situation.
        6.1) Verify your claims by quoting the exact applicable information (including policies) when referring to them.

        7) Completeness:

        Ensure that all requirements, constraints, options, and preferences are exhaustively incorporated into your plan.
        7.1) Resolve conflicts using the order of importance in #1.
        7.2) Avoid premature conclusions: There may be multiple relevant options for a given situation.

        7.2.1) To check whether an option is relevant, reason about all information sources from #5.
        7.2.2) You may need to consult the user to even know whether something is applicable. Do not assume it is not applicable without checking.
        7.3) Review applicable sources of information from #5 to confirm which are relevant to the current state.

        8) Persistence and patience:

        Do not give up unless all the reasoning above is exhausted.
        8.1) Don't be dissuaded by time taken or user frustration.
        8.2) This persistence must be intelligent:
        - On transient errors (e.g. please try again), you must retry unless an explicit retry limit (e.g. max x tries) has been reached. If such a limit is hit, you must stop.
        - On other errors, you must change your strategy or arguments, not repeat the same failed call.

        9) Inhibit your response:

        Only take an action after all the above reasoning is completed. Once you’ve taken an action, you cannot take it back."
    """)

    llm = ChatOllama(
        model="gemma3:4b",
        temperature=0,
    )

    messages = [
        (
            "system",
            INSTRUCTIONS,
        ),
        ("human", user_message),
    ]

    # 2. Create a generator function to yield strings from the AIMessageChunks
    async def event_stream():
        # This calls the .stream() method signature you requested
        stream_iterator = llm.astream(
            input=messages, 
            # config=None, stop=None, **kwargs can be added here if needed
        )
        
        async for chunk in stream_iterator:
            # We must yield the string content, not the object
            if chunk.content:
                yield chunk.content

    # 3. Return a StreamingHttpResponse
    return StreamingHttpResponse(event_stream(), content_type='text/plain')

# ===================================================================================
# Payment related start
# ===================================================================================

def get_paypal_access_token():
    """Get access token from PayPal"""
    url = f"{PAYPAL_BASE_URL}/v1/oauth2/token"
    
    headers = {
        'Accept': 'application/json',
        'Accept-Language': 'en_US',
    }
    
    data = 'grant_type=client_credentials'
    
    response = requests.post(
        url,
        headers=headers,
        data=data,
        auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET)
    )
    
    if response.status_code == 200:
        return response.json()['access_token']
    else:
        raise Exception(f"Failed to get PayPal access token: {response.text}")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_subscription_tiers(request):
    """Get all available subscription tiers"""
    tiers = SubscriptionTier.objects.all()
    tier_data = []
    
    for tier in tiers:
        tier_data.append({
            'id': tier.id,
            'name': tier.name,
            'display_name': tier.display_name,
            'price': float(tier.price),
            'monthly_translation_limit': tier.monthly_translation_limit,
            'daily_translation_limit': tier.daily_translation_limit,
            'features': tier.features
        })
    
    return Response({
        'tiers': tier_data,
        'current_tier': request.user.get_current_tier().name,
        'usage': {
            'monthly_used': request.user.monthly_translations_used,
            'daily_used': request.user.daily_translations_used,
            'monthly_limit': request.user.get_current_tier().monthly_translation_limit,
            'daily_limit': request.user.get_current_tier().daily_translation_limit
        }
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_paypal_order(request):
    """Create a PayPal order for subscription payment"""
    try:
        tier_id = request.data.get('tier_id')
        
        if not tier_id:
            return Response({'error': 'Tier ID is required'}, status=400)
        
        try:
            tier = SubscriptionTier.objects.get(id=tier_id)
        except SubscriptionTier.DoesNotExist:
            return Response({'error': 'Invalid tier ID'}, status=400)
        
        # Don't allow payment for free tier
        if tier.name == 'free':
            return Response({'error': 'Cannot purchase free tier'}, status=400)
        
        # Get PayPal access token
        access_token = get_paypal_access_token()
        
        # Create PayPal order
        order_data = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {
                    "currency_code": "USD",
                    "value": str(tier.price)
                },
                "description": f"{tier.display_name} Subscription - Monthly"
            }],
            "application_context": {
                "return_url": f"{request.build_absolute_uri('/').rstrip('/')}/payment/success",
                "cancel_url": f"{request.build_absolute_uri('/').rstrip('/')}/payment/cancel"
            }
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        }
        
        response = requests.post(
            f"{PAYPAL_BASE_URL}/v2/checkout/orders",
            headers=headers,
            json=order_data
        )
        
        if response.status_code == 201:
            order = response.json()
            
            # Store payment transaction
            transaction = PaymentTransaction.objects.create(
                user=request.user,
                subscription_tier=tier,
                paypal_order_id=order['id'],
                amount=tier.price,
                currency='USD',
                status='pending'
            )
            
            # Get approval URL
            approval_url = None
            for link in order['links']:
                if link['rel'] == 'approve':
                    approval_url = link['href']
                    break
            
            return Response({
                'order_id': order['id'],
                'approval_url': approval_url
            })
        else:
            logging.error(f"PayPal order creation failed: {response.text}")
            return Response({'error': 'Failed to create PayPal order'}, status=500)
            
    except Exception as e:
        logging.error(f"Error creating PayPal order: {str(e)}")
        return Response({'error': 'Internal server error'}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def capture_paypal_payment(request):
    """Capture PayPal payment after user approval (with atomic transaction)"""

    try:
        order_id = request.data.get('order_id')
        
        if not order_id:
            return Response({'error': 'Order ID is required'}, status=400)
            
        # Use a transaction to ensure atomicity
        with transaction.atomic():
            # Use select_for_update() to lock the row until the transaction is complete
            transaction_obj = PaymentTransaction.objects.select_for_update().get(
                paypal_order_id=order_id,
                user=request.user,
                status='pending'
            )

            # Get PayPal access token
            access_token = get_paypal_access_token()
            
            # ... (rest of the PayPal API call logic is the same) ...
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {access_token}',
            }
            
            response = requests.post(
                f"{PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}/capture",
                headers=headers
            )

            if response.status_code == 201:
                capture_data = response.json()
                
                # Update transaction
                transaction_obj.status = 'completed'
                transaction_obj.paypal_capture_id = capture_data['id']
                transaction_obj.is_verified = True
                transaction_obj.verification_date = timezone.now()
                if 'payer' in capture_data and 'payer_id' in capture_data['payer']:
                    transaction_obj.paypal_payer_id = capture_data['payer']['payer_id']
                transaction_obj.save()
                
                # Update user subscription
                user = request.user
                user.subscription_tier = transaction_obj.subscription_tier
                user.subscription_start_date = timezone.now()
                user.subscription_end_date = timezone.now() + timedelta(days=30)
                user.is_subscription_active = True
                # Reset usage counters upon new subscription
                user.daily_translations_used = 0
                user.monthly_translations_used = 0
                user.save()
                
                return Response({ 'success': True, 'message': 'Payment successful!' }) # Simplified response
            else:
                # The 'with' block will automatically roll back the transaction on error
                logging.error(f"PayPal capture failed: {response.text}")
                transaction_obj.status = 'failed'
                transaction_obj.save()
                return Response({'error': 'Payment capture failed'}, status=500)

    except PaymentTransaction.DoesNotExist:
        return Response({'error': 'Transaction not found or already processed'}, status=404)
    except Exception as e:
        logging.error(f"Error capturing PayPal payment: {str(e)}")
        return Response({'error': 'Internal server error'}, status=500)
    

# Add these views to your views.py for handling PayPal redirects
def payment_success_view(request):
    """Handle successful payment redirect from PayPal"""
    return True


def payment_cancel_view(request):
    """Handle cancelled payment redirect from PayPal"""
    return False

# ===================================================================================
# Payment related end
# ===================================================================================


# ===================================================================================
# Template related start
# ===================================================================================
@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    email = request.data.get('email')
    password = request.data.get('password')

    user = authenticate(request, username=email, password=password)

    if user is not None:
        # THE FIX: Before calling login, explicitly set the user's backend attribute.
        # This tells Django's login function exactly how this user was authenticated.
        user.backend = 'api.backends.EmailBackend'
        
        # Now, use Django's standard, battle-tested login function.
        login(request, user)
        return Response({'message': 'Login successful'})
    else:
        return Response({'error': 'Invalid credentials'}, status=401)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request) # Django's built-in logout
    return JsonResponse({'message': 'Logout successful!'})


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):

    logging.error("Start registration")
    logging.error(f"This is received data {request.data}")
    # Use DRF's request.data, which handles JSON parsing automatically.
    form = CustomUserCreationForm(request.data)
    
    validity = form.is_valid()
    logging.error(f"Form validity {validity}")

    if form.is_valid():
        user = form.save(commit=False)
        user.is_active = True

        # Set user to free tier by default
        free_tier, created = SubscriptionTier.objects.get_or_create(
            name='free',
            defaults={
                'display_name': 'Free',
                'price': 0,
                'monthly_translation_limit': 50,
                'daily_translation_limit': 5,
                'features': ['Vocab usage', 'Quote usage']
            }
        )
        user.subscription_tier = free_tier
        user.save()

        return Response({'message': 'Account created successfully!'}, status=201)
    else:
        # --- Crucial Debugging for Errors ---
        logging.error("FORM IS INVALID. Errors are:")
        logging.error(f"{form.errors.as_json()}") # Log the specific errors as JSON

        # This is the standard way to return validation errors.
        return Response(form.errors, status=400)


@api_view(['GET']) # Explicitly allow GET requests
@permission_classes([IsAuthenticated]) # Enforce that the user must be logged in
def user_profile_view(request):
    """
    A view to get the logged-in user's profile information.
    """

    user = request.user
    
    # Use a serializer to safely convert the user model to JSON.
    serializer = UserSerializer(user)
    
    profile_data = serializer.data
    profile_data['subscription'] = {
        'tier': user.get_current_tier().name,
        'tier_display_name': user.get_current_tier().display_name,
        'is_active': user.is_subscription_active,
        'start_date': user.subscription_start_date,
        'end_date': user.subscription_end_date,
        'usage': {
            'daily_used': user.daily_translations_used,
            'monthly_used': user.monthly_translations_used,
            'daily_limit': user.get_current_tier().daily_translation_limit,
            'monthly_limit': user.get_current_tier().monthly_translation_limit
        }
    }
    
    # profile_data['csrfToken'] = get_token(request)
    
    return Response(profile_data)
# ===================================================================================
# Template related end
# ===================================================================================


# ==================================================================================
# Websocket Starts
# ==================================================================================
@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):

    return Response("OK", status=200)


# ==================================================================================
# Websocket Ends
# ==================================================================================