#from itertools import chain, takewhile

from django.conf import settings
from django.db import models, IntegrityError
from django import forms
from django.template import engines, TemplateSyntaxError
from django.urls import reverse
from django.utils import html
from django.utils.functional import cached_property
from django.utils.translation import gettext

from ..exceptions import Redirection
from ..utils import instantiate, cached_classproperty

#======================================================================================================================

class Choices:
    """
    User friendly choices for fields with a choice attribute.
    
    Creation of an instance requires a max_length at which to truncate the keys
    and a list of (name, label) pairs, where name should be a readable name to use in code
    and label a user friendly text that will be used by the choice widget in forms.
    In the database, the choices will be stored as a code that is equal to name[:max_length].
    Alternatively, one can provide a (code, name, label) tuple to specify the code explicitly,
    e.g. to avoid duplicate codes or to use more meaningfull codes.
    
    Usage:

        STATES = Choices(4,
                ('INACTIVE', _("Inactive")),
                ('ACTIVE', _("Active")),
                ('URGENT', _("Urgent")),
                ('DONE', _("Done")),
                ('IACC', 'INACCURATE', _('Inaccurate')),
            )

        state =  models.CharField(max_length=STATES.max_length, choices=STATES.choices, default=STATES.INACTIVE)      
        # or equivalently:
        state =  STATES.ChoiceField(default=STATES.INACTIVE)      
        
    """

    def __init__(self, max_length, *args, **kwargs):
        self.max_length = max_length
        expanded_args = [(arg[0][:max_length], arg[-2], arg[-1]) for arg in args]
        self._code = {name: code for code, name, label in expanded_args}
        if settings.DEBUG:
            if len(set(code for code, name, label in expanded_args)) != len(args):
                raise KeyError
        self.choices = [(code, label) for code, name, label in expanded_args]
        # Set optional arguments.
        for key, value in kwargs.items():
            setattr(self, key, value)
        
    def __getattr__(self, name):
        return self._code[name] if name in self._code else super().__getattribute__(name)

    def __iter__(self):
        return self.choices.__iter__()

    def __len__(self):
        return self.choices.__len__()

    def ChoiceField(self, *args, **kwargs):
        return models.CharField(max_length=self.max_length, choices=self.choices, *args, **kwargs)

    def __all_keys__(self):
        """
        Return a list of all codes defined in the list of choices.
        """
        return [code for code, label in self.choices]


#----------------------------------------------------------------------------------------------------------------------

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

@instantiate()
class Kyks(dict):
    """
    A dict that only allows objects with a kyk_in method.
    """

    def __setitem__(self, key, value):
        if not hasattr(value, 'kyk_in'):
            raise TypeError("{} does not have a kykin method".format(key))
        if key != str(key):
            raise TypeError("{} must be a string".format(key))
        if key.isdigit():
            raise TypeError("{} should not be a number".format(key))
        if key in self:
            raise Warning("Duplicate Kyk name {}".format(key))
        super().__setitem__(key, value)

    def add(self, name=None):
        """
        Decorator that adds an instance of cls to the Kyks dictionnary 
        with the given name or cls.__name__ if no name is provided.
        """
        if isinstance(name, str):
            # If the decorator was invoked as @Kyks.add('my_name')
            def decorating_name(cls):
                self[name] = cls()
                return cls
            return decorating_name 
        else:
            def decorating_class(cls):
                Kyks[cls.__name__] = cls()
                return cls
            if name is None: 
                # If the decorator was invoked as @Kyks.add()
                return decorating_class
            else:
                # If the decorator was invoked as @Kyks.add
                return decorating_class(cls=name)


#======================================================================================================================
    
def template_from_string(template_string, using=None):
    """
    Convert a string into a template object, using a given template engine
    or using the default backends from settings.TEMPLATES if no engine was specified.
    """
    # This function is based on django.template.loader.get_template, 
    # but uses Engine.from_string instead of Engine.get_template.
    # (The Engine class is defined in django.template.engine.py.)
    chain = []
    engine_list = engines.all() if using is None else [engines[using]]
    for engine in engine_list:
        try:
            return engine.from_string(template_string)
        except TemplateSyntaxError as e:
            chain.append(e)
    raise TemplateSyntaxError(template_string, chain=chain)


#======================================================================================================================

class restrict:
    """
    A decorator that restricts access to action methods based upon the status of the user.
    The user status must be greater than or equal to the given status.
    
    This decorator should always be called with parentheses::

        @restrict(Status.EDITOR)

    This limits access to the method to users with a status equal to or higher than ``Status.EDITOR``.
    The default status is ``Status.USER``, called as::
        
        @restrict()

    The original method is stored as the attribute ''bypass_restrictions'' on the
    decorated method in order to facilitate looser restrictions in subclasses.
    """

    DEFAULT_STATUS = Status.USER

    def __init__(self, status=DEFAULT_STATUS):
        self.status = status

    def __call__(self, method):
        # Retrieve the underlying method (in case the method was decorated before).
        def restricted_method(kyk, request, *args, **kwargs):
            """
            Decorator function that returns the result of a kyk action method,
            i,e. a string or a (template, context) pair.
            """
            return restricted_method.bypass_restrictions(kyk, request, *args, **kwargs
                ) if request.user.status >= self.status else ''
        # Store the original method as an attribute on the new method,
        # so that subclasses can define less strict access conditions.
        restricted_method.bypass_restrictions = method
        return restricted_method


#----------------------------------------------------------------------------------------------------------------------
    
class allow_author:
    """
    A decorator that allows a user to bypass previous restrictions
    if he is the author of a kyk and has suficient status.
    
    This decorator should always be called with parentheses and precede other resgtrictions::

        @allow_author(Status.USER)
        @restrict(Status.STAFF)

    This gives access to the method to the user who is the author of the kyk
    and has a status equal to or higher than ``Status.EDITOR``.

    The default status is ``Status.USER``, called as::
        
        @allow_author()
        @restrict()

    The default author field on the kyk is ``author``.
    This can be modified by redefining the ``AUTHOR_FIELD`` on the class
    or by passing in an additional ``author_field`` keyword to the decorator.

        @allow_author(author_field='owner')
        @restrict(Status.ADMINISTRATOR)

    The original method is stored as the attribute ''bypass_restrictions'' on the
    decorated method in order to facilitate looser restrictions in subclasses.
    """

    DEFAULT_STATUS = Status.USER
    AUTHOR_FIELD = 'author'

    def __init__(self, status=DEFAULT_STATUS, author_field=AUTHOR_FIELD):
        self.status = status
        self.author_field = author_field

    def __call__(self, method):
        # Retrieve the underlying method (in case the method was decorated before).
        if not hasattr(method, 'bypass_restrictions'):
            # The method was unrestricted so there is no use in allowing priviliged access.
            return method
        def allowed_method(kyk, request, *args, **kwargs):
            """
            Decorator function that returns the result of a kyk action method,
            i,e. a string or a (template, context) pair.
            """
            try:
                author = getattr(kyk, self.author_field)
            except AttributeError:
                return method(kyk, request, *args, **kwargs)
            else:
                return allowed_method.bypass_restrictions(kyk, request, *args, **kwargs
                    ) if (request.user == author) and (request.user.status >= self.status
                    ) else method(kyk, request, *args, **kwargs)
        # Store the original method as an attribute on the new method,
        # so that subclasses can define alternative access conditions.
        allowed_method.bypass_restrictions = method.bypass_restrictions
        return allowed_method
 
    
#======================================================================================================================

class KykBase:
    """
    This class defines minimal attributes and methods required by the kykin template tag.
    This is used by static and dynamic page kyks, but can be used by other classes as well.
    """
    # Note that KykPanel only makes sense for static and dynamic page kyks, 
    # so KykBase does not make any reference to KykPanel.

    kyk_STATUS = Status.PUBLIC
    kyk_TEMPLATE = template_from_string("{{ kyk }}")

    def kyk_in(self, request, template=None, **kwargs):
        """
        Return the template and context used to render the kyk with the kykin tag.
        """
        if template is None:
            template = self.kyk_TEMPLATE
        kwargs.update(kyk=self)
        return self.kyk_TEMPLATE, kwargs

    @classmethod
    def kyk_allowed(cls, user):
        """
        Check whether the user has sufficient status to access self (returns True or False).
        """
        return user.status >= cls.kyk_STATUS

    
#----------------------------------------------------------------------------------------------------------------------

