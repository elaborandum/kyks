#from itertools import chain, takewhile

from django.db import models, IntegrityError
from django import forms
from django.urls import reverse
from django.utils import html
from django.utils.translation import gettext_lazy

from ..exceptions import Redirection
from ..utils import cached_classproperty

from .base import Status, Templates, Kyks, KykBase, KykGetButton
from .actions import simple_action, ButtonAction


#======================================================================================================================

class KykModelIdentifier:
    """
    Returns a string that identifies the model instance unambiguously and consistently
    with the same result if the page is loaded again after an action.
    If retrieved from the class, then kyk_Identifier is returned.
    """
  
    def __get__(self, instance, cls=None):
        return cls.kyk_Identifier if instance is None else f'{cls.kyk_Identifier}-{instance.pk}' 


#----------------------------------------------------------------------------------------------------------------------

class KykModel(KykBase, models.Model):
    """
    An abstract Django model that implements the KykBase attributes.
    """

    kyk_STATUS = Status.USER
    kyk_TEMPLATE = Templates.MODEL

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
        Returns a string that should identify the model class unambiguously and 
        consistently with the same result if the page is loaded again after an action.
        """
        return cls._meta.label

    kyk_identifier = KykModelIdentifier()
    # def kyk_identifier(self):
    #     return f'{self.kyk_Identifier.lower()}-{self.pk}'

    @cached_classproperty
    def kyk_Form(cls):
        """
        Returns a ModelForm class to create or edit the kyk.
        """
        Form = forms.modelform_factory(cls, exclude=[])
        Form.kyk_TEMPLATE = Templates.FORM
        return Form
        
    @classmethod
    def kyk_process_form(cls, request, data, submitter, *, style=None, redirection='.', 
                         files=None, FormClass=None, stage=0, **kwargs):
        """
        Present and process a form to create a new kyk.
        """
        # The style keyword argument is added to remove it from kwargs
        # before passing them on to kyk_process_form
        if FormClass is None:
            FormClass = cls.kyk_Form
        form = FormClass(data=data, files=files, prefix=submitter, **kwargs)
        if form.is_valid():
            kyk = form.save()
            return kyk.kyk_post_save(request, submitter, redirection)
        form_template = getattr(form, 'kyk_TEMPLATE', Templates.FORM)
        form_context = {
            'form': form,
            'submitter': submitter, 
            'submit_label': "Save",
            'cancel_label': "Cancel",
            }
        if style is not None:
            form_context['style'] = style
        return form_template, form_context

    def kyk_post_save(self, request, submitter, redirection):
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


    @ButtonAction.apply(Status.EDITOR)
    @classmethod
    def kyk_create(cls, request, data, submitter, **kwargs):
        """
        Present and process a form to create a new kyk.
        """
        return cls.kyk_process_form(request, data, submitter, initial=kwargs)

    @ButtonAction.apply(Status.EDITOR)
    def kyk_edit(self, request, data, submitter, **kwargs):
        """
        Present and process a form to edit this kyk.
        """
        return self.kyk_process_form(request, data, submitter, instance=self, initial=kwargs)

    @simple_action(Status.EDITOR)
    def kyk_delete(self, request, form_template=Templates.FORM, redirection=None, 
                   stage=0, design='', **kwargs):
        """
        Present and process a form to delete this kyk.
        """
        action = 'Delete'
        submitter = '{}-{}'.format(self.kyk_identifier, action)
        button_design = ''
        if (request.method == 'GET') and (request.GET.get(action) == self.kyk_identifier):
            if stage == 1:
                button_design = 'disabled'
            else:
                # Here we are either in stage 0 (i.e. no stages) or in stage 2
                alert = gettext_lazy("Are you sure you want to delete this item?")
                kwargs.update(alert=alert, submitter=submitter, submit_label="Confirm", 
                              cancel_label="Cancel")
                return form_template, kwargs
        elif (request.method == 'POST') and (submitter in request.POST):
            if stage == 1:
                button_design = 'disabled'
            else:
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
        if stage <= 1:
            # Display a button that calls to action.
            return KykGetButton(action, self.kyk_identifier, design=f'{design} {button_design}')
        else: # Here we are in stage 2 but without any actions to process.
            return ''

    def kyk_get_superior(self):
        """
        Return a kyk that can be considered as the object to which instances 
        of this model belong. 
        This is used by KykModel.kyk_delete for redirection upon deletion.
        by default, a Kyks['home'] is used as superior.         
        """
        return Kyks['home']


#======================================================================================================================
