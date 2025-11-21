from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
    
class MasterCustomerGroup(models.Model):
    _name = 'customer.group'
    _rec_name = 'vit_group_name'

    vit_group_name = fields.Char(string="Group", tracking=True)
    vit_pricelist_id = fields.Many2one('product.pricelist', string="Pricelist", tracking=True)
    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    is_updated = fields.Boolean(string="Updated", default=False, readonly=True, tracking=True)
    index_store = fields.Many2many('setting.config', string="Index Store", readonly=True)