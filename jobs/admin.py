from django.contrib import admin
from .models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'location', 'source', 'last_seen')
    search_fields = ('title', 'company', 'location', 'description')
    ordering = ('-last_seen',)
