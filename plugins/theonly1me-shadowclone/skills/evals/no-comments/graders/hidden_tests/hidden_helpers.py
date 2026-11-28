def kinds(invoice):
    return [item.kind for item in invoice.line_items]


def amounts(invoice, kind):
    return [item.amount_cents for item in invoice.line_items if item.kind == kind]
