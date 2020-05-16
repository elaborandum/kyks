

#======================================================================================================================

class Redirection(Exception):
    """
    Exception that signals a redirection.
    Intended to be called from inside a kyk template.

    Use:    
        raise Redirection(my_url)
        raise Redirection(to=my_view_name)
        raise Redirection(my_object, permanent=True)
        ...
    The first argument can be an url, a view or a model object (whose get_absolute_url method will be invoked).    
    """
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


#----------------------------------------------------------------------------------------------------------------------

class PermanentRedirection(Redirection):
    """
    Exception that signals a permanent redirection.
    Intended to be called from inside a kyk template.
    """
    def __init__(self, *args, **kwargs):
        super(self, PermanentRedirection).__init__(permanent=True, *args, **kwargs)


#======================================================================================================================

class Reload(Exception):
    """
    Exception that processes the request again but using a different kyk as page kyk,
    and optionally a given template (otherwise Templates.PAGE will be used).
    """

    def __init__(self, kyk=None, template=''):
        self.kyk = kyk
        self.template = template


#----------------------------------------------------------------------------------------------------------------------

class ReloadAsGet(Reload):
    """
    Exception that triggers a reprocessing of the view, handling the request as a 'GET'
    instead of a 'POST'. (This is enforced by the views.kyk_view function.)

    Use:    
        raise ReloadAsGet(request)
    
    The first argument should be the request object (this porbably will have changed,
    due to login, logout or changemood).    
    """


#======================================================================================================================

class KykInsufficientStatus(Exception):
    """
    Exception that signals that the user does not have a high enough status to display a kyk
    or to perform an action on it.
    """


#----------------------------------------------------------------------------------------------------------------------

class KykEmpty(Exception):
    """
    Exception that signals that a kyk results in an empty string
    for which the ``as_li``, ``as_p``, ``as_td`` or as ``<name>`` options should not apply.
    """
    # Its behavior is exactly the same as KykInsufficientStatus,
    # but we have defined it separately because it corresponds to different semantics.


#----------------------------------------------------------------------------------------------------------------------

class KykNotFoundError(Exception):
    """
    Exception that signals that a kyk was not recognized as a static page kyk, nor as an existing dynamic page kyk.
    """



#======================================================================================================================

