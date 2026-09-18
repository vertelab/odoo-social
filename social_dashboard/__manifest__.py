# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Social: Dashboard",
    "version": "18.0.1.0.0",
    "category": "Marketing/Social Marketing",
    "summary": "BI dashboards for social_marketing powered by dashboard_vrtl",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "license": "AGPL-3",
    "depends": ["dashboard_vrtl", "social_marketing"],
    "data": [
        "security/ir.model.access.csv",
        "data/dashboard_source_data.xml",
    ],
    "post_init_hook": "_post_init_load_dashboards",
    "installable": True,
    "application": False,
    "auto_install": False,
}
