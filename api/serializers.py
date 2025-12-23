from rest_framework import serializers
from .models import User, Project, SubscriptionTier

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        # Define the fields you want to send to the frontend.
        # NEVER include the password hash.
        fields = [
            'id',  # don't delete this?
            'email', 
            'name', # don't delete this?
            'username',
        ]


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        # List all the fields you want to send to the frontend
        fields = ['id', 'project_name', 'project_id', 'created_at', 'cognee_nodeset_name']


class RegisterSerializer(serializers.ModelSerializer):
    """Custom registration to set subscription tier"""
    
    def custom_signup(self, request, user):
        # Set free tier for new users
        free_tier, _ = SubscriptionTier.objects.get_or_create(
            name='free',
            defaults={
                'display_name': 'Free',
                'price': 0,
                'monthly_translation_limit': 50,
                'daily_translation_limit': 5,
                'features': []
            }
        )
        user.subscription_tier = free_tier
        user.save()