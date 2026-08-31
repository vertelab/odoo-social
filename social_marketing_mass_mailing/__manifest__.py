# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Social: Mass Mailing Bridge",
    "version": "18.0.1.0.0",
    "category": "Marketing/Social Marketing",
    "summary": "Show social posts and mass mailings side by side on the shared UTM campaign",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "license": "AGPL-3",
    "depends": [
        "social_marketing",
        "mass_mailing",
    ],
    "data": [
        "views/utm_campaign_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
}
