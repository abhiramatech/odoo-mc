from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
    
class MasterCustomerGroup(models.Model):
    _name = 'customer.group'

    vit_group_name = fields.Char(string="Group", tracking=True)
    vit_pricelist_id = fields.Many2one('product.pricelist', string="Pricelist", tracking=True)