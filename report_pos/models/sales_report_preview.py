from odoo import models, fields, _, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
import uuid
from odoo.http import request

class SalesReportDetailPreview(models.TransientModel):
    _inherit = 'sales.report'
    
    def action_preview_report_detail(self):
        self.ensure_one()
        if not self.vit_date_from or not self.vit_date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")

        # base url
        url = f"/my/sales/report/detail?date_from={self.vit_date_from}&date_to={self.vit_date_to}"
        # jika ada invoice_no, tambahkan ke url
        if self.vit_invoice_no:
            url += f"&invoice_no={self.vit_invoice_no}"
        # jika ada pos_order_ref, tambahkan ke url
        if self.vit_pos_order_ref:
            url += f"&pos_order_ref={self.vit_pos_order_ref}"

        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': url,
        }


    def action_preview_report_recap(self):
        self.ensure_one()
        if not self.vit_date_from or not self.vit_date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")
        
        url = f"/sales/report/recap?date_from={self.vit_date_from}&date_to={self.vit_date_to}"
        if self.vit_invoice_no:
            url += f"&invoice_no={self.vit_invoice_no}"
        if self.vit_pos_order_ref:
            url += f"&pos_order_ref={self.vit_pos_order_ref}"

        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': url,
        }
    
    def action_preview_report_spending(self):
        self.ensure_one()
        if not self.vit_date_from or not self.vit_date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")
        
        url = f"/sales/report/spending?date_from={self.vit_date_from}&date_to={self.vit_date_to}"
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': url,
        }
    
    def action_preview_report_hourly(self):
        self.ensure_one()
        if not self.vit_date_from or not self.vit_date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")
        
        url = f"/sales/report/hourly?date_from={self.vit_date_from}&date_to={self.vit_date_to}"
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': url,
        }
    
    def action_preview_report_hourly_category(self):
        self.ensure_one()
        if not self.vit_date_from or not self.vit_date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")
        
        url = f"/sales/report/hourly_category?date_from={self.vit_date_from}&date_to={self.vit_date_to}"
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': url,
        }
    
    def action_preview_report_hourly_payment(self):
        self.ensure_one()
        if not self.vit_date_from or not self.vit_date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")
        
        url = f"/sales/report/hourly_payment?date_from={self.vit_date_from}&date_to={self.vit_date_to}"
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': url,
        }
    
    def action_preview_report_contribution_by_brand(self):
        self.ensure_one()
        if not self.vit_date_from or not self.vit_date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")
        
        url = f"/sales/report/contribution_by_brand?date_from={self.vit_date_from}&date_to={self.vit_date_to}"
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': url,
        }
    
    def action_preview_report_contribution_by_category(self):
        self.ensure_one()
        if not self.vit_date_from or not self.vit_date_to:
            raise UserError(_("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To"))

        url = f"/my/sales/report/contribution_by_category?date_from={self.vit_date_from}&date_to={self.vit_date_to}"
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': url,
        }