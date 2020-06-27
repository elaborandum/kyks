from django import template as django_template
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.template.base import kwarg_re
from django.utils import html

from ..utils import template_from_file


#======================================================================================================================

register = django_template.Library()

# Note: the kyk argument to the template tags can be a kyk object or a string.
# In the latter case we lookup the string in the Kyks dictionary and return the corresponding kyks obejct.
# This is achieved by calling Kyks.get(kyk, kyk), which should always return a kyk object.
# (In case that kyk is not a kyk object nor a key in Kyks, one can expect AttributeErrors)


#======================================================================================================================

@register.simple_tag
def define(val=None):
    """
    Adds a variable to the context:
        
        {% define <val> as <variable name> %}
    """
    return val


#======================================================================================================================
# kykin is a helper function for KykNode.render.
# It has been split out as a separate function in order to improve readability.

def kykin(context, kyk,  using=None, *args, **kwargs):
    """
    Render a kyk with the current request and context and with the template provided by the kyk.
    Returns a string-like object.
    
    A kyk is a method or function hat takes a request as input 
    and returns either a string or a (template, extra context) pair.
    It can also be an object whose kyk_in method fits this definition,
    or a string or a function that returns a string or a (template, extra context) pair.
    
    If the user does not have enough status to access kyk, then ``None`` is returned,
    signaling to KykNode.render that no post-formatting should be applied. 
    """
    #print("kykin", kyk or '--', kwargs)
    try:
        request = context.request
    except AttributeError:
        """"
        kyks requires django.template.context_processors.request in TEMPLATE_CONTEXT_PROCESSORS
        such that the request forms part of the context
        """
        if settings.DEBUG:
            raise ImproperlyConfigured("No request found in contest!")
        else:
            return ''
    # Check if the user has permissions to access the kyk.
    if hasattr(kyk, 'kyk_allowed') and not kyk.kyk_allowed(request.user):
        return ''
    # Generate the content from the kyk.    
    if hasattr(kyk, 'kyk_in'): # kyk is a kyk instance
        content = kyk.kyk_in(request, *args, **kwargs)
    elif callable(kyk): # kyk is a function
        content = kyk(request, *args, **kwargs)
    else: # kyk is a string
        content = kyk
    # Process the content if a (template, context) pair was returned.    
    if isinstance(content, tuple):
        template, extra_context = content
        if not hasattr(template, 'render'): 
            # In this case, template should be the file name of a template.
            template = template_from_file(template)
        with context.update(extra_context):
            content = template.render(context)
    return content


#----------------------------------------------------------------------------------------------------------------------

class KykNode(django_template.Node):
    
    def __init__(self, kyk, *args, name=None, nodelist=[], **kwargs):
        self.kyk = kyk
        # name and nodelist empty unless the clause 'as <name>' was used in the tag.
        self.name, self.nodelist = name, nodelist
        self.args, self.kwargs = args, kwargs

    def render(self, context):
        args = [arg.resolve(context) for arg in self.args]
        kwargs = {key:value.resolve(context) for key, value in self.kwargs.items()}
        #result = kykin(context, self.kyk, *args, **kwargs)
        result = kykin(context, self.kyk.resolve(context), *args, **kwargs)
        # We mitigate the risk of injection attacks by escaping the result.
        # In the other branches, html.format_html and nodelist.render will apply escaping too.                    
        result = html.conditional_escape(result)
        if self.name and self.nodelist:
            with context.push(**{self.name: result}): # This assigns the result to a context variable with the saved name.  
                return self.nodelist.render(context)
        else:
            return result
        # Note on html.format_html: by default, the Django template engine renders to a html-safe string 
        # (this is not the case for other rendering engines like Jinja2).


#----------------------------------------------------------------------------------------------------------------------

@register.tag('kykin')
def do_kyk_in(parser, token):
    """
    Render a kyk with the current request and context and with the template provided by the kyk.
    
    For the specifications of <kyk>, see ``kykin.__doc__``.

    If the option ``as <name>`` is used, then the result of kyk_in is stored in the variable ``name``
    that can be used inside the block that starts with the ``kykin .. as ..`` tag and ends with ``endkyk.``

    Examples::

        {% kykin kyk style=Styles.LINK %}

        {% kykin kyk as result %}
            {% if result %}
                <dt>Result:</dt><dd>{{ result }}</dd>
            {% endif %}                
        {% endkyk %}
    """
    bits = token.split_contents()
    # tag_name = bits[0]
    kyk = parser.compile_filter(bits[1])
    bits = bits[2:]
#   name, args, kwargs = kyk_token_kwargs(remaining_bits, parser)
    name = None
    args = []
    kwargs = {}
    while bits:
        bit = bits[0]
        del bits[0]
        if (bit == 'as') and bits:
            name = bits[0]
            del bits[0]
        else:
            match = kwarg_re.match(bit)
            if match and match.group(1):
                key, value = match.groups()
                kwargs[key] = parser.compile_filter(value)
            else: # if no match or no match.group(1):
                args.append(parser.compile_filter(bit))
    if name:
        nodelist = parser.parse(('endkyk',))
        parser.delete_first_token()
    else:
        nodelist = []
    return KykNode(kyk, name=name, nodelist=nodelist, *args, **kwargs)


#======================================================================================================================

