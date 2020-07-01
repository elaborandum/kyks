#from itertools import chain, takewhile

from django.conf import settings
from django.db import models, IntegrityError
from django import forms
from django.template import Template
from django.urls import reverse
from django.utils import html
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy

from ..exceptions import Redirection
from ..utils import cached_classproperty


#======================================================================================================================

class ParameterDict(dict):
    """
    Allows to refer to parameters as class attibutes,
    It is defined as a class to allow extension in other modules and to allow some useful overloadings. 
    e.g. looping over a ParameterDict yields item pairs, in ascending order of value.
    """

    def __init__(self, *args, **kwargs):
        if args:
            kwargs.update({key:i+1 for i, key in enumerate(args)})
        super().__init__(kwargs)

    def __getattr__(self, attr):
        return self[attr]

    def choices(self, force=set(), maximum=None):
        """
        Returns a list of (value, key) pairs (sorted in the order of definition),
        up to a maximum value and only if the key is listed in force, if force is given.
        """     
        member_items = sorted(self.items(), key=lambda x:x[1])
        if force:
            member_items = ((key, value) for key, value in member_items if key in force)
        if maximum is not None:
            member_items = ((key, value) for key, value in member_items if value <= maximum)
        return [(value, key) for key, value in member_items]

    @cached_property
    def value2key(self):
        """
        Returns a dictionary that maps values to keys.
        This can be useful when one wants to store parameters in the database:
        it is safer to store the keys than to store the values because they are less likely to change.
        """
        return {value:key for key, value in self.items()}

#----------------------------------------------------------------------------------------------------------------------

Templates = ParameterDict(**settings.KYK_TEMPLATES)

Status = ParameterDict(*settings.KYK_STATUS)

Styles = ParameterDict(*settings.KYK_STYLES)


#======================================================================================================================


class kykdict(dict):

    def __setitem__(self, key, val):
        """
        When including an item in Kyks, this method makes sure that the key
        is stored on the item as item.kyk_Kyks_key.
        """        
        try:
            val.kyk_Kyks_key = key
        except AttributeError:
            pass
        super().__setitem__(key, val)

Kyks = kykdict() # A dict used to store static kyks.
# The kyks context processor makes it available in templates.
# We use a custum dict class in order to be able to set attributes on Kyks,
# e.g. Kyks.append

def append2Kyks(name=None):
    """
    Decorator that adds an instance of cls to the Kyks dictionnary 
    with the given name or cls.__name__ if no name is provided.
    """
    if isinstance(name, str):
        # The decorator was invoked as @append2Kyks('my_name')
        def decorating_name(cls):
            kyk = cls()
            kyk.identifier = name
            Kyks[name] = kyk
            return cls
        return decorating_name 
    else:
        def decorating_class(cls):
            name = cls.__name__
            kyk = cls()
            kyk.identifier = name
            Kyks[name] = kyk
            return cls
        if name is None: 
            # The decorator was invoked as @append2Kyks()
            return decorating_class
        else:
            # The decorator was invoked as @append2Kyks
            return decorating_class(cls=name)

Kyks.append = append2Kyks 
# Kyks.append was not defined as a method on kykdict in order to be able to use it as a decorator


#======================================================================================================================

class KykBase:
    """
    This class defines minimal attributes and methods required by the kykin template tag.
    This is used by static and dynamic page kyks, but can be used by other classes as well.
    """
    # Note that KykPanel only makes sense for static and dynamic page kyks, 
    # so KykBase does not make any reference to KykPanel.

    kyk_STATUS = Status.PUBLIC # Default required status to view the kyk
    kyk_ACTION_STATUS = Status.PUBLIC # Default required status to act on the kyk
    kyk_TEMPLATE = Template("{{ kyk }}") 
    
    def kyk_in(self, request, template=None, **kwargs):
        """
        Return the template and context used to render the kyk with the kykin tag.
        """
        if template is None:
            template = self.kyk_TEMPLATE 
            # We can not set this as a default value for the template argument
            # because subclasses would use KykBase.kyk_TEMPLATE
            # instead of their own kyk_TEMPLATE value.
        kwargs.update(kyk=self)
        return template, kwargs

    def kyk_allowed(self, user):
        """
        Check whether the user has sufficient status to access self (returns True or False).
        """
        return user.status >= self.kyk_STATUS

    def get_absolute_url(self):
        return reverse('Kyks', kwargs={'key': self.kyk_Kyks_key})


#======================================================================================================================

class Action(KykBase):
    """
    Action to be used in the Activate decorator.
    Sets the allowed status to the given status value or if that is None,
    then to cls.kyk_ACTION_STATUS where cls is the class where the method is decorated. 
    """

    def __init__(self, status=None):
        if status is not None:
            self.kyk_STATUS = status

    @cached_property # This will be overriden if status is provided upon initialization.
    #@property # Does not work with @property because property.__set__ is messed up.
    def kyk_STATUS(self):
        return self._cls.kyk_ACTION_STATUS

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
        def decorator(obj):
            method = obj.kyk_in.method if isinstance(obj, Action) else obj
            if isinstance(method, classmethod):
                def kyk_in(*args, **kwargs):
                    """
                    Return the template and context used to render the kyk with the kykin tag.
                    """
                    return kyk_in.method.__func__(action._cls, *args, **kwargs)
            else:       
                def kyk_in(*args, **kwargs):
                    """
                    Return the template and context used to render the kyk with the kykin tag.
                    """
                    return kyk_in.method(action._instance, *args, **kwargs)
            kyk_in.method = method
            action.kyk_in = kyk_in
            return action
        return decorator
  

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

class KykSimple(KykBase):
    """
    A simple kyk that displays a template.
    It is added to Kyks as Kyks[name].
    Additional attributes of the kyk can be provided as keyword arguments. 
    """

    def __init__(self, name, template, status=None, **kwargs):
        self.kyk_TEMPLATE = template
        if status is not None:
            self.kyk_STATUS = status
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.identifier = name
        Kyks[name] = self
        
    @classmethod
    def from_string(cls, template_string, **kwargs):
        """
        Creates a simple kyk from a template provided as a text string.
        """
        return cls(Template(template_string), **kwargs)


#----------------------------------------------------------------------------------------------------------------------

class KykList(KykBase):
    """
    An kyk that displays a query list of kyks.
    """
    kyk_TEMPLATE = Templates.LIST

    def __init__(self, Model, query=None, *, initial=dict(), use_kwargs=False,
                 order_by_fields=[], template=None, **kwargs):
        """
        Model : KykModel (or if query is given, then whatever model you want to add after the list).
            The model for which to make the query.
            At the end of the list, an option is given to add kyks of this type
        query : callable, optional
            Should return the query list. 
            The default is None, in which case Model.objects.all is used.
        initial : dict, optional
            Dict with initial values for the kyk_add action.
        use_kwargs: bool, optional
            Use the kwargs dict as the initial dict for kyk_add? Default: False. 
        order_by_fields : list, optional
            A list of field names by which to order the query list.
        template : template object or filename, optional
            Template used to render the list. By default, Templates.LIST is used.
        **kwargs : 
            additional filter parameters to be used by query().filter 
        """

        self.Model = Model
        if hasattr(Model, 'kyk_STATUS'):
            self.kyk_STATUS = Model.kyk_STATUS
        # query has to be callable! (Otherwise the instance would be reusing 
        # the same querylist over and over again.)
        self.query = Model.objects.all if query is None else query
        self.initial = kwargs if use_kwargs else initial
        self.order_by_fields = order_by_fields
        if template is not None:
            self.kyk_TEMPLATE = template
        self.filters = kwargs

    def kyk_in(self, request, index=0, size=20, order_by_field=None, **kwargs):
        """
        List a set of kyks.
        The GET parameter ``index`` and ``size`` can be used to select
        a range ``[index:index+size]`` of kyks from the list.
        One can specify a list of fields by which to order that will
        be passed on the the ``order_by`` QuerySet method.
        If no list of fields is supplied, the default ordering as defined in
        Model.Meta.ordering is used.
        """
        index = int(request.GET.get('index', index))
        size = int(request.GET.get('size', size))
        #order_by_fields = request.GET.get('order_by_fields', order_by_fields)
        kyk_list = self.query().filter(**self.filters) if self.filters else self.query()
        order_by_fields = [order_by_field, ] + self.order_by_fields if order_by_field else self.order_by_fields 
        if order_by_fields:
            kyk_list = kyk_list.order_by(*order_by_fields)
        previous_index = index - size
        if previous_index < 0 < index:
            previous_index = 0
        next_index = index + size
        if next_index < kyk_list.count():
            kyk_list = kyk_list[index:next_index]
        else:
            kyk_list = kyk_list[index:]
            next_index = 0
        kwargs.update(previous_index=previous_index,
                     next_index=next_index,
                     size=size,
                     kyk_list=kyk_list,
                     kyk_add=self.kyk_add,
                     kyk=self,
                     )    
        return self.kyk_TEMPLATE, kwargs 

    #@Action.apply()
    def kyk_add(self):
        """
        Defines an action that adds a new kyk to the list.
        """
        def action(request):
            if not self.Model.kyk_create.kyk_allowed(request.user):
                return 'Forbidden'
            return self.Model.kyk_create.kyk_in(request, **self.initial)
        return action
    
#----------------------------------------------------------------------------------------------------------------------

class KykModel(KykBase, models.Model):
    """
    An abstract Django model that implements the KykBase attributes.
    """

    kyk_STATUS = Status.USER
    kyk_TEMPLATE = Templates.MODEL
    kyk_EDITING = False # Flag to indicate if the kyk is being edited.

    class Meta:
        abstract = True

    def get_field_items(self, field_names=None, *args, **kwargs):
        """
        Returns a list of (field name, field value) pairs for the fields
        listed in field_names, or for all fields if no names were given.
        """
        if field_names is None:
            field_names = self._meta.get_fields(*args, **kwargs)
        return [(field.verbose_name , getattr(self, field.name)) 
                for field in field_names]

    def get_absolute_url(self):
        app, model = self._meta.label.split('.')
        return reverse('kykmodel', 
                       kwargs={'app': app, 'model': model, 'pk': self.pk},
                       )

    @cached_classproperty
    def kyk_Identifier(cls):
        """

        Returns
        -------
        string
            Should identify the model class unambiguously and consistently
            with the same result if the page is loaded again after an action.
        """
        return cls._meta.label
        
    @cached_property
    def kyk_identifier(self):
        """

        Returns
        -------
        string
            Should identify the model instance unambiguously and consistently
            with the same result if the page is loaded again after an action.

        """
        return '{}-{}'.format(self._meta.label_lower, self.pk) 

    @cached_classproperty
    def kyk_Form(cls):
        """
        Returns a ModelForm class to create or edit the kyk.
        """
        Form = forms.modelform_factory(cls, exclude=[])
        Form.kyk_TEMPLATE = Templates.FORM
        return Form
        
    @classmethod
    def kyk_process_form(cls, action, identifier, request, *, instance=None, 
            label=None, style=None, redirection='.', FormClass = None,
            form_template=None, set_flag=None, **kwargs):
        """
        Present and process a form to create a new kyk.
        """
        # The style keyword argument is added to remove it from kwargs
        # before passing them on to kyk_process_form
        if label is None:
            label = action.title()
        submitter = '{}-{}'.format(identifier, action)
        if (request.method == 'GET') and (request.GET.get(action) == identifier):
            # Present an unbound form to create the kyk.
            posted = False
            data = files = None
        elif (request.method == 'POST') and (submitter in request.POST):
            # Process a bound form to create the kyk.
            # If it does not validate, then present it again.
            posted = True
            data = request.POST
            files = request.FILES
        else:
            # Display a button that calls to action.
            return KykGetButton(action, identifier, label=label)
        if FormClass is None:
            FormClass = cls.kyk_Form
        form = FormClass(data=data, files=files, prefix=submitter, instance=instance, **kwargs)
        if posted and form.is_valid():
            kyk = form.save()
            return kyk.kyk_post_save(request, action, redirection)
        if form_template is None:
            form_template = getattr(form, 'kyk_TEMPLATE', Templates.FORM)
        form_context = {
            'form': form,
            'submitter': submitter, 
            'submit_label': "Save",
            'cancel_label': "Cancel",
            }
        if style is not None:
            form_context['style'] = style
        # If an instance is being edited, then set its kyk_EDITING attribute 
        if instance and set_flag:
            setattr(instance, set_flag, True)
        return form_template, form_context


    def kyk_post_save(self, request, action, redirection):
        """
        Method called by kyk_process_form if the form was valid
        and the kyk was saved succesfully.
        This can be used to set attributes on request.user or in the session.
        Should return the kyk or redirect to another page.
        """
        if redirection is None:
            return self
        elif redirection == 'new':
            raise Redirection(self)
        else:
            raise Redirection(redirection)


    @Action.apply(Status.EDITOR)
    @classmethod
    def kyk_create(cls, request, **kwargs):
        """
        Present and process a form to create a new kyk.
        """
        return cls.kyk_process_form('Create', cls.kyk_Identifier, request, 
            initial=kwargs, label="Create {}".format(cls.__name__))

    @Action.apply(Status.EDITOR)
    def kyk_edit(self, request, **kwargs):
        """
        Present and process a form to edit this kyk.
        """
        return self.kyk_process_form('Edit', self.kyk_identifier, request, 
            instance=self, initial=kwargs, set_flag='kyk_EDITING',
            )

    @Action.apply(Status.EDITOR)
    def kyk_delete(self, request, form_template=Templates.FORM, redirection=None, **kwargs):
        """
        Present and process a form to delete this kyk.
        """
        action = 'Delete'
        submitter = '{}-{}'.format(self.kyk_identifier, action)
        if (request.method == 'GET') and (request.GET.get(action) == self.kyk_identifier):
            alert = gettext_lazy("Are you sure you want to delete this item?")
            kwargs.update(alert=alert, submitter=submitter, submit_label="Confirm", 
                          cancel_label="Cancel")
            return form_template, kwargs
        elif (request.method == 'POST') and (submitter in request.POST):
            # Delete the kyk and its leaf.
            if redirection is None:
                redirection = self.kyk_get_superior() 
            try: 
                self.delete()
            except IntegrityError:
                return html.format_html('<p><span class="alert label">{}</span></p>', 
                    gettext_lazy("This item could not be deleted."),
                    )
            else: # try succeeded
                raise Redirection(redirection)
        else:
            # Display a button that calls to action.
            return KykGetButton(action, self.kyk_identifier)

    def kyk_get_superior(self):
        """
        Return a kyk that can be considered as the object to which instances 
        of this model belong. 
        This is used by KykModel.kyk_delete for redirection upon deletion.
        by default, a KykList(KykModel) is used as superior.         
        """
        return KykList(self.__class__)


#======================================================================================================================

def url_with_get(action, code, *, url='.'):
    return "{}/?{}={}".format(url.rstrip('/'), action, code)


#----------------------------------------------------------------------------------------------------------------------

def KykGetButton(action, code, label=None, *, url='.'):
    """
    Creates a string that displays a GET button with a given label that produces a GET request with query ?action=code.
    This can be used as the return result for kyk actions.
    """
    template_string = '<a class="button" href="{}">{}</a>'
    complete_url = url_with_get(action, code, url=url)
    if label is None:
        label = gettext_lazy(action.replace('_', ' ').title()) 
        # gettext_lazy translates the string
    return html.format_html(template_string, complete_url, label)


#======================================================================================================================

def KykPostButton(code, label, *, url='.', cancel_label='', **kwargs):
    """
    Displays a POST button with a given label that produces a POST request with code as submit code.
    This can be used as the return result for kyk actions.
    """
    kwargs.update(submit_code=code, submit_label=label, destination_url=url, cancel_label=cancel_label)
    return Templates.FORM, kwargs


#======================================================================================================================
