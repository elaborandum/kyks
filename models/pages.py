from django.conf import settings
from django.db import models, transaction, IntegrityError
from django.utils import timezone
from django.utils.functional import cached_property

from mptt.models import MPTTModel, TreeForeignKey

from base import  (Status, Styles, Templates, restrict, allow_author, KykBase, 
                   KykModel, template_from_string, KykGetButton, KykPostButton,
                   )



#----------------------------------------------------------------------------------------------------------------------

#======================================================================================================================

class Panel(KykBase):
    """
    Special class of kyk to allow panels in pages and adding new page items inside them.
    The ``name`` argument is used to identify the panel items in the database
    (the actual value used in the database is "<page_class>.<name>").
    """    
    
    def __init__(self, name, template=None, status=None):
        self.name = name
        if template is not None:
            self.kyk_TEMPLATE = template
        if status is not None:
            self.kyk_STATUS = status

    def __get__(self, instance, owner=None):
        """
        This method turns the panel into a descriptor, such that each access
        from a page sets the page attribute on the panel.
        """
        if instance is None:
            return self.__class__
        else:
            self.page = instance
            return self

    @cached_property
    def prefix(self):
        """
        Retruns a string that identifies the self object unambiguously and consistently
        with the same result if the page is loaded again after an action.
        """
        return "{}-{}".format(self.page.prefix, self.name)
            
    def get_children(self):
        """
        Returns an iterator over all the page items in the panel.
        """
        if hasattr(self.page, 'get_children'):
            return (child.leaf for child in self.page.get_children() if child.panel == self.name)
        else: 
            return (child.leaf for child in KykTree.objects.root_nodes().filter(panel=self.name))

    def add(self, request, style=None, **kwargs):
        """
        Provides an action to add a page item to the kyk.
        """

#======================================================================================================================

class KykTree(MPTTModel):
    """
    A tree structure (based on MPTTModel) on which page items can be attached as leaves.
    """

    # PARAMETERS:
    # ----------

    SLUGMAXLENGTH = 100

    # FIELDS:
    # ------
    
    # Tree fields:
    parent = TreeForeignKey(
        'self', on_delete=models.PROTECT, related_name='children', db_index=True, null=True, blank=True)
    panel = models.SlugField(max_length=SLUGMAXLENGTH, blank=True)
    # Content fields (should refer to models derived from AbstractLeaf, with a OneToOneKey to this model):
    leaf_name = models.SlugField() # max_length=50 by Django's default
    # Other fields
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
        
    @property
    def leaf(self):
        """
        Return the model instance that has a one-to-one relation to this kyk.
        This is a dummy field equivalent to a GenericForeignKey field.
        """
        return getattr(self, self.leaf_name)

    def save(self, leaf=None, *args, **kwargs):
        """
        Save the stem that holds the leaf. 
        Note: stem was created as stem_form.save(commit=False) and leaf as leaf_form.save(commit=False)
        Note: This does not save the leaf! To save the leaf in the database, call leaf.save!
        """
        if leaf is not None:
            self.leaf_name = self.leaf_names[leaf.__class__] #TODO: improve leaf names
        super().save(*args, **kwargs)
        if self.is_child_node():
            # We update the timestamp on all ancestors
            # because modifying a child should also count as modifying the  parent.
            self.get_ancestors(include_self=True).update(modification_date=timezone.now())


#======================================================================================================================

class PageItem(KykModel):
    """
    An abstract class from which one should derive new page item models.
    Page items can be anything you would like to put on a page, like texts, images, ... 
    """
    # All kykpage-specific methods and attributes are prepended with 'kyk_'
    # in order to minimize the risk of name collisions with other classes,
    # so that this class can be used as a mixin on existing models.

    # FIELDS:
    # ------

    kyk_stem = models.OneToOneField(
        to=KykTree,
        on_delete=models.CASCADE,
        related_name='leaf_%(app_label)s_%(class)s',
        primary_key=True, # By using this field as primeray key we save a column in the database.
        db_column='id', # The actual kyk_stem id will be stored in this field.
        # We set it explicitly to 'id' because otherwise ForeignKey to leaf classes do not work correctly
        # (unless we were to specify 'to_field=kyk_stem_id' on every Foreign Key to a Leaf Class).
        )
    # Use it sparingly because resolving it always requires an additional database query.
    # It is imperative that this field is called 'kyk_stem', because several methods depend on it!

    class Meta:
        abstract = True

    @transaction.atomic # This code executes inside a transaction.
    def save(self, stem=None, force_insert=False, force_update=False, using=None, update_fields=None, *args, **kwargs):
        """
        Save the stem and the leaf created by leaf_class.create to the database.
        Note: stem was created as stem_form.save(commit=False) and leaf as leaf_form.save(commit=False)
        """
        if stem is not None:
            stem.save(leaf=self, force_insert=force_insert, force_update=force_update, using=using)
            self.kyk_stem = stem
        super().save(
            force_insert=force_insert, force_update=force_update, using=using, update_fields=update_fields, 
            *args, **kwargs)

    @transaction.atomic # This code executes inside a transaction.
    def delete(self, using=None, keep_parents=False):
        # Explicitly delete links to the leaf:
        # for linker in LeafLink.objects.filter(link=self.kyk_stem):
        #    linker.delete(using=using)
        self.kyk_stem.delete(using=using)
        if self.pk is not None:
            super().delete(using=using, keep_parents=keep_parents)

#======================================================================================================================
