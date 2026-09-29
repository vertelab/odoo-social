# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3
"""Remove the orphaned data-binding records left behind by the move to
social_image_creator.

Why this file exists
--------------------
Commit 014801d moved the whole data-binding feature (model, fields, access
rules, views) from `social_marketing` into `social_image_creator`, to respect
the dependency direction (`social_image_creator` depends on `social_marketing`,
never the other way round). The source files moved; the *database rows* the old
module had created were never removed.

That leaves two xmlids owned by `social_marketing` that no longer exist in any
of its data files:

  * social_marketing.social_data_binding_view_list                (view 1719)
  * social_marketing.social_marketing_post_template_view_form_bindings
                                                                  (view 1720)

View 1720 is an *extension* of the post-template form (view 670). It carries
`<field name="binding_ids"/>`, and `binding_ids` is added to
`social_marketing.post.template` by `social_image_creator`. When the admin
clicks Upgrade on "Social: Marketing", Odoo validates every extension of view
670 while loading `social_marketing/views/social_marketing_post_template_views.xml`
— at that point `social_image_creator` has not been (re)loaded, so the field
does not exist on the model and the load aborts with:

    Field "binding_ids" does not exist in model "social_marketing.post.template"

Odoo's own orphan cleanup (`ir.model.data._process_end`) would normally delete
these xids, but it runs at the END of the module load — after `load_data`. The
crash happens *during* `load_data`, so the cleanup never gets the chance. It is
a deadlock: the row that breaks the upgrade is the row the upgrade would have
removed.

Hence `pre-migrate.py`, not `post-migrate.py`: this stage runs before data
loading (odoo/modules/loading.py, `migrations.migrate_module(package, 'pre')`),
which is the only place early enough to break the deadlock.

What it does
------------
Deletes exactly the two xmlids above and the two view rows they point at. The
two views only reference each other (1720's arch points at 1719's xmlid), so
they are removed as a pair; the "is it referenced elsewhere?" guard therefore
ignores references coming from within the pair itself.

The corresponding `social_image_creator` records (views 1765/1766) are the live
ones and are left alone. The model/field/access duplicates are deliberately not
touched here: they share their `res_id` with the `social_image_creator` rows, so
they are harmless aliases, and `_process_end` sweeps them once the load can
complete.

Idempotent: running it twice changes nothing the second time.
"""

import logging

_logger = logging.getLogger(__name__)

# (module, name) of the orphaned ir_model_data rows. All are ir.ui.view.
ORPHAN_XMLIDS = [
    ('social_marketing', 'social_data_binding_view_list'),
    ('social_marketing', 'social_marketing_post_template_view_form_bindings'),
]


def migrate(cr, version):
    """Delete the orphaned data-binding views owned by social_marketing.

    `version` is the version being upgraded FROM. On a fresh install it is
    falsy and there is nothing to clean.
    """
    if not version:
        return

    # Resolve the orphan xmlids to their view ids.
    cr.execute(
        """
        SELECT id, name, res_id
          FROM ir_model_data
         WHERE model = 'ir.ui.view'
           AND (module, name) IN %s
        """,
        (tuple(ORPHAN_XMLIDS),),
    )
    rows = cr.fetchall()
    if not rows:
        return

    imd_ids = [r[0] for r in rows]
    view_ids = [r[2] for r in rows if r[2] is not None]

    # Safety: refuse to delete a view that something OUTSIDE the orphan pair
    # still depends on (another xmlid on the same record, a child view, or an
    # arch reference from a different view).
    for view_id in view_ids:
        cr.execute(
            """
            SELECT 1 FROM ir_model_data
             WHERE model = 'ir.ui.view' AND res_id = %s AND id <> ALL(%s)
             LIMIT 1
            """,
            (view_id, imd_ids),
        )
        if cr.fetchone():
            _logger.warning(
                'social_marketing: view %s still has another xmlid; leaving the '
                'orphans alone', view_id)
            return

        cr.execute(
            "SELECT 1 FROM ir_ui_view WHERE inherit_id = %s LIMIT 1",
            (view_id,),
        )
        if cr.fetchone():
            _logger.warning(
                'social_marketing: view %s is inherited by another view; leaving '
                'the orphans alone', view_id)
            return

    # Arch references: only count references from views that are NOT part of
    # the orphan pair (1720 legitimately points at 1719's xmlid).
    cr.execute(
        """
        SELECT id FROM ir_ui_view
         WHERE id <> ALL(%s)
           AND (arch_db::text LIKE '%%social_marketing.social_data_binding_view_list%%'
                OR arch_db::text LIKE '%%social_marketing.social_marketing_post_template_view_form_bindings%%')
         LIMIT 1
        """,
        (view_ids or [0],),
    )
    if cr.fetchone():
        _logger.warning(
            'social_marketing: an orphan xmlid is still referenced by another '
            'view arch; leaving the orphans alone')
        return

    cr.execute("DELETE FROM ir_model_data WHERE id = ANY(%s)", (imd_ids,))
    if view_ids:
        cr.execute("DELETE FROM ir_ui_view WHERE id = ANY(%s)", (view_ids,))
    _logger.info(
        'social_marketing: removed %s orphaned data-binding view(s) moved to '
        'social_image_creator', len(view_ids))
