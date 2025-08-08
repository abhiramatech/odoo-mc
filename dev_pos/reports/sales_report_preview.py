from odoo import models, fields, _, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
import uuid
from odoo.http import request

class SalesReportDetailPreview(models.TransientModel):
    _inherit = 'sales.report'

    access_url = fields.Char(
        'Portal Access URL', compute='_compute_access_url',
        help='Customer Portal URL')
    access_token = fields.Char('Security Token', copy=False)

    def _compute_access_url(self):
        for record in self:
            record.access_url = '#'
 
    def action_preview_report_detail_web(self):
        # raise ValidationError(_(f"action_generate_report_detail_preview"))
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': self.get_portal_url(),
        }
    
    def _portal_ensure_token(self):
        """ Get the current record access token """
        if not self.access_token:
            # we use a `write` to force the cache clearing otherwise `return self.access_token` will return False
            self.sudo().write({'access_token': str(uuid.uuid4())})
        return self.access_token
    
    def get_portal_url(self, suffix=None, report_type=None, download=None, query_string=None, anchor=None):
        """
            Get a portal url for this model, including access_token.
            The associated route must handle the flags for them to have any effect.
            - suffix: string to append to the url, before the query string
            - report_type: report_type query string, often one of: html, pdf, text
            - download: set the download query string to true
            - query_string: additional query string
            - anchor: string to append after the anchor #
        """
        self.ensure_one()
        url = self.access_url + '%s?access_token=%s%s%s%s%s' % (
            suffix if suffix else '',
            self._portal_ensure_token(),
            '&report_type=%s' % report_type if report_type else '',
            '&download=true' if download else '',
            query_string if query_string else '',
            '#%s' % anchor if anchor else ''
        )
        return url
    
    def action_preview_report_detail(self):
        self.ensure_one()

        date_from = self.vit_date_from
        date_to = self.vit_date_to
        invoice_no = self.vit_invoice_no
        pos_order_ref = self.vit_pos_order_ref

        if not date_from or not date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")

        account_move = self.env['account.move'].search([('name', '=', invoice_no)], limit=1)

        domain = []
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if account_move:
            domain.append(('account_move', '=', account_move.id))
        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = self.env['pos.order'].search(domain)

        if not orders:
            raise UserError("Tidak ada data POS di periode tersebut.")

        values = {
            'orders': orders,
            'date_from': date_from.strftime('%d/%m/%Y'),
            'date_to': date_to.strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
        }

        return request.render('dev_pos.template_preview_report_detail', values)