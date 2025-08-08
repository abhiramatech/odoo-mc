from odoo import http
from odoo.http import request
from odoo import models, fields, _, api


class SalesReportDetailController(http.Controller):
    @http.route('/sales/report/detail/<int:wizard_id>', type='http', auth='user', website=True)
    def portal_sales_report_detail(self, wizard_id, **kw):
        wizard = request.env['sales.report'].sudo().browse(wizard_id)
        if not wizard.exists():
            return request.not_found()

        # Ambil ulang data seperti sebelumnya
        date_from = wizard.vit_date_from
        date_to = wizard.vit_date_to
        invoice_no = wizard.vit_invoice_no
        pos_order_ref = wizard.vit_pos_order_ref

        domain = []
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if invoice_no:
            move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)
            if move:
                domain.append(('account_move', '=', move.id))
        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)

        values = {
            'orders': orders,
            'date_from': date_from.strftime('%d/%m/%Y') if date_from else '',
            'date_to': date_to.strftime('%d/%m/%Y') if date_to else '',
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
        }

        return request.render('nama_modul.template_preview_report_detail', values)
