# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Social: Marketing Agency",
    "version": "18.0.1.6.1",
    "category": "Marketing/Social Marketing",
    "summary": "Agency layer: brands, customer underlag, portal accounts and per-brand dashboards",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "license": "AGPL-3",
    "depends": [
        "social_marketing",
        "social_planner",
        "dashboard_vrtl",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/dashboard_metric_data.xml",
        "data/agency_document_type_data.xml",
        "views/social_brand_views.xml",
        "views/social_brand_credential_views.xml",
        "views/res_partner_views.xml",
        "views/res_users_views.xml",
        "views/social_agency_document_views.xml",
        "views/communication_policy_views.xml",
        "views/social_marketing_post_template_views.xml",
        "views/social_marketing_post_views.xml",
        "views/social_marketing_listening_views.xml",
        "views/social_marketing_competitor_views.xml",
        "views/social_agency_invite_views.xml",
        "views/dashboard_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
