import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class ReportSaleDetailsInherit(models.AbstractModel):
    _inherit = "report.point_of_sale.report_saledetails"

    def get_sale_details(self, date_start=False, date_stop=False, config_ids=False, session_ids=False):
        # 🔹 Panggil bawaan dulu
        res = super().get_sale_details(date_start, date_stop, config_ids, session_ids)

        sessions = self.env["pos.session"].browse(session_ids) if session_ids else []
        for session in sessions:
            # 🔹 Ambil total modal semua shift dalam session
            modal_total = sum(self.env["end.shift"].search([("session_id", "=", session.id)]).mapped("modal"))

            for payment in res.get("payments", []):
                if payment.get("session") == session.id and payment.get("cash"):
                    # final_count asli + modal_total
                    payment["final_count"] = (payment.get("final_count") or 0.0) + modal_total
                    # difference harus ikut update
                    payment["money_difference"] = (payment.get("money_counted") or 0.0) - payment["final_count"]

        return res

class PosSession(models.Model):
    _inherit = 'pos.session'

    is_updated = fields.Boolean(string="Updated", default=False, readonly=True, tracking=True)
    name_session_pos = fields.Char(string="Name Session POS (Odoo Store)", tracking=True)

    def write_sessions(self):
        update_session = self.env['pos.session'].search([])
        for rec in update_session:
            rec.write({
                'state': 'opened'
            })