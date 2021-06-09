from django.conf import settings
from django.template import Template
from django.urls import reverse
from django.utils.functional import cached_property


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
            kyk.kyk_identifier = name
            Kyks[name] = kyk
            return cls
        return decorating_name 
    else:
        def decorating_class(cls):
            name = cls.__name__
            kyk = cls()
            kyk.kyk_identifier = name
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
    #kyk_ACTION_STATUS = Status.PUBLIC # Default required status to act on the kyk
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


#----------------------------------------------------------------------------------------------------------------------

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
        self.kyk_identifier = name
        Kyks[name] = self
        
    @classmethod
    def from_string(cls, template_string, **kwargs):
        """
        Creates a simple kyk from a template provided as a text string.
        """
        return cls(Template(template_string), **kwargs)


#======================================================================================================================

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
        def action(request, stage=0):
            if not self.Model.kyk_create.kyk_allowed(request.user):
                return 'Forbidden'
            return self.Model.kyk_create.kyk_in(request, stage=stage, **self.initial)
        return action


#======================================================================================================================
