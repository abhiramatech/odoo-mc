from odoo import models, fields, _, api
from odoo.exceptions import UserError, ValidationError

class SalesReportDetail(models.TransientModel):
    _name = 'sales.report'
    _description = 'Sales Report'

    vit_date_from = fields.Date(string='Date From')
    vit_date_to = fields.Date(string='Date To')
    vit_invoice_no = fields.Char(string='Invoice No')
    
    def action_generate_report_detail(self):
        raise ValidationError("Masuk action_generate_report_detail")

    def action_generate_report_hourly(self):
        raise ValidationError("Masuk action_generate_report_hourly")
    
    def action_generate_report_recap(self):
        raise ValidationError("Masuk action_generate_report_recap")
    
    def action_generate_report_spending(self):
        raise ValidationError("Masuk action_generate_report_spending")