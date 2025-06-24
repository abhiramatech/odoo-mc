from odoo import models, fields, api
from odoo.exceptions import ValidationError

class MultipleBarcode(models.Model):
    _name = "multiple.barcode"
    _description = "Multiple Barcode"

    barcode = fields.Char(string="Barcode", required=True)
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product Variant', ondelete='cascade')
    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    index_store = fields.Many2many('setting.config', string="Index Store", readonly=True)

    @api.model
    def create(self, vals):
        # Auto-fill product_id if product_tmpl_id has one variant
        if not vals.get('product_id') and vals.get('product_tmpl_id'):
            tmpl = self.env['product.template'].browse(vals['product_tmpl_id'])
            if tmpl.product_variant_ids and len(tmpl.product_variant_ids) == 1:
                vals['product_id'] = tmpl.product_variant_ids.id
        return super(MultipleBarcode, self).create(vals)

    def write(self, vals):
        for record in self:
            if not record.product_id and (vals.get('product_tmpl_id') or record.product_tmpl_id):
                tmpl = self.env['product.template'].browse(vals.get('product_tmpl_id', record.product_tmpl_id.id))
                if tmpl.product_variant_ids and len(tmpl.product_variant_ids) == 1:
                    vals['product_id'] = tmpl.product_variant_ids.id
        return super(MultipleBarcode, self).write(vals)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    multi_barcode_ids = fields.One2many('multiple.barcode', 'product_tmpl_id', string='Multiple Barcodes')


class ProductProduct(models.Model):
    _inherit = 'product.product'

    multi_barcode_ids = fields.One2many('multiple.barcode', 'product_id', string='Multiple Barcodes')
