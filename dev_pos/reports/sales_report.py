from odoo import models, fields, _, api
from odoo.exceptions import UserError, ValidationError
import base64
import io
import xlsxwriter

class SalesReportDetail(models.TransientModel):
    _name = 'sales.report'
    _description = 'Sales Report'

    vit_date_from = fields.Date(string='Date From')
    vit_date_to = fields.Date(string='Date To')
    vit_invoice_no = fields.Char(string='Invoice No')
    vit_pos_order_ref = fields.Char(string='POS Order Ref')
    
    # def action_generate_report_detail(self):
    #     raise ValidationError("Masuk action_generate_report_detail")
    
    
# [{'id': 17, 'name': 'S01/0016', 'date_order': datetime.datetime(2025, 6, 17, 7, 45, 20), 'user_id': (2, 'Administrator'), 'amount_difference': 0.0, 'amount_tax': 0.0, 'amount_total': 0.0, 'amount_paid': 0.0, 'amount_return': 0.0, 'margin': 0.0, 'margin_percent': 0.0, 'is_total_cost_computed': True, 'lines': [31, 32], 'company_id': (1, 'Visi-Intech'), 'country_code': 'ID', 'pricelist_id': False, 'partner_id': (10, 'Astri Ririn'), 'sequence_number': 14, 'session_id': (5, 'POS/00003'), 'config_id': (1, 'S01'), 'currency_id': (12, 'IDR'), 'currency_rate': 1.0, 'state': 'paid', 'account_move': False, 'picking_ids': [79], 'picking_count': 1, 'failed_pickings': False, 'picking_type_id': (9, 'Store 01: PoS Orders'), 'procurement_group_id': False, 'floating_order_name': False, 'general_note': '', 'nb_print': 0, 'pos_reference': 'Order 00005-008-0014', 'sale_journal': (12, 'Point of Sale'), 'fiscal_position_id': False, 'payment_ids': [], 'session_move_id': False, 'to_invoice': False, 'shipping_date': False, 'is_invoiced': False, 'is_tipped': False, 'tip_amount': 0.0, 'refund_orders_count': 0, 'refunded_order_id': False, 'has_refundable_lines': True, 'ticket_code': 'k7my0', 'tracking_number': '514', 'uuid': 'f123d9f8-3721-40f3-9d18-dd3132506887', 'email': 'ririn.e@visi-intech.com', 'mobile': False, 'is_edited': False, 'has_deleted_line': False, 'order_edit_tracking': False, 'available_payment_method_ids': [2, 3, 1], 'display_name': 'S01/0016', 'create_uid': (2, 'Administrator'), 'create_date': datetime.datetime(2025, 6, 17, 7, 45, 22, 29417), 'write_uid': (2, 'Administrator'), 'write_date': datetime.datetime(2025, 6, 17, 7, 45, 22, 29417), 'l10n_id_qris_transaction_ids': [], 'employee_id': False, 'cashier': 'Administrator', 'online_payment_method_id': False, 'next_online_payment_amount': 0.0, 'table_id': False, 'customer_count': 0, 'takeaway': False, 'crm_team_id': False, 'sale_order_count': 0, 'table_stand_number': False, 'use_self_order_online_payment': False}]
    
    def action_generate_report_detail(self):
        date_from = self.vit_date_from or False
        date_to = self.vit_date_to or False
        invoice_no = self.vit_invoice_no or False
        pos_order_ref = self.vit_pos_order_ref or False

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

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()

        header = [
            'User', 'Customer Code', 'Customer Name', 'Kode Currency', 'Kode Store',
            'No Faktur', 'Order Ref', 'No Retur', 'No HP', 'Tanggal', 
            'Item Code', 'Nama Item', 'POS Category', 'Satuan', 'Quantity',
            'Harga', 'Taxes', 'Sub Total', 'Sub Total Nett'
        ]

        for col, title in enumerate(header):
            worksheet.write(0, col, title)

        row = 1
        for order in orders:
            for order_line in order.lines:
                worksheet.write(row, 0, order.user_id.name or '')
                worksheet.write(row, 1, order.partner_id.customer_code or '')
                worksheet.write(row, 2, order.partner_id.name or '')
                worksheet.write(row, 3, order.currency_id.name or '')
                worksheet.write(row, 4, order.config_id.name or '')
                worksheet.write(row, 5, order.account_move.name or '')
                worksheet.write(row, 6, order.name or '')
                worksheet.write(row, 7, order.name if 'REFUND' in order.name.upper() else '')
                worksheet.write(row, 8, order.partner_id.mobile or '')
                worksheet.write(row, 9, str(order.date_order))

                worksheet.write(row, 10, order_line.product_id.default_code or '')
                worksheet.write(row, 11, order_line.product_id.name or '')
                worksheet.write(row, 12, order_line.product_id.product_tmpl_id.pos_categ_ids[0].name if order_line.product_id.product_tmpl_id.pos_categ_ids else '')
                worksheet.write(row, 13, order_line.product_uom_id.name or '')
                worksheet.write(row, 14, order_line.qty)
                worksheet.write(row, 15, order_line.price_unit)
                worksheet.write(row, 16, ", ".join(order_line.tax_ids_after_fiscal_position.mapped('name')) or '')
                worksheet.write(row, 17, order_line.price_subtotal)
                worksheet.write(row, 18, order_line.price_subtotal_incl)
                row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Detail.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }


    def action_generate_report_hourly(self):
        raise ValidationError("Masuk action_generate_report_hourly")
    
    def action_generate_report_recap(self):
        raise ValidationError("Masuk action_generate_report_recap")
    
    def action_generate_report_spending(self):
        raise ValidationError("Masuk action_generate_report_spending")