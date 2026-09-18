# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Social: Planner Dashboard",
    "version": "18.0.1.0.0",
    "category": "Marketing/Social Marketing",
    "summary": "Planning, compliance and community dashboards for social_planner",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "license": "AGPL-3",
    "depends": ["social_planner", "dashboard_vrtl"],
    "data": [
        "security/ir.model.access.csv",
        "data/dashboard_source_data.xml",
        "views/res_config_settings_views.xml",
    ],
    "post_init_hook": "_post_init_load_dashboards",
    "installable": True,
    "application": False,
    "auto_install": True,
}
