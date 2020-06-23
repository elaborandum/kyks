from django.apps import apps
from django.http import Http404
from django.shortcuts import render

from .exceptions import Reload, ReloadAsGet
from .models import Templates, Kyks, KykList, KykModel


#======================================================================================================================

def KykView(arg=None, template=Templates.PAGE):
    """
    Factory that creates views for generic KykModel kyks.
    If arg is a KykModel: renders specific kyks or a list of kyks from that model.
    If arg is a string: the view will ask for a model name and renders specific
    kyks o a list o kyks from the model with that name in the app named <arg>.
    If arg is None: the view will ask for an app name and a model name and 
    render specific kyks o a list o kyks from the model with that name in that app.
    Otherwise, arg is assumed to be a valid kyk and the view will render that kyk.
    By default, the ``Templates.PAGE`` template will be used for rendering,
    unless another template is provided.
    """
    if isinstance(arg, type) and issubclass(arg, KykModel):
        kykModel = arg
        def view(request, pk=None, **kwargs):
            return kyk_render(request, kykModel, pk=pk, template=template, **kwargs)
    elif apps.is_installed(arg): # arg is the name of an app:
        app = arg
        def view(request, model, pk=None, **kwargs):
            kykModel = apps.get_model(app, model)
            return kyk_render(request, kykModel, pk=pk, template=template, **kwargs)
    elif arg is None:
        def view(request, app, model, pk=None, **kwargs):
            kykModel = apps.get_model(app, model)
            return kyk_render(request, kykModel, pk=pk, template=template, **kwargs)
    else: # arg is a regular kyk or the key pointing to a regular kyk in Kyks
        def view(request, **kwargs):
            return safe_render(request, kyk=Kyks.get(arg, arg), template=template, **kwargs) 
    return view


#----------------------------------------------------------------------------------------------------------------------

def kyk_render(request, kykModel, pk=None, **kwargs):
    """
    View that renders a specific kyk or a list of kyks from the given model.
    """
    kyk = KykList(kykModel) if pk is None else kykModel.objects.get(pk=pk)
    return safe_render(request, kyk, **kwargs)


#----------------------------------------------------------------------------------------------------------------------

def safe_render(request, kyk, template, *, RELOADS=3, **kwargs):
    """
    Render the request using a template with the kyk in its context. 
    The rendering is tried ``RELOADS`` times in order to catch redirections.
    """
    for it in range(RELOADS):
        kwargs.update(kyk=kyk)
        try:
            return render(request, template, context=kwargs)
        except ReloadAsGet as reload:
            request.method = 'GET'
            request.POST = {}
            kyk, template = reload.kyk or kyk, reload.template or template
        except Reload as reload:
            kyk, template = reload.kyk or kyk, reload.template or template
    else: # for it in range(RELOADS):
        # If render did not work like it should after 3 iterations, then show the error page.
        raise Http404()


#======================================================================================================================
        