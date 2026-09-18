# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from . import models

_logger = logging.getLogger(__name__)


def _post_init_load_dashboards(env):
    """Load the social dashboards and place their menus under the Social app."""
    dashboards = [
        ("social_dashboard", "data/dashboards/social_manager.yaml", 10),
    ]
    parent_menu = env.ref(
        "social_marketing.menu_social_marketing_global", raise_if_not_found=False
    )
    for module, path, sequence in dashboards:
        try:
            dashboard = env["dashboard.dashboard"].load_from_module_yaml(module, path)
            if parent_menu:
                dashboard.write({
                    "parent_menu_id": parent_menu.id,
                    "menu_sequence": sequence,
                })
                dashboard.create_update_menu()
            _logger.info("%s: loaded dashboard %s", module, dashboard.key)
        except Exception:
            _logger.exception("%s: failed to load %s", module, path)
