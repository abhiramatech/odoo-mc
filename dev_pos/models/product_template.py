from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
  

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_integrated = fields.Boolean(string="Integrated", default=False)
    index_store = fields.Many2many('setting.config', string="Index Store")
    vit_sub_div = fields.Char(string="Sub Category")
    vit_item_kel = fields.Char(string="Kelompok")
    vit_item_type = fields.Char(string="Type")
    vit_is_discount = fields.Boolean(string="Discount")

    def _check_barcode_uniqueness(self):
        # Override untuk mematikan validasi barcode unik
        # Tidak akan pernah raise ValidationError lagi walaupun ada duplikat
        return True

class ProductProductInherit(models.Model):
    _inherit = 'product.product'

    vit_is_discount = fields.Boolean(string="Is Discount", default=False)

    def _check_barcode_uniqueness(self):
        # Override untuk mematikan validasi barcode unik
        # Tidak akan pernah raise ValidationError lagi walaupun ada duplikat
        return True