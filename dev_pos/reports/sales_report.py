from odoo import models, fields, _, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
import base64
import io
import xlsxwriter

class SalesReportDetail(models.TransientModel):
    _name = 'sales.report'
    _description = 'Sales Report'

    vit_date_from = fields.Date(string='Date From')
    vit_date_to = fields.Date(string='Date To')
    vit_invoice_no = fields.Char(string='Invoice No.')
    vit_pos_order_ref = fields.Char(string='POS Order No.')
  
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

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan Penjualan")
        worksheet.write(1, 0, "[ {} - {} ]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        header = [
            'User', 'Kasir', 'Customer Code', 'Customer Name', 'Kode Currency', 'Kode Store',
            'Invoice No.', 'Order No.', 'Session', 'No Retur', 'No HP', 'Tanggal',
            'Sub Divisi', 'Item Kelas', 'Item Tipe',
            'Item Code', 'Nama Item', 'POS Category', 'Satuan', 'Quantity',
            'Harga', 'Taxes', 'Sub Total', 'Sub Total Nett'
        ]

        for col, title in enumerate(header):
            worksheet.write(4, col, title)

        row = 5
        for order in orders:
            local_date_order = fields.Datetime.context_timestamp(self, order.date_order)
            for order_line in order.lines:
                worksheet.write(row, 0, order.user_id.name or '')
                worksheet.write(row, 1, order.employee_id.name or '')
                worksheet.write(row, 2, order.partner_id.customer_code or '')
                worksheet.write(row, 3, order.partner_id.name or '')
                worksheet.write(row, 4, order.currency_id.name or '')
                worksheet.write(row, 5, order.config_id.name or '')
                worksheet.write(row, 6, order.account_move.name or '')
                worksheet.write(row, 7, order.name or '')
                worksheet.write(row, 8, order.session_id.name or '')
                worksheet.write(row, 9, order.name if 'REFUND' in order.name.upper() else '')
                worksheet.write(row, 10, order.partner_id.mobile or '')
                worksheet.write(row, 11, local_date_order.strftime('%d/%m/%Y %H:%M:%S'))
                
                worksheet.write(row, 12, order_line.product_id.vit_sub_div or '')
                worksheet.write(row, 13, order_line.product_id.vit_item_kel or '')
                worksheet.write(row, 14, order_line.product_id.vit_item_type or '')

                worksheet.write(row, 15, order_line.product_id.default_code or '')
                worksheet.write(row, 16, order_line.product_id.name or '')
                worksheet.write(row, 17, order_line.product_id.product_tmpl_id.pos_categ_ids[0].name if order_line.product_id.product_tmpl_id.pos_categ_ids else '')
                worksheet.write(row, 18, order_line.product_uom_id.name or '')
                worksheet.write(row, 19, order_line.qty)
                worksheet.write(row, 20, order_line.price_unit)
                worksheet.write(row, 21, ", ".join(order_line.tax_ids_after_fiscal_position.mapped('name')) or '')
                worksheet.write(row, 22, order_line.price_subtotal)
                worksheet.write(row, 23, order_line.price_subtotal_incl)
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

    def action_generate_report_recap(self):
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

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan Penjualan")
        worksheet.write(1, 0, "[ {} - {} ]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        header = [
            'User', 'Kasir', 'Customer Code', 'Customer Name', 'Kode Currency', 'Kode Store',
            'Invoice No.', 'Order No.', 'Session', 'No Retur', 'No HP', 'Tanggal', 
            'Sub Divisi', 'Item Kelas', 'Item Tipe',
            'Total Quantity', 'Total Bersih'
        ]

        for col, title in enumerate(header):
            worksheet.write(4, col, title)

        row = 5
        for order in orders:
            total_qty = sum(order.lines.mapped('qty'))
            total_bersih = sum(order.lines.mapped('price_subtotal_incl'))
            local_date_order = fields.Datetime.context_timestamp(self, order.date_order)

            worksheet.write(row, 0, order.user_id.name or '')
            worksheet.write(row, 1, order.employee_id.name or '')
            worksheet.write(row, 2, order.partner_id.customer_code or '')
            worksheet.write(row, 3, order.partner_id.name or '')
            worksheet.write(row, 4, order.currency_id.name or '')
            worksheet.write(row, 5, order.config_id.name or '')
            worksheet.write(row, 6, order.account_move.name or '')
            worksheet.write(row, 7, order.name or '')
            worksheet.write(row, 8, order.session_id.name or '')
            worksheet.write(row, 9, order.name if 'REFUND' in order.name.upper() else '')
            worksheet.write(row, 10, order.partner_id.mobile or '')
            worksheet.write(row, 11, local_date_order.strftime('%d/%m/%Y %H:%M:%S'))
            worksheet.write(row, 12, order.product_id.vit_sub_div or '')
            worksheet.write(row, 13, order.product_id.vit_item_kel or '')
            worksheet.write(row, 14, order.product_id.vit_item_type or '')
            worksheet.write(row, 12, total_qty)
            worksheet.write(row, 13, total_bersih)
            row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Recap.xlsx',
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

    def action_generate_report_spending(self):
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

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan History Penjualan")
        worksheet.write(1, 0, "[ {} - {} ]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))
        
        range_spending = [
            (0, 50000, "0 - 50.000"),
            (50001, 100000, "50.001 - 100.000"),
            (100001, 250000, "100.001 - 250.000"),
            (250001, 500000, "250.001 - 500.000"),
            (500001, 1000000, "500.001 - 1.000.000"),
            (1000001, 3000000, "1.000.001 - 3.000.000"),
            (3000001, 5000000, "3.000.001 - 5.000.000"),
            (5000001, 20000000, "5.000.001 - 20.000.000"),
            (20000001, float('inf'), ">20.000.001"),
        ]
        
        tanggal_set = set(fields.Datetime.context_timestamp(self, order.date_order).date() for order in orders)
        tanggal_list = sorted(list(tanggal_set))
        
        header = ["Nomor", "Nama"]
        for tgl in tanggal_list:
            header += [f"Qty-{tgl.strftime('%d/%m/%Y')}", f"Trx-{tgl.strftime('%d/%m/%Y')}", f"Sales-{tgl.strftime('%d/%m/%Y')}"]

        for col, title in enumerate(header):
            worksheet.write(4, col, title)

        row = 5
        for idx, (min_spending, max_spending, label) in enumerate(range_spending, 1):
            worksheet.write(row, 0, idx)
            worksheet.write(row, 1, label)

            col = 2
            for tgl in tanggal_list:
                order_filtered = orders.filtered(lambda o: fields.Datetime.context_timestamp(self, o.date_order).date() == tgl and min_spending <= o.amount_total <= max_spending)

                total_qty = sum(order_filtered.mapped(lambda o: sum(o.lines.mapped('qty'))))
                total_trx = len(order_filtered)
                total_sales = sum(order_filtered.mapped('amount_total'))

                worksheet.write(row, col, total_qty)
                worksheet.write(row, col + 1, total_trx)
                worksheet.write(row, col + 2, total_sales)

                col += 3
            row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Spending.xlsx',
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

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan History Penjualan")
        worksheet.write(1, 0, "[{} - {}]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        # Ambil semua tanggal unik dalam order
        tanggal_set = set(fields.Datetime.context_timestamp(self, order.date_order).date() for order in orders)
        tanggal_list = sorted(list(tanggal_set))

        # Buat header kolom
        headers = ["Jam"]
        for tgl in tanggal_list:
            tgl_str = tgl.strftime('%d/%m/%Y')
            headers += [f"Qty-{tgl_str}", f"Trx-{tgl_str}", f"Sales-{tgl_str}"]

        for col, title in enumerate(headers):
            worksheet.write(4, col, title)

        row = 5
        for hour in range(24):
            worksheet.write(row, 0, f"{hour:02d}")

            col = 1
            for tgl in tanggal_list:
                order_filtered = orders.filtered(lambda o: fields.Datetime.context_timestamp(self, o.date_order).date() == tgl and fields.Datetime.context_timestamp(self, o.date_order).hour == hour)

                total_qty = sum(order_filtered.mapped(lambda o: sum(o.lines.mapped('qty'))))
                total_trx = len(order_filtered)
                total_sales = sum(order_filtered.mapped('amount_total'))

                worksheet.write(row, col, total_qty)
                worksheet.write(row, col + 1, total_trx)
                worksheet.write(row, col + 2, total_sales)

                col += 3
            row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Hourly.xlsx',
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
