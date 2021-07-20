# The kyks module


## What are kyks?

A kyk is any object that has a `kyk_in` method with the following
signature:

```python
    def kyk_in(self, request, context, style, template=None, *args, **kwargs):
        ...
        return template, local_context
        # or
        return "... text ..."
```

Then this object can be called from a template with the `kykin` tag:

```
    {% kykin kyk %}
    {% kykin Kyks.contact style=Styles.BRIEF %}
```

The latter will render the kyk `Kyks['contact']` inside the template,
in the specified style. 

The `kyk_in` method should return either a plain string or a (template,
local_context) pair that will be rendered by the render_to_string
method, so that the content can be included in the template where the
kyk was called from.


## Etymology

**view → look → kijk → kÿk → kyk** :smile:

> "Although that way may not be obvious at first unless you're Dutch."
>
> Tim Peters, The Zen of Python


## Simple kyks

The easiest way to define a kyk is to create an instance of the KykSimple
class with a name, a template and optional keyword arguments.

```python
    from kyks.model import KykSimple

    menu = KykSimple('mainmenu', 
          'my_site/mainmenu.html',
          # Using .all and not .all() here so that the queries are executed 
          # when this kyk is displayed in a template and not when it is created.
          stories=Stories.objects.all,
          )
```

This creates the object `Kyks['mainmenu']` that can be called from templates
as `{% kykin Kyks.mainmenu %}`. The keyword arguments are added to the 
KykSimple object as object attributes, to make them easily accessible
in the templates, e.g. 
`{% for story in Kyks.mainmenu.stories %} ... {% endfor %}`

When used in a template, tag `{% kykin Kyks.mainmenu %}` will render the
`menu` object using the template provided when we created the object. 

Note that the `kykin` tag renders a template inside a template, 
** nested templates **. But it does more than that. It actually calls
`menu.kykin` to render the object, so it act as a view inside a view,
**nested views**, which is what the kyks module is all about.


## The KykBase mixin

```python
    from kyks.model import KykBase

    class Anchovy(KykBase):
        kyk_TEMPLATE = 'myapp/an_appallingly_dull_template.html'

```

The KykBase class automatically provides the `Anchovy` class with a 
`kyk_in` method that will render the template with the template 
variable `kyk` referring to the instance of the class, so that 
additional attributes can be sourced.

The KykBase class does not provide an `__init__` or `__new__` method, so
it can safely be used as a mixin. 
Note that all kyk related attributes and methods start with `kyk_` in
order to minimize collisions with other classes when KykBase is used as
a mixin.


## KykModel

The KykModel class combines the  `django.db.models.Model` class with 
the `KykBase` mixin and adds a number of actions to facilitate database 
operations, like creating, editing and deleting model data.


## Actions

Actions are methods on kyk that implement actions, typically by
presenting and processing a form. A typical example is the `kyk_create`
action for KykModel kyks.

The action method should behave in a similar way as the `kyk_in` method.
In fact, `kyk_in` is the default value for the `action` keyword when the
`kykin` tag is used. So, the action method should process the request and
context inputs, and return a string-like object or a template, context
pair:

```
    {% kykin kyk.my_action %}
```

This will call the method `kyk.my_action(request, context, *args, **kwargs)`.

A simple way to create actions is the `simple_action` decorator:

```python
from kyks.models import Status, KykModel, simple_action

class Purchase(KykModel):

    @simple_action()
    def set_currency(self, request):
        """
        Sets the last_currency value in the session.
        """
        ...
```

This autmatically adds a `kyk_in` attribute to `purchase.set_currency`
that displays a button with the label `Set Currency` or that 
executes the action if the button was pressed.

To separate the button from the output of the action,
one can use the `@ButtonAction.apply()` decorator:

```python
from kyks.models import Status, KykModel, simple_action, ButtonAction

class Purchase(KykModel):

    @ButtonAction()
    def set_currency(self, request):
        """
        Sets the last_currency value in the session.
        """
        ...
```
and then in the template:
```
<div class='buttons'>
  {% kykin kyk.action1.button %}
  {% kykin kyk.action2.button %}
  {% kykin kyk.action3.button %}
</div>
<div class='results'>
  {% kykin kyk.action1.result %}
  {% kykin kyk.action2.result %}
  {% kykin kyk.action3.result %}
<div class='buttons'>
```


# Status

The `KykUser`class adds the `KykBase` mixin to the 
`django.contrib.auth.models.AbstractUser` class, but it does more than that.
It also adds `status` and `max_status` attributes to the user model.
These attributes control which kyks and which actions will be presented
to each user. 

If no user is logged in, then the lowest value, `Status.PUBLIC`, is
assumed. Once logged in, a user can change its status to `Status.USER`
or other values as defined by the `KYK_STATUS` list in the settings module,
e.g.:

```python
KYK_STATUS = [
    # Defines status values that are used to determine the access restrictions.
    # The implementation of the restrictions can differ from class to class
    # and depend on the implementation of the kyk_in and action methods.
    # The explanation after each value is only a guideline
    # that is used as the default value in many cases
    # but probably is changed in many applications.
    # E.g. to write comments one could requires HUMAN or USER status,
    # while adding items to the home page might require ADMINISTRATOR status.
    'PUBLIC',         # Standard displaying of contents.
    'HUMAN',          # Not a robot (catchpa?)
    'USER',           # For authenticated users.
    'CLIENT',         # can review own purchases. 
    'STAFF',          # can see and do some more stuff 
    'TRANSLATOR',     # can translate existing translatable kyks
    'EDITOR',         # can create, edit, move and delete existing kyks
    'AGENT',          # can create and edit business objects
    'DIRECTOR',       # can create, edit, delete and move business objects
    'ADMINISTRATOR',  # Allow advanced edit buttons
]
```
These values can be accessed as `Status.<key>` in templates and in code 
that imports the `Status` object.

```python
from kyks.models import Status
```

The status variable can easily be used to configure access to certain 
actions using a decorator:

```python
from kyks.models import Status, KykModel, simple_action

class Purchase(KykModel):

    @simple_action(Status.STAFF)
    def set_currency(self, request):
        """
        Sets the last_currency value in the session.
        """
        ...
```


# Styles

The settings file should also define a list of style codes:

```python
KYK_STYLES = [
    # Defines style values to display kyks.
    # If a kyk does not define a style, 
    # the style with the nearest lower value will be applied.   
    # 
    # Styles that can be rendered using only kyk.__str__:
    'TEXT',
    'LINK',
    'BUTTON',
    # Styles that might need wider access to kyk:
    'CELL', # displaid as a table cell (might allow edit/delte actions) = 'as_table'
    'ITEM', # displaid as a list item (might allow edit/delte actions) = 'as_li'
    'QUOTE', # Summary without actions = 'as_p'
    'SHOW', # Summary that allows actions
    'PAGE',
]
```

It is supposed that a kyk\'s `kyk_in` method or its template know how to
render different styles.

