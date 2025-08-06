from odoo import models, fields, _, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

class SalesReportDetailPreview(models.TransientModel):
    _inherit = 'sales.report'
 
    def action_preview_report_detail(self):
        # raise ValidationError(_(f"action_generate_report_detail_preview"))
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': self.get_portal_url(),
        }