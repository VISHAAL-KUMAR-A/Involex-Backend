from django.contrib import admin
from .models import ClioUser, ClioMatter


@admin.register(ClioUser)
class ClioUserAdmin(admin.ModelAdmin):
    list_display = ('email', 'clio_user_id', 'token_expires_at',
                    'created_at', 'updated_at')
    search_fields = ('email', 'clio_user_id')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ClioMatter)
class ClioMatterAdmin(admin.ModelAdmin):
    list_display = ('client_name', 'description',
                    'status', 'created_at', 'updated_at')
    search_fields = ('client_name', 'description')
    readonly_fields = ('created_at', 'updated_at')
