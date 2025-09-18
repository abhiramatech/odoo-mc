# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class LoyaltyHistory(models.Model):
    _name = 'loyalty.history'
    _description = "History for Loyalty cards and Ewallets"
    _order = 'id desc'

    card_id = fields.Many2one(comodel_name='loyalty.card', required=True, ondelete='cascade')
    points_before = fields.Float()
    points_after = fields.Float()
    pos_order_id = fields.Many2one(comodel_name='pos.order')