class KykSimple(KykBase):
    """
    A simple kyk that displays a template.
    """

    def __init__(self, template):
        self.kyk_TEMPLATE = template
        
    classmethod
    def from_string(cls, template_string):
        """
        Creates a simple kyk from a template provided as a text string.
        """
        return cls(template_from_string(template_string))


#----------------------------------------------------------------------------------------------------------------------

class KykModel(KykBase, models.Model):
    """
    An abstract Django model that implements the KykBase attributes.
    """

    kyk_STATUS = Status.User
    kyk_TEMPLATE = Templates.MODEL
    kyk_FORM_TEMPLATE = Templates.FORM

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
        return reverse('kyks.kykmodel', 
                       kwargs={'app': app, 'model': model, 'pk': self.pk},
                       )

    @cached_classproperty
    def Identifier(cls):
        """

        Returns
        -------
        string
            Should identify the model class unambiguously and consistently
            with the same result if the page is loaded again after an action.
        """
        return cls._meta.label
        
    @cached_property
    def identifier(self):
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
        return forms.modelform_factory(cls)
        
    @classmethod
    def kyk_process_form(cls, action, identifier, request, *, label=None, 
            style=None, redirection='.', form_template=None, **kwargs):
        """
        Present and process a form to create a new kyk.
        Sponsor can be a model instance or a string from which this method
        was called, so that a page can include severall different kyk_add
        buttons without form prefix conflicts (because each sponsor provides
        a different prefix).
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
        form = cls.kyk_Form(data=data, files=files, prefix=submitter, **kwargs)
        if posted and form.is_valid():
            kyk = form.save()
            if redirection is None:
                return kyk
            else:
                raise Redirection(redirection)
        if form_template is None:
            form_template = cls.kyk_FORM_TEMPLATE
        form_context = {
            'form': form,
            'submitter': submitter, 
            'submit_label': label,
            'cancel_label': "Cancel",
            }
        if style is not None:
            form_context['style'] = style
        return form_template, form_context

    @classmethod
    @restrict(Status.EDITOR)
    def kyk_create(cls, request, **kwargs):
        """
        Present and process a form to create a new kyk.
        """
        return cls.kyk_process_form('Create', cls.Identifier, request, **kwargs)

    @restrict(Status.EDITOR)
    def kyk_edit(self, request, **kwargs):
        """
        Present and process a form to edit this kyk.
        """
        return self.kyk_process_form('Edit', self.identifier, request, instance=self, **kwargs)

    @restrict(Status.EDITOR)
    def kyk_delete(self, request, form_template=Templates.FORM, **kwargs):
        """
        Present and process a form to delete this kyk.
        """
        action = 'Delete'
        submitter = '{}-{}'.format(self.identifier, action)
        if (request.method == 'GET') and (request.GET.get(action) == self.identifier):
            alert = gettext("Are you sure you want to delete this item?")
            kwargs.update(alert=alert, submitter=submitter, submit_label="Confirm", 
                          cancel_label="Cancel")
            return form_template, kwargs
        elif (request.method == 'POST') and (submitter in request.POST):
            redirection_page = '.'
            # Delete the kyk and its leaf.
            try: 
                self.delete()
            except IntegrityError:
                return html.format_html('<p><span class="alert label">{}</span></p>', 
                    gettext("This item could not be deleted."),
                    )
            else: # try succeeded
                raise Redirection(redirection_page)
        else:
            # Display a button that calls to action.
            return KykGetButton(action, self.identifier)

    @classmethod   
    def kyk_list(cls, request, index=0, size=20, order_by_fields=None, 
                 template=Templates.LIST, **kwargs):
        """
        List a set of kyks.
        The GET parameter ``index`` and ``size`` can be used to select
        a range ``[index:index+size]`` of kyks from the list.
        One can specify a list of fields by which to order that will
        be passed on the the ``order_by`` QuerySet method.
        If no list of fields is supplied, the default ordering as defined in
        Model.Meta.ordering is used.
        """
        index = request.GET.get('index', index)
        size = request.GET.get('size', size)
        order_by_fields = request.GET.get('order_by_fields', order_by_fields)
        kyk_list = cls.objects.all()
        if order_by_fields is not None:
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
            )
        return template, kwargs
        

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
        label = gettext(action.title()) # gettext translates the string
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
