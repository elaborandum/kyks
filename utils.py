"""
Some general-purpose classes, functions and/or decorators that might be useful for other apps as well.
"""


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

