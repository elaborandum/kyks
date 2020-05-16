from django.shortcuts import redirect

from .exceptions import Redirection
from .models.users import set_user_status


#======================================================================================================================

class SimpleMiddleware(object):

    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        # ...
        # Calling the view.
        response = self.get_response(request)
        # Code to be executed for each request/response after
        # the view is called.
        # ...
        return response


#======================================================================================================================

class RedirectionMiddleware(SimpleMiddleware):
    """
    Catch redirection exceptions in the middleware,
    and return the corresponding redirect response.
    Include this class in MIDDLEWARE in settings.py!
    """

    def process_exception(self, request, exception):
        if isinstance(exception, Redirection):
            return redirect(*exception.args, **exception.kwargs)


#======================================================================================================================

class KykMiddleware(SimpleMiddleware):
    """
    Sets two attributes on the request.user object:
        - status: determines the actions that the user can perform on kyks
        - max_status: determines the maximal status that the user can have.

    Include this class in MIDDLEWARE in settings.py, after
        'django.contrib.sessions.middleware.SessionMiddleware' and
        'django.contrib.auth.middleware.AuthenticationMiddleware'!
    """

    def __call__(self, request):
        set_user_status(request.user, request.session)
        response = self.get_response(request)
        return response


#======================================================================================================================
