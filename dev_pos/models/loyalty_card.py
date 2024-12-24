# -*- coding: utf-8 -*-
from odoo import fields, models


class LoyaltyCardInherit(models.Model):
    _inherit = 'loyalty.card'

    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    is_updated = fields.Boolean(string="Updated", default=False, readonly=True, tracking=True)  
    index_store = fields.Many2many('setting.config', string="Index Store", readonly=True)
    vit_trxid = fields.Char(string="Transaction ID", default=False)


    def delete_card(self):
        a = self.env['loyalty.card'].search([('code', '=', "0443-3174-4ce2Store")])
        a.unlink()

    def write(self, vals):
        # Only set is_updated to True if it hasn't been explicitly set to False in vals
        if 'is_updated' not in vals:
            vals['is_updated'] = True

        return super(LoyaltyCardInherit, self).write(vals)
