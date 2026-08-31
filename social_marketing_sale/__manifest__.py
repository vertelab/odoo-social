# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Social: Sales Bridge",
    "version": "18.0.1.0.0",
    "category": "Marketing/Social Marketing",
    "summary": "Attribute confirmed sales orders and revenue to social campaigns and to individual posts",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "license": "AGPL-3",
    "depends": [
        "social_marketing",
        "sale",
    ],
    "data": [
        "views/utm_campaign_views.xml",
        "views/social_marketing_post_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
}
