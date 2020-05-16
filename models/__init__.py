from .base import (Choices,  ParameterDict, Status, Styles, Templates, Kyks, 
                   restrict, allow_author, KykBase, KykSimple, KykModel, 
                   template_from_string, KykGetButton, KykPostButton,
                   )
from users import AbstractKykUser, KykUser, Users, set_user_status, login, logout

Kyks['users'] = Users()


#======================================================================================================================
