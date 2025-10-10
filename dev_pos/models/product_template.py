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
    brand = fields.Char(string="Brand", tracking=True)

    def _check_barcode_uniqueness(self):
        # Override untuk mematikan validasi barcode unik
        # Tidak akan pernah raise ValidationError lagi walaupun ada duplikat
        return True

    def write(self, vals):
        # Log perubahan untuk field tertentu ke chatter
        for product in self:
            changes = []
            
            # Track list_price changes
            if 'list_price' in vals:
                old_price = product.list_price
                new_price = vals['list_price']
                if old_price != new_price:
                    changes.append(f"Sales Price: {old_price:,.2f} → {new_price:,.2f}")
            
            # Track product_tag_ids changes
            if 'product_tag_ids' in vals:
                old_tags = ', '.join(product.product_tag_ids.mapped('name')) if product.product_tag_ids else 'Not Set'
                
                # Process new tags
                new_tag_ids = vals['product_tag_ids']
                if new_tag_ids:
                    # Handle different formats of many2many write
                    tag_records = self.env['product.tag']
                    for command in new_tag_ids:
                        if command[0] == 6:  # (6, 0, [ids])
                            tag_records = self.env['product.tag'].browse(command[2])
                        elif command[0] == 4:  # (4, id)
                            tag_records |= self.env['product.tag'].browse(command[1])
                        elif command[0] == 3:  # (3, id) - unlink
                            continue
                        elif command[0] == 5:  # (5,) - clear all
                            tag_records = self.env['product.tag']
                            break
                    new_tags = ', '.join(tag_records.mapped('name')) if tag_records else 'Not Set'
                else:
                    new_tags = 'Not Set'
                
                if old_tags != new_tags:
                    changes.append(f"Product Tags: {old_tags} → {new_tags}")
            
            # Track brand changes
            if 'brand' in vals:
                old_brand = product.brand or 'Not Set'
                new_brand = vals['brand'] or 'Not Set'
                if old_brand != new_brand:
                    changes.append(f"Brand: {old_brand} → {new_brand}")
            
            # Track index_store changes
            if 'index_store' in vals:
                old_stores = ', '.join(product.index_store.mapped('name')) if product.index_store else 'Not Set'
                
                # Process new stores
                new_store_ids = vals['index_store']
                if new_store_ids:
                    # Handle different formats of many2many write
                    store_records = self.env['setting.config']
                    for command in new_store_ids:
                        if command[0] == 6:  # (6, 0, [ids])
                            store_records = self.env['setting.config'].browse(command[2])
                        elif command[0] == 4:  # (4, id)
                            store_records |= self.env['setting.config'].browse(command[1])
                        elif command[0] == 3:  # (3, id) - unlink
                            continue
                        elif command[0] == 5:  # (5,) - clear all
                            store_records = self.env['setting.config']
                            break
                    new_stores = ', '.join(store_records.mapped('name')) if store_records else 'Not Set'
                else:
                    new_stores = 'Not Set'
                
                if old_stores != new_stores:
                    changes.append(f"Index Store: {old_stores} → {new_stores}")
            
            # Track vit_is_discount changes
            if 'vit_is_discount' in vals:
                old_discount = 'Yes' if product.vit_is_discount else 'No'
                new_discount = 'Yes' if vals['vit_is_discount'] else 'No'
                if old_discount != new_discount:
                    changes.append(f"Discount: {old_discount} → {new_discount}")
            
            # Post message to chatter if there are changes
            if changes:
                message = '\n'.join(changes)
                product.message_post(body=message, subject="Product Information Updated")
        
        return super(ProductTemplate, self).write(vals)


class ProductProductInherit(models.Model):
    _inherit = 'product.product'

    vit_is_discount = fields.Boolean(string="Is Discount", default=False)

    def _check_barcode_uniqueness(self):
        # Override untuk mematikan validasi barcode unik
        # Tidak akan pernah raise ValidationError lagi walaupun ada duplikat
        return True