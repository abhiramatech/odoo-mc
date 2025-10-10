# -*- coding: utf-8 -*-
from odoo import fields, models


class LoyaltyRuleInherit(models.Model):
    _inherit = 'loyalty.rule'

    vit_trxid = fields.Char(string="Transaction ID", default=False)
    reward_point_amount = fields.Float(
        digits=(16, 5),  # Total 16 digit, 5 angka di belakang koma
        default=1, 
        string="Reward"
    )
