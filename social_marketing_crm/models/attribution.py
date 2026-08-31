# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3
""" Shared aggregation used by both ends of the CRM attribution chain.

The campaign end groups crm.lead by `campaign_id`, the post end groups it by
`source_id`. Nothing else differs, so the grouping field is the only argument.

No sudo() anywhere. The aggregation runs as the calling user, so record rules
on crm.lead apply and a salesman only ever sees the leads of their own team
reflected in the figures. Read access is gated one level higher, by the
`groups=` on every field that exposes these numbers.
"""


def aggregate_leads(env, groupby_field, record_ids):
    """ Return {record_id: (lead_count, won_count, expected_revenue)}.

    :param groupby_field: 'campaign_id' or 'source_id' on crm.lead
    :param record_ids: ids of the utm.campaign or social_marketing.post records

    Counting follows Odoo's own `utm.campaign.crm_lead_count`, which uses
    active_test=False so a lost (archived) lead still counts as a lead the
    post produced. Expected revenue deliberately does NOT: a lost lead has no
    expected revenue left, so summing it would inflate the pipeline figure.
    """
    result = {record_id: [0, 0, 0.0] for record_id in record_ids}
    if not record_ids:
        return {record_id: tuple(values) for record_id, values in result.items()}

    Lead = env['crm.lead']
    domain = [(groupby_field, 'in', list(record_ids))]

    all_leads = Lead.with_context(active_test=False)
    for group, count in all_leads._read_group(domain, [groupby_field], ['__count']):
        if group.id in result:
            result[group.id][0] = count

    won_domain = domain + [('stage_id.is_won', '=', True)]
    for group, count in all_leads._read_group(won_domain, [groupby_field], ['__count']):
        if group.id in result:
            result[group.id][1] = count

    # Active leads only, and expected_revenue is already a Monetary in the
    # company currency (crm.lead uses currency_field='company_currency'), so
    # this sum never mixes currencies.
    for group, revenue in Lead._read_group(domain, [groupby_field], ['expected_revenue:sum']):
        if group.id in result:
            result[group.id][2] = revenue or 0.0

    return {record_id: tuple(values) for record_id, values in result.items()}
