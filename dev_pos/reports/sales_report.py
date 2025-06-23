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
    
    # def action_generate_report_detail(self):
    #     raise ValidationError("Masuk action_generate_report_detail")
    
    @api.multi
    def action_generate_report_detail(self):
        orders = self.env['pos.order'].search([
            ('date_order', '>=', self.vit_date_from),
            ('date_order', '<=', self.vit_date_to),
        ])

        if not orders:
            raise UserError("Tidak ada data POS di periode tersebut.")

        # Buat file XLSX di memory
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()

        # Header
        worksheet.write(0, 0, 'Order Name')
        worksheet.write(0, 1, 'Date')
        worksheet.write(0, 2, 'Total Amount')

        # Isi data
        row = 1
        for order in orders:
            worksheet.write(row, 0, order.name)
            worksheet.write(row, 1, str(order.date_order))
            worksheet.write(row, 2, order.amount_total)
            row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        # Buat attachment
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