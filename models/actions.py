from django.utils.functional import cached_property

from ..utils import do_not_call_in_templates

from .base import Status, KykBase, KykGetButton


#======================================================================================================================

def simple_action(status):
    """
    Generates a decorator that converts a method into an action,
    accessible to users with a status higher than or equal to the given value.
    """
    def kyk_allowed(user):
        """
        Check whether the user has sufficient status to access self (returns True or False).
        """
        return user.status >= status
    def decorator(method):
        method.kyk_allowed = kyk_allowed
        return do_not_call_in_templates(method)
    return decorator


#======================================================================================================================

class Action(KykBase):
    """
    Action.apply is a decorator that converts a method into a kyk action
    that can be used in templates as {% kykin kyk.action %}
    Sets the allowed status to the given status value or if that is None,
    then to cls.kyk_ACTION_STATUS where cls is the class where the method is decorated.
    or to cls.kyk_STATUS if cls.kyk_ACTION_STATUS was not defined.
    """

    def __init__(self, status=None):
        if status is not None:
            self.kyk_STATUS = status              

    @cached_property # This will be overriden if status is provided upon initialization.
    #@property # Does not work with @property because property.__set__ is messed up.
    def kyk_STATUS(self):
        try:
            return self._cls.kyk_ACTION_STATUS
        except AttributeError:
            return self._cls.kyk_STATUS
          
    def __get__(self, instance, cls=None):
        self._instance, self._cls = instance, cls
        return self

    @classmethod
    def apply(cls, *args, **kwargs):
        """
        Generates a decorator that converts an action method into an action kyk of this class.
        The method has to be invoked on the class, otherwise it will not work as a decorator::
            
            @Action.apply(Status.STAFF)
            def my_action_method(self, request, *args, **kwargs):
            
        """
        action = cls(*args, **kwargs)
        def decorator(method):
            if isinstance(method, classmethod):
                action.func = method.__func__
                def kyk_in(*args, **kwargs):
                    """
                    Return the template and context used to render the kyk with the kykin tag.
                    """
                    print("class action: ", action)
                    return action.func(action._cls, *args, **kwargs)
            else:       
                action.func = method
                def kyk_in(*args, **kwargs):
                    """
                    Return the template and context used to render the kyk with the kykin tag.
                    """
                    print("action: ", action)
                    return action.func(action._instance, *args, **kwargs)
            action.kyk_in = kyk_in
            return action
        return decorator
  
    def __str__(self):
        if hasattr(self, '_cls'):
            return f"Action {self.func.__name__} on {self._cls}"
        else:
            return f"Action {self.func.__name__}"


#----------------------------------------------------------------------------------------------------------------------
#======================================================================================================================



#======================================================================================================================

class ButtonAction(Action):
    """
    Action to be used through its apply decorator.
    Sets the allowed status to the given status value or if that is None,
    then to cls.kyk_ACTION_STATUS where cls is the class where the method is decorated. 

    The action displays a button that can activate it, using::
      
        {% kykin kyk.action.button %}

    and the result of the action through another kykin tag::
      
        {% kykin kyk.action.result %}
    
    The latter will return an empty string if the action was not actived
    by pressing the button.
    
    By default, the name of the decorated method is used as the action parameter
    and as its label. These parameters can be changed by setting the name and 
    label attributes in the constructor.
    """
    PRESENT_BUTTON = 1
    PRESENT_FORM = 2
    PROCESS_FORM = 3
    
    def __init__(self, status=None, name='', label=''):
        super().__init__(status=status)  
        self.name = name
        if label:
            self.label = label

    @classmethod
    def apply(cls, *args, **kwargs):
        """
        Generates a decorator that converts an action method into an action kyk of this class.
        The method has to be invoked on the class, otherwise it will not work as a decorator::
            
            @ButtonAction.apply(Status.STAFF)
            def my_action_method(self, request, stage=0, *args, **kwargs):
            
        """
        action = cls(*args, **kwargs)
        def decorator(method):
            if isinstance(method, classmethod):
                def caller(*args, **kwargs):
                    return method.__func__(action._cls, *args, **kwargs)
            else:
                def caller(*args, **kwargs):
                    return method.__func__(action._instance, *args, **kwargs)
            action.method = caller
            action.func = method.__func__
            if not action.name:
                action.name = method.__name__
            return action
        return decorator
    
    @property
    def label(self):
        return self.name.title()

    @property
    def kyk_identifier(self):
        return (self._cls if self._instance is None else self._instance).kyk_identifier

    @property
    def submitter(self):
        return '{}-{}'.format(self.kyk_identifier, self.name)
  
    def get_stage(self, request):
        if (request.method == 'GET') and (request.GET.get(self.name) == self.kyk_identifier):
            stage = self.PRESENT_FORM
        elif (request.method == 'POST') and (self.submitter in request.POST):
            stage = self.PROCESS_FORM
        else:
            stage = self.PRESENT_BUTTON
        return stage

    def kykin(self, request, stage=0, *args, **kwargs):
        stage = stage or self.get_stage(request)
        if stage <= self.PRESENT_BUTTON:
            return self.button(request, stage=stage)
        else:
            return self.result(request, *args, **kwargs)
            # For backwards compatibility the stage parameter was left out.
#            return self.result(request, stage=stage, *args, **kwargs)
                
    @do_not_call_in_templates
    def button(self, request, stage=0):
        """
        Displays a button that can activate the action.
        """
        # We have to apply the activate decorator to make sure that the Django template
        # engine does not call the method before the kykin tag is executed.
        stage = stage or self.get_stage(request)
        design = '' if stage <= self.PRESENT_BUTTON else 'disabled' 
        return KykGetButton(self.name, self.kyk_identifier, label=self.label, design=design)

    @do_not_call_in_templates
    def result(self, request, stage=0, *args, **kwargs):
        """
        Displays a button that can activate the action.
        """
        # We have to apply the activate decorator to make sure that the Django template
        # engine does not call the method before the kykin tag is executed.
        stage = stage or self.get_stage(request)
        if stage <= self.PRESENT_BUTTON:
            return ''
        data = request.POST if stage == self.PROCESS_FORM else None 
        return self.method(request, *args, data=data, **kwargs)


#----------------------------------------------------------------------------------------------------------------------
    
class AuthorAction(Action):
    """
    An action decorator that allows a user to bypass previous restrictions
    if he is the author of a kyk and has suficient status.
    
        @AuthorAction(Status.USER, author_field='owner').apply()

    This gives access to the method to the user who is the author of the kyk
    and has a status equal to or higher than ``Status.USER``.

    The default author status is ``Status.USER``. 
    This can be modified by redefining the ``AUTHOR_STATUS`` on the class
    or by passing in an additional ``author_status`` keyword upon initialization.

    The default author field on the kyk is ``author``. This can be modified 
    by passing in an additional ``author_field`` keyword upon initialization.

    One can also define a minimum status level for users other than the author.
    Otherwise the kyk_ACTION_STATUS value of the containing class will be used.

    """

    AUTHOR_STATUS = Status.USER

    def __init__(self, author_status=None, status=None, *, author_field='author'):
        if author_status is not None:
            self.AUTHOR_STATUS = author_status
        self.AUTHOR_FIELD = author_field
        super().__init__(status=status)
        
    def kyk_allowed(self, user):
        """
        Check whether the user has sufficient status to access self (returns True or False).
        """
        required_status = self.kyk_STATUS
        try:
            author = getattr(self._intance, self.AUTHOR_FIELD)
        except AttributeError:
            pass
        else:
            if user == author:
                required_status = self.AUTHOR_STATUS
        return user.status >= required_status
 
        
#======================================================================================================================


#======================================================================================================================
