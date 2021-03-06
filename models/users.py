from django import forms
from django.contrib import auth
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

from ..exceptions import Redirection
from ..utils import cached_classproperty

from .base import Status, Templates, Kyks, KykBase
from .actions import simple_action, ButtonAction, KykGetButton


#======================================================================================================================

class AbstractKykUser(KykBase, AbstractUser):
    """
    A variant of the default user model that allows to treat user objects as kyks,
    and that assigns a status value to each user.
    
    This is an abstract model. The idea is that you derive a user class from it in your project,
    and designate that one as AUTH_USER_MODEL in settings.py.
    """    

    kyk_STATUS = Status.STAFF  # only staff has implicit access to the action methods 
    #kyk_TEMPLATE = Templates.USER

    status = Status.USER # Default user status, will be overwritten by an instance attribute upon login.

    class Meta:
        abstract = True        

    @cached_classproperty
    def UserCreationForm(cls):
        """
        We have to adjust the UserCreationForm to the new user model.
        """
        from django.contrib.auth.forms import UserCreationForm as DjangoForm # We can not import this earlier on.
        class UserCreationForm(DjangoForm):
            class Meta(DjangoForm.Meta):
                model = cls
                # fields = DjangoForm.Meta.fields
        return UserCreationForm
    
    @cached_classproperty
    def UserChangeForm(cls):
        """
        We have to adjust the UserChangeForm to the new user model.
        """
        from django.contrib.auth.forms import UserChangeForm as DjangoForm # We can not import this earlier on.
        class UserChangeForm(DjangoForm):
            class Meta(DjangoForm.Meta):
                model = cls
                # fields = DjangoForm.Meta.fields
        return UserChangeForm


#----------------------------------------------------------------------------------------------------------------------

class KykUser(AbstractKykUser):
    """
    A variant of the default user model that allows to treat user objects as kyks,
    and that assigns a status value to each user.
    
    Set AUTH_USER_MODEL = 'kyks.KykUser' in settings.py to use this as your user class.
    """    


#======================================================================================================================

@Kyks.append
class Users(KykBase):
    """
    A static kyk that handles user login/logout and status changes.
    """

    kyk_ACTION_STATUS = Status.PUBLIC
    kyk_TEMPLATE = Templates.USERS
    kyk_FORM_TEMPLATE = Templates.FORM
    # template = Template("My name is {{ request.user.username }}.")
    
    @ButtonAction.apply()    
    def register(self, request, data, submitter, **kwargs):
        """
        Registers a new user.
        """
        form = auth.get_user_model().UserCreationForm(data=data, prefix=submitter)
        if form.is_valid():
            form.save()
            new_user = auth.authenticate(username=form.cleaned_data['username'],
                                         password=form.cleaned_data['password1'],
                                         )
            login(request, new_user)
            raise Redirection('.')
        else:
            kwargs.update(form=form, submitter=submitter, submit_label=_("Save"), cancel_label=_("Cancel"))
        return self.kyk_FORM_TEMPLATE, kwargs

    @ButtonAction.apply()    
    def login(self, request, data, submitter, **kwargs):
        """
        Log the user in.
        """
        form = auth.forms.AuthenticationForm(request, data=data, prefix=submitter)
        if form.is_valid():                
            # AuthenticationForm.clean contains the following line::
            #     self.user_cache = authenticate(self.request, username=username, password=password)
            # So if the user has been validated, its user object will be available as form.user_cache
            login(request, form.user_cache)
            raise Redirection('.')
        else:
            kwargs.update(form=form, submitter=submitter, submit_label=_("Log in"))
            return Templates.FORM, kwargs
        
    @simple_action()    
    def logout(self, request, *args, **kwargs):
        """
        Log the user out.
        """
        submitter = self.kyk_identifier + ':logout'
        if (request.method == 'POST') and (submitter in request.POST):
            logout(request)
            raise Redirection('.')
        else:
            kwargs.update(submitter=submitter, submit_label=_("Log out"))
            return Templates.FORM, kwargs

    @simple_action()
    def loginout(self, request, *args, **kwargs):
        return self.login(request, *args, **kwargs
            ) if request.user.is_anonymous else self.logout(request, *args, **kwargs)

    @simple_action()
    def edit_button(self, request, *args, **kwargs):
        action = 'edit'
        return KykGetButton(action, self.kyk_identifier, label=_("Profile"),)# url=self.get_absolute_url())

    @ButtonAction.apply()
    def edit(self, request, data, submitter, **kwargs):
        form = auth.get_user_model().UserChangeForm(data=data, prefix=submitter, instance=request.user)
        if form.is_valid():
            form.save()
        else:
            kwargs.update(form=form, submitter=submitter, submit_label=_("Save"), cancel_label=_("Cancel"))
        return self.kyk_FORM_TEMPLATE, kwargs

    @simple_action()
    def change_status(self, request, *args, **kwargs):
        """
        Show a form that allows the user to change his status.
        """
        action = 'setstatus'
        submitter = '{}-{}'.format(self.kyk_identifier, action)
        if (request.method == 'POST') and (submitter in request.POST):
            data = request.POST
        else:
            data = None
        form = KykStatusForm(request, data=data, prefix=self.kyk_identifier)
        if form.is_valid():
            form.save()
            raise Redirection('.')
        else:
            kwargs.update(form=form, submitter=submitter, submit_label=_("Set status"))
        return form.kyk_TEMPLATE, kwargs
    

#======================================================================================================================

def set_user_status(user, session={}):
    if not user.is_authenticated:
        user.max_status = Status.HUMAN if session.get('is_human', False) else Status.PUBLIC
    elif user.is_superuser:
        user.max_status = Status.ADMINISTRATOR
    elif user.is_staff:
        user.max_status = Status.AGENT
    else:
        user.max_status = Status.USER
    user.status = min(session.get('status', Status.USER), user.max_status)


#----------------------------------------------------------------------------------------------------------------------

def login(request, user):
    auth.login(request, user)                  
    set_user_status(request.user, request.session)


#----------------------------------------------------------------------------------------------------------------------

def logout(request):
    auth.logout(request)                  
    set_user_status(request.user, request.session)


#======================================================================================================================

class KykStatusForm(forms.Form):
    
    kyk_TEMPLATE = Templates.FORM
    
    status = forms.TypedChoiceField(coerce=int, label=_("Select status"), label_suffix=":", required=True)
    
    def __init__(self, request, data=None, *args, **kwargs):
        super().__init__(data=data, *args, **kwargs)
        self.fields['status'].initial = request.user.status
        self.request = request
        self.fields['status'].choices = Status.choices(maximum=request.user.max_status)

    def save(self):
        """
        Stores the mood in the session.
        One should call this only if form.is_valid(),
        otherwise a KeyError will occur ('mood' not in form.cleaned_data)
        """
        status = self.cleaned_data['status']
        if self.request.user.status != status:
            self.request.session['status'] = status
            set_user_status(self.request.user, self.request.session)


#======================================================================================================================

