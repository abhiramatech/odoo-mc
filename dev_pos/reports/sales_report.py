from odoo import models, fields, _, api
from odoo.exceptions import UserError, ValidationError

class SalesReport(models.TransientModel):
    _name = 'sales.report'
    _description = 'Sales Report'

    vit_date_from = fields.Date(string='Date From')
    vit_date_to = fields.Date(string='Date To')
    vit_invoice_no = fields.Char(string='Invoice No', required=True)
    vit_sales_detail = fields.Boolean(string="Sales Report Detail", default=False)
    vit_sales_recap = fields.Boolean(string="Sales Report Recap ", default=False)
    vit_sales_spending = fields.Boolean(string="Sales Report Spending", default=False)
    vit_sales_hourly = fields.Boolean(string="Sales Report Hourly", default=False)
    
    def action_generate_report(self):
        return
