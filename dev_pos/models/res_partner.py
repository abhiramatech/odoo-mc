import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    customer_code = fields.Char(string='Customer Code', tracking=True)
    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    index_store = fields.Many2many('setting.config', string="Index Store", readonly=True)
    vit_customer_group = fields.Many2one('customer.group', string="Customer Group", tracking=True)

    def write(self, vals):
        # Log perubahan untuk field tertentu ke chatter
        for partner in self:
            changes = []
            
            # Track phone changes
            if 'phone' in vals:
                old_phone = partner.phone or 'Not Set'
                new_phone = vals['phone'] or 'Not Set'
                if old_phone != new_phone:
                    changes.append(f"Phone: {old_phone} → {new_phone}")
            
            # Track category_id changes
            if 'category_id' in vals:
                old_categories = ', '.join(partner.category_id.mapped('name')) if partner.category_id else 'Not Set'
                
                # Process new categories
                new_category_ids = vals['category_id']
                if new_category_ids:
                    # Handle different formats of many2many write
                    category_records = self.env['res.partner.category']
                    for command in new_category_ids:
                        if command[0] == 6:  # (6, 0, [ids])
                            category_records = self.env['res.partner.category'].browse(command[2])
                        elif command[0] == 4:  # (4, id)
                            category_records |= self.env['res.partner.category'].browse(command[1])
                        elif command[0] == 3:  # (3, id) - unlink
                            continue
                        elif command[0] == 5:  # (5,) - clear all
                            category_records = self.env['res.partner.category']
                            break
                    new_categories = ', '.join(category_records.mapped('name')) if category_records else 'Not Set'
                else:
                    new_categories = 'Not Set'
                
                if old_categories != new_categories:
                    changes.append(f"Tags: {old_categories} → {new_categories}")
            
            # Track customer_code changes
            if 'customer_code' in vals:
                old_code = partner.customer_code or 'Not Set'
                new_code = vals['customer_code'] or 'Not Set'
                if old_code != new_code:
                    changes.append(f"Customer Code: {old_code} → {new_code}")
            
            # Track index_store changes
            if 'index_store' in vals:
                old_stores = ', '.join(partner.index_store.mapped('name')) if partner.index_store else 'Not Set'
                
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
            
            # Post message to chatter if there are changes
            if changes:
                message = '\n'.join(changes)
                partner.message_post(body=message, subject="Partner Information Updated")
        
        return super(ResPartner, self).write(vals)