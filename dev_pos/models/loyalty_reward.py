from odoo import fields, models, api

class LoyaltyRewardInherit(models.Model):
    _inherit = 'loyalty.reward'

    vit_trxid = fields.Char(string="Transaction ID", default=False)

    def _get_discount_product_values(self):
        def generate_default_code(index):
            return f'Promo-{str(index).zfill(3)}'

        values = super()._get_discount_product_values()

        # Ambil produk terakhir untuk menghitung default_code
        last_product = self.env['product.product'].search([], order='id desc', limit=1)
        last_code = last_product.default_code if last_product and last_product.default_code else 'Promo-000'

        try:
            last_index = int(last_code.split('-')[1])
        except (IndexError, ValueError):
            last_index = 0

        # Tambahkan default_code + flag discount
        for i, val in enumerate(values):
            new_index = last_index + i + 1
            val.update({
                'default_code': generate_default_code(new_index),
                'vit_is_discount': True,  # ✅ tambahkan flag
            })

        return values

    def write(self, vals):
        """Saat update reward, generate default_code baru & tandai vit_is_discount"""
        res = super().write(vals)
        for reward in self:
            if reward.discount_line_product_id:
                values = reward._get_discount_product_values()
                if values:
                    reward.discount_line_product_id.write({
                        'default_code': values[0].get('default_code'),
                        'vit_is_discount': True,  # ✅ update flag juga
                    })
        return res
    
    # def write(self, vals):
    #     res = super().write(vals)

    #     if 'description' in vals:
    #         self._create_missing_discount_line_products()
    #         for reward in self:
    #             product = reward.discount_line_product_id
    #             if product:
    #                 # Update the name of the discount product
    #                 product.write({'name': reward.description})

    #                 # Update default_code for the discount product
    #                 last_code = product.default_code or ''
    #                 if last_code:
    #                     try:
    #                         last_index = int(last_code.split('-')[1])
    #                     except (IndexError, ValueError):
    #                         last_index = 0
    #                 else:
    #                     last_index = 0

    #                 new_code = f'Promo-{str(last_index + 1).zfill(3)}'
    #                 product.write({'default_code': new_code})

    #     if 'active' in vals:
    #         if vals['active']:
    #             if self.discount_line_product_id:
    #                 self.discount_line_product_id.action_unarchive()
    #         else:
    #             if self.discount_line_product_id:
    #                 self.discount_line_product_id.action_archive()

    #     return res
