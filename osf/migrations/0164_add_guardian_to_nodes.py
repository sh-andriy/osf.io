# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-08-27 21:07
from __future__ import unicode_literals

from math import ceil

import logging
from django.db import migrations, connection

logger = logging.getLogger(__name__)

"""
NODE MIGRATION
1) Creates three django groups for each existing abstract node (admin/write/read)
2) Gives admin groups admin/write/read perms, write groups write/read, and read: read
 - Populates osf NodeGroupObjectPermission (DFK) table instead of out-of-the-box guardian GroupObjectPermission table
3) Adds node contributors to corresponding django groups - a node write contributor is added to the node's write django group
 - Populates OSFUserGroups table with group id/user id pair
"""

def reverse_guardian_migration(state, schema):
    sql = """
        -- Drop NodeGroupObjectPermission table - table gives node django groups
        -- permissions to node
        DELETE FROM osf_nodegroupobjectpermission;

        -- Remove user membership in Node read/write/admin Django groups
        DELETE FROM osf_osfuser_groups
        WHERE group_id IN (
          SELECT id
          FROM auth_group
          WHERE name LIKE '%' || 'node_' || '%'
        );

        -- Remove admin/write/read node django groups
        DELETE FROM auth_group
        WHERE name LIKE '%' || 'node_' || '%';
        """

    with connection.cursor() as cursor:
        cursor.execute(sql)

# Forward migration - for each node, create a read, write, and admin Django group
add_node_read_write_admin_auth_groups = """
    INSERT INTO auth_group (name)
    SELECT regexp_split_to_table('node_' || N.id || '_read,node_' || N.id || '_write,node_' || N.id || '_admin', ',')
    FROM osf_abstractnode N
    WHERE N.id > {start} AND N.id <= {end};
    """

# Forward migration - add read permissions to all node django read groups, add read/write perms
# to all node django write groups, and add read/write/admin perms to all node django admin groups
add_permissions_to_node_groups = """
    -- Adds "read_node" permissions to all Node read groups - uses NodeGroupObjectPermission table
    INSERT INTO osf_nodegroupobjectpermission (content_object_id, group_id, permission_id)
    SELECT N.id as content_object_id, G.id as group_id, PERM.id AS permission_id
    FROM osf_abstractnode AS N, auth_group G, auth_permission AS PERM
    WHERE G.name = 'node_' || N.id || '_read'
    AND PERM.codename = 'read_node'
    AND N.id > {start}
    AND N.id <= {end};

    -- Adds "read_node" and "write_node" permissions to all Node write groups
    INSERT INTO osf_nodegroupobjectpermission (content_object_id, group_id, permission_id)
    SELECT N.id as object_pk, G.id as group_id, PERM.id AS permission_id
    FROM osf_abstractnode AS N, auth_group G, auth_permission AS PERM
    WHERE G.name = 'node_' || N.id || '_write'
    AND (PERM.codename = 'read_node' OR PERM.codename = 'write_node')
    AND N.id > {start}
    AND N.id <= {end};

    -- Adds "read_node", "write_node", and "admin_node" permissions to all Node admin groups
    INSERT INTO osf_nodegroupobjectpermission (content_object_id, group_id, permission_id)
    SELECT N.id as object_pk, G.id as group_id, PERM.id AS permission_id
    FROM osf_abstractnode AS N, auth_group G, auth_permission AS PERM
    WHERE G.name = 'node_' || N.id || '_admin'
    AND (PERM.codename = 'read_node' OR PERM.codename = 'write_node' OR PERM.codename = 'admin_node')
    AND N.id > {start}
    AND N.id <= {end};
    """

# Forward migration - for every contributor that has read perms only to a node,
# add that contributor to the node's read group - this allows us to start using
# guardian to track which permissions a contributor has.
add_read_contribs_to_read_groups = """
    -- Add users with read permissions only on the node to the node's read group
    INSERT INTO osf_osfuser_groups (osfuser_id, group_id)
    SELECT C.user_id as osfuser_id, G.id as group_id
    FROM osf_abstractnode as N, osf_contributor as C, auth_group as G
    WHERE C.node_id = N.id
    AND C.read = TRUE
    AND C.write = FALSE
    AND C.admin = FALSE
    AND G.name = 'node_' || N.id || '_read'
    AND N.id > {start}
    AND N.id <= {end};
    """

# Forward migration - for every contributor that has write and read perms to a node,
# add that contributor to the node's write group - this allows us to start using
# guardian to track which permissions a contributor has.
add_write_contribs_to_write_groups = """
    -- Add users with write permissions on node to the node's write group
    INSERT INTO osf_osfuser_groups (osfuser_id, group_id)
    SELECT C.user_id as osfuser_id, G.id as group_id
    FROM osf_abstractnode as N, osf_contributor as C, auth_group as G
    WHERE C.node_id = N.id
    AND C.read = TRUE
    AND C.write = TRUE
    AND C.admin = FALSE
    AND G.name = 'node_' || N.id || '_write'
    AND N.id > {start}
    AND N.id <= {end};
    """

# Forward migration - for every contributor that has admin/write/read perms to a node,
# add that contributor to the node's admin group - this allows us to start using
# guardian to track which permissions a contributor has.
add_admin_contribs_to_admin_groups = """
    -- Add users with admin permissions on the node to the node's admin group
    INSERT INTO osf_osfuser_groups (osfuser_id, group_id)
    SELECT C.user_id as osfuser_id, G.id as group_id
    FROM osf_abstractnode as N, osf_contributor as C, auth_group as G
    WHERE C.node_id = N.id
    AND C.read = TRUE
    AND C.write = TRUE
    AND C.admin = TRUE
    AND G.name = 'node_' || N.id || '_admin'
    AND N.id > {start}
    AND N.id <= {end};
    """

def migrate_nodes_to_guardian(state, schema):
    AbstractNode = state.get_model('osf', 'abstractnode')
    max_nid = getattr(AbstractNode.objects.last(), 'id', 0)
    increment = 100000

    migrations = [
        {'sql': add_node_read_write_admin_auth_groups, 'description': 'Creating node admin/write/read django groups:'},
        {'sql': add_permissions_to_node_groups, 'description': 'Adding permissions to node django groups:'},
        {'sql': add_read_contribs_to_read_groups, 'description': 'Adding node read contribs to read django groups:'},
        {'sql': add_write_contribs_to_write_groups, 'description': 'Adding node write contribs to write django groups:'},
        {'sql': add_admin_contribs_to_admin_groups, 'description': 'Adding node admin contribs to admin django groups:'}
    ]

    for migration in migrations:
        total_pages = int(ceil(max_nid / float(increment)))
        page_start = 0
        page_end = 0
        page = 0
        logger.info('{}'.format(migration['description']))
        while page_end <= (max_nid):
            page += 1
            page_end += increment
            if page <= total_pages:
                logger.info('Updating page {} / {}'.format(page_end / increment, total_pages))
            with connection.cursor() as cursor:
                cursor.execute(migration['sql'].format(
                    start=page_start,
                    end=page_end
                ))
            page_start = page_end
    logger.info('Finished adding guardian to nodes.')
    return

class Migration(migrations.Migration):

    dependencies = [
        ('osf', '0163_migrate_preprints_to_direct_fks'),
    ]

    operations = [
        migrations.RunPython(migrate_nodes_to_guardian, reverse_guardian_migration),
    ]
