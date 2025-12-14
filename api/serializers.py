from rest_framework import serializers
from .models import User, Project

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