from .models import Status, Styles, Kyks


#======================================================================================================================

def kyks(request):
    """
    Includes certain parameters by default in all RequestContext instances.    
    """ 
    return {'Styles': Styles,
            'Status': Status,
            'Kyks': Kyks,
            }