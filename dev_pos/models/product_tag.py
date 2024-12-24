from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
  

class ProductTagsInherit(models.Model):
    _inherit = 'product.tag'

    is_integrated = fields.Boolean(string="Integrated", default=False)
    vit_trxid = fields.Char(string="Transaction ID", default=False)