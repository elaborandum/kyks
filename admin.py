from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import KykUser

# Register your models here.

admin.site.register(KykUser, UserAdmin)