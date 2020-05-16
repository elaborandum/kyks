from django.apps import apps
from django.http import Http404
from django.shortcuts import render

from .exceptions import Reload, ReloadAsGet
from .models import Templates, Kyks, KykBase


#======================================================================================================================

MAX_ITERATIONS = 3


#----------------------------------------------------------------------------------------------------------------------

class KykView:
    """
    Class that creates views for generic KykModel kyks.
    ``KykView(kyk)`` creates a view that renders the kyk if kyk derives from KykBase.
    ``KykView(template)`` creates a view that renders the kyk with the
    given template (or Templates.PAGE if no template is provided).
    """
    
    template = Templates.PAGE
    kyk = None
    
    def __init__(self, arg=None):
        if isinstance(arg, KykBase):
            self.kyk = arg
        elif arg is not None:
            self.template = arg
                    
    def __call__(self, request, app=None, model=None, pk=None, **kwargs):
        """
        View function that renders the ``app.model`` instance with primary key ``pk``,
        or lists ``app.model`` objects using the kyk_list action if ``pk`` is not provided,
        or ``Kyks[app]`` if only app is provided.
        """
        if app is None:
            kyk = self.kyk
        elif model is None:
            kyk = Kyks[app]
        else:
            KykModel = apps.get_model(app, model)         
            kyk = KykModel.kyk_list if pk is None else KykModel.objects.get(pk=pk)
        return self.safe_render(request, kyk, **kwargs)        

    def safe_render(self, request, kyk, template=None, **kwargs):
        if template is None:
            template = self.template
        for it in range(MAX_ITERATIONS):
            kwargs.update(kyk=kyk)
            try:
                return render(request, template, context=kwargs)
            except ReloadAsGet as reload:
                request.method = 'GET'
                request.POST = {}
                kyk, template = reload.kyk or self.kyk, reload.template or self.template
            except Reload as reload:
                kyk, template = reload.kyk or self.kyk, reload.template or self.template
        else: # for it in range(MAX_ITERATIONS):
            # If render did not work like it should after 3 iterations, then show the error page.
            raise Http404()


#----------------------------------------------------------------------------------------------------------------------
  


#======================================================================================================================
        