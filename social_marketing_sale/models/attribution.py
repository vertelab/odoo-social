# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3
""" Shared aggregation used by both ends of the sales attribution chain.

The campaign end groups sale.order by `campaign_id`, the post end groups it by
`source_id`. Only the grouping field differs.

Currency. sale.order.amount_total is expressed in the order currency, so
summing it raw across orders produces a number that looks like money and is
not. Every order carries `currency_rate`, the stored company-to-order rate at
the order date, which is exactly what Odoo's own sale.report divides by to
report in company currency. The same division is used here, so this bridge and
the Sales analysis report can never disagree.

No sudo(). The search runs as the calling user, so sale.order record rules
apply. Read access is gated by the `groups=` on every exposed field.
"""

CONFIRMED_STATES = ('sale',)


def aggregate_orders(env, groupby_field, record_ids):
    """ Return {record_id: (quotation_count, order_count, revenue)}.

    `quotation_count` is every sale.order attributed, cancelled ones excluded.
    `order_count` and `revenue` cover confirmed orders only. Revenue is in the
    company currency.
    """
    result = {record_id: [0, 0, 0.0] for record_id in record_ids}
    if not record_ids:
        return {record_id: tuple(values) for record_id, values in result.items()}

    company_currency = env.company.currency_id
    orders = env['sale.order'].search([
        (groupby_field, 'in', list(record_ids)),
        ('state', '!=', 'cancel'),
    ])
    for order in orders:
        key = order[groupby_field].id
        if key not in result:
            continue
        result[key][0] += 1
        if order.state in CONFIRMED_STATES:
            result[key][1] += 1
            rate = order.currency_rate or 1.0
            result[key][2] += order.amount_total / rate

    for values in result.values():
        values[2] = company_currency.round(values[2])

    return {record_id: tuple(values) for record_id, values in result.items()}
