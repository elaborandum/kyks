"""
Some general-purpose classes, functions and/or decorators that might be useful for other apps as well.
"""

from django.conf import settings
from django.db import models as django_models
from django.template import Template
from django.template.loader import get_template


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
        return django_models.CharField(max_length=self.max_length, choices=self.choices, *args, **kwargs)

    def __all_keys__(self):
        """
        Return a list of all codes defined in the list of choices.
        """
        return [code for code, label in self.choices]


#======================================================================================================================

def template_from_file(filename):
    """
    Returns a Django template object created from the contents of a file.
    """
    return get_template(filename).template
    # get_template returns a template enginge object whose template attribute is the
    # Template object that we want.


#----------------------------------------------------------------------------------------------------------------------

class lazy_Template:
    """
    Descriptor that loads a template file and converts it into a Template object
    on first use, i.e. after all apps are ready.
    """

    def __init__(self, source=None, filename=None):
        self.source = source
        self.filename = filename
        
    def __set_name__(self, owner, name):
        self.name = name
        
    def __get__(self, instance, cls=None):
        template = template_from_file(self.filename) if self.source is None else Template(self.source)
        setattr(cls, self.name, template)
        return template


#======================================================================================================================

class instantiate:
    """
    A decorator that replaces a class by an instance of itself.
    *note:* be careful with super() because python2 style super in methods will break!
    """
    
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        
    def __call__(self, cls):
        return cls(*self.args, **self.kwargs)


#----------------------------------------------------------------------------------------------------------------------

def is_classmethod(method):
    """
    Is method a classmethod?
    It basically tests if method.__self__ exists and is a class which is True for classmethods
    and False for ordinary functions and methods, properties and staticmethods.
    """
    return isinstance(getattr(method, '__self__', None), type)


#----------------------------------------------------------------------------------------------------------------------

class cached_classproperty:
    """
    Decorator that converts a method with a single cls argument into a property cached on the class.

    When not used as a decorator, the optional ``name`` argument allows to make cached properties of other methods 
    (e.g.  url = cached_property(get_absolute_url, name='url') )
    """
    def __init__(self, method, name=None):
        self.method = method
        self.name = name or method.__name__
        self.__doc__ = getattr(method, '__doc__', "Cached class property of method {}".format(self.name))
        # Should we copy other attributes from vars(method)?

    def __get__(self, instance, cls=None):
        res = self.method(cls)
        setattr(cls, self.name, res)
        return res


#======================================================================================================================

def get_derived_classes(cls, include_self=True):
    """
    generator that iterates over all classes that derive from cls (subclasses, subsubclasses, etc.)
    """
    if include_self:
        yield cls
    for subcls in sorted(cls.__subclasses__(), key=lambda x: x.__name__):
        yield from get_derived_classes(subcls)


#======================================================================================================================

class InnerClassMeta(type):
    """
    Metaclass that turns classes inside classes into inner-class instances when called from an outer-class instance, 
    with the outer-class instance passed on as the only argument to the inner-class __init__ method.
    Example::

        class A:
            class B(metaclass=InnerClassMeta):
                def __init__(self, a):
                    self.a = a
    
        a = A()
        # Now a.B is an instance of class B, initialized as B(a). E.g.:
        a.B.a is a
        # Result: True
        
    """    
    
    def __get__(cls, instance=None, owner=None):
        # This method was inspired by cached_property.__get__
        if instance is None:
            return cls
        # On the instance, we replace the inner class with an instance of the inner class, 
        # initialized with the instance of the outer class.    
        obj = instance.__dict__[cls.__name__] = cls(instance)
        return obj


#======================================================================================================================
