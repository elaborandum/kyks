"""
This module defines a generic url pattern for KykModel objects.
The ``kykmodel`` path is used by KykModel.get_absolute_url.
Either include it in your urlpatterns as:: 
    
    path('objects/', include('kyks.urls')),

or define an alternative url pattern with the name 'kykmodel'
that takes ``app``, ``model`` and ``pk`` as parameters.
"""

from django.urls import path

from .views import KykModelView, KyksView


#----------------------------------------------------------------------------------------------------------------------

urlpatterns = [
    path('<str:key>/', KyksView(), name='Kyks'),
    path('<str:app>/<str:model>/<int:pk>/', KykModelView(), name='kykmodel'),
]

