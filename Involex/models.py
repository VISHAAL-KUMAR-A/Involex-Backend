from django.db import models

# Create your models here.


class ClioUser(models.Model):
    access_token = models.CharField(max_length=255)
    refresh_token = models.CharField(max_length=255)
    token_expires_at = models.DateTimeField()
    clio_user_id = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    region = models.CharField(max_length=2, default='NA', choices=[
        ('NA', 'North America'),
        ('EU', 'Europe'),
        ('CA', 'Canada')
    ])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.email


class ClioMatter(models.Model):
    matter_id = models.CharField(max_length=100)
    description = models.CharField(max_length=255)
    client_name = models.CharField(max_length=255)
    status = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.client_name} - {self.description}"
