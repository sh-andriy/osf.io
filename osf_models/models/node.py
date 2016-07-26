import urlparse

from django.core.exceptions import ValidationError
from django.db import models
from modularodm import Q
from typedmodels.models import TypedModel

from osf_models.models import MetaSchema
from osf_models.models.contributor import Contributor
from osf_models.models.mixins import Loggable
from osf_models.models.sanctions import Embargo, RegistrationApproval, Retraction
from osf_models.models.tag import Tag
from osf_models.models.user import OSFUser
from osf_models.models.validators import validate_title
from osf_models.utils.auth import Auth
from osf_models.utils.datetime_aware_jsonfield import DateTimeAwareJSONField
from website.exceptions import UserNotAffiliatedError
from .base import BaseModel, GuidMixin

from osf_models.utils.base import api_v2_url

from osf_models.app import ModelsConfig as app_config

class AbstractNode(TypedModel, Loggable, GuidMixin, BaseModel):
    """
    All things that inherit from AbstractNode will appear in
    the same table and will be differentiated by the `type` column.
    """

    CATEGORY_MAP = {
        'analysis': 'Analysis',
        'communication': 'Communication',
        'data': 'Data',
        'hypothesis': 'Hypothesis',
        'instrumentation': 'Instrumentation',
        'methods and measures': 'Methods and Measures',
        'procedure': 'Procedure',
        'project': 'Project',
        'software': 'Software',
        'other': 'Other',
        '': 'Uncategorized',
    }

    affiliated_institutions = models.ManyToManyField('Institution', related_name='nodes')
    # alternative_citations = models.ManyToManyField(AlternativeCitation)
    category = models.CharField(max_length=255,
                                choices=CATEGORY_MAP.items(),
                                default=CATEGORY_MAP[''])
    # Dictionary field mapping user id to a list of nodes in node.nodes which the user has subscriptions for
    # {<User.id>: [<Node._id>, <Node2._id>, ...] }
    # TODO: Can this be a reference instead of data?
    child_node_subscriptions = DateTimeAwareJSONField(default={})
    contributors = models.ManyToManyField(OSFUser,
                                          through=Contributor,
                                          related_name='nodes')
    creator = models.ForeignKey(OSFUser,
                                db_index=True,
                                related_name='created',
                                on_delete=models.SET_NULL,
                                null=True)
    # TODO: Uncomment auto_* attributes after migration is complete
    date_created = models.DateTimeField()  # auto_now_add=True)
    date_modified = models.DateTimeField(db_index=True, null=True)  # auto_now=True)
    deleted_date = models.DateTimeField(null=True)
    description = models.TextField()
    file_guid_to_share_uuids = DateTimeAwareJSONField(default={})
    forked_date = models.DateTimeField(db_index=True, null=True)
    forked_from = models.ForeignKey('self',
                                    related_name='forks',
                                    on_delete=models.SET_NULL,
                                    null=True)
    is_fork = models.BooleanField(default=False, db_index=True)
    is_public = models.BooleanField(default=False, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    # logs = Logs have a reverse relation to nodes
    # node_license = models.ForeignKey(NodeLicenseRecord)
    nodes = models.ManyToManyField('self', related_name='children')
    parent_node = models.ForeignKey('self',
                                    related_name='parent',
                                    on_delete=models.SET_NULL,
                                    null=True)
    # permissions = Permissions are now on contributors
    piwik_site_id = models.IntegerField(null=True)
    public_comments = models.BooleanField(default=True)
    primary_institution = models.ForeignKey(
        'Institution',
        related_name='primary_nodes',
        null=True)
    root = models.ForeignKey('self',
                             related_name='absolute_parent',
                             on_delete=models.SET_NULL,
                             null=True)
    suspended = models.BooleanField(default=False, db_index=True)
    # Tags for internal use
    system_tags = models.ManyToManyField(Tag, related_name='tagged_by_system')
    tags = models.ManyToManyField(Tag, related_name='tagged')
    # The node (if any) used as a template for this node's creation
    template_node = models.ForeignKey('self',
                                      related_name='templated_from',
                                      on_delete=models.SET_NULL,
                                      null=True)
    title = models.TextField(
        validators=[validate_title]
    )  # this should be a charfield but data from mongo didn't fit in 255
    # TODO why is this here if it's empty
    users_watching_node = models.ManyToManyField(OSFUser, related_name='watching')
    wiki_pages_current = DateTimeAwareJSONField(default={})
    wiki_pages_versions = DateTimeAwareJSONField(default={})
    # Dictionary field mapping node wiki page to sharejs private uuid.
    # {<page_name>: <sharejs_id>}
    wiki_private_uuids = DateTimeAwareJSONField(default={})

    def __unicode__(self):
        return u'{} : ({})'.format(self.title, self._id)

    @property  # TODO Separate out for submodels
    def absolute_api_v2_url(self):
        if self.is_registration:
            path = '/registrations/{}/'.format(self._id)
            return api_v2_url(path)
        if self.is_collection:
            path = '/collections/{}/'.format(self._id)
            return api_v2_url(path)
        path = '/nodes/{}/'.format(self._id)
        return api_v2_url(path)

    @property
    def absolute_url(self):
        if not self.url:
            return None
        return urlparse.urljoin(app_config.domain, self.url)

    def add_affiliated_intitution(self, inst, user, save=False, log=True):
        if not user.is_affiliated_with_institution(inst):
            raise UserNotAffiliatedError('User is not affiliated with {}'.format(inst.name))
        if inst not in self.affiliated_institutions:
            self.affiliated_institutions.add(inst)
        if log:
            from website.project.model import NodeLog

            self.add_log(
                action=NodeLog.AFFLILIATED_INSTITUTION_ADDED,
                params={
                    'node': self._primary_key,
                    'institution': {
                        'id': inst._id,
                        'name': inst.name
                    }
                },
                auth=Auth(user)
            )

    def can_view(self, auth):
        if auth and getattr(auth.private_link, 'anonymous', False):
            return self._id in auth.private_link.nodes

        if not auth and not self.is_public:
            return False

        return (self.is_public or
                (auth.user and self.has_permission(auth.user, 'read')) or
                auth.private_key in self.private_link_keys_active or
                self.is_admin_parent(auth.user))

    @property
    def comment_level(self):
        if self.public_comments:
            return 'public'
        else:
            return 'private'

    @comment_level.setter
    def comment_level(self, value):
        if value == 'public':
            self.public_comments = True
        elif value == 'private':
            self.public_comments = False
        else:
            raise ValidationError(
                'comment_level must be either `public` or `private`')

    def get_absolute_url(self):
        return self.absolute_api_v2_url

    def get_permissions(self, user):
        contrib = user.contributor_set.get(node=self)
        perm = []
        if contrib.admin:
            perm.append('admin')
        if contrib.write:
            perm.append('write')
        if contrib.read:
            perm.append('read')
        return []

    def has_permission(self, user, permission):
        return getattr(user.contributor_set.get(node=self), permission, False)

    @property
    def is_retracted(self):
        return False  # TODO wat

    @property
    def nodes_pointer(self):
        return []

    @property
    def url(self):
        return '/{}/'.format(self._id)

    # visible_contributor_ids was moved to this property
    @property
    def visible_contributor_ids(self):
        return self.contributor_set.filter(visible=True)

class Node(AbstractNode):
    """
    Concrete Node class: Instance of AbstractNode(TypedModel). All things that inherit from AbstractNode will appear in
    the same table and will be differentiated by the `type` column.

    FYI: Behaviors common between Registration and Node should be on the parent class.
    """
    pass


class Registration(AbstractNode):
    is_registration = models.NullBooleanField(default=False, db_index=True)  # TODO SEPARATE CLASS
    registered_date = models.DateTimeField(db_index=True, null=True)
    registered_user = models.ForeignKey(OSFUser,
                                        related_name='related_to',
                                        on_delete=models.SET_NULL,
                                        null=True)

    registered_schema = models.ManyToManyField(MetaSchema)

    registered_meta = DateTimeAwareJSONField(default={})
    # TODO Add back in once dependencies are resolved
    registration_approval = models.ForeignKey(RegistrationApproval, null=True)
    retraction = models.ForeignKey(Retraction, null=True)
    embargo = models.ForeignKey(Embargo, null=True)

    registered_from = models.ForeignKey('self',
                                        related_name='registrations',
                                        on_delete=models.SET_NULL,
                                        null=True)


class Collection(GuidMixin, BaseModel):
    # TODO: Uncomment auto_* attributes after migration is complete
    date_created = models.DateTimeField(null=False)  # auto_now_add=True)
    date_modified = models.DateTimeField(null=True,
                                         db_index=True)  # auto_now=True)
    is_bookmark_collection = models.BooleanField(default=False, db_index=True)
    nodes = models.ManyToManyField('Node', related_name='children')
    title = models.TextField(
        validators=[validate_title]
    )  # this should be a charfield but data from mongo didn't fit in 255

    @property
    def nodes_pointer(self):
        return self.nodes.filter(primary=False)

    @property
    def is_collection(self):
        """
        Just to keep compatibility with previous code.
        :return:
        """
        return True
