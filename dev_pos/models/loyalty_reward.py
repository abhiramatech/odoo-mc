from odoo import fields, models, api
from odoo.exceptions import ValidationError

class LoyaltyRewardInherit(models.Model):
    _inherit = 'loyalty.reward'

    vit_trxid = fields.Char(string="Transaction ID", default=False)
    vit_item_code_sap = fields.Char(string="Item Code SAP", required=True) 
    vit_reward_trxid = fields.Char(string="Reward Item", index=True)


    def _get_discount_product_values(self):
        values = super()._get_discount_product_values()

        # Gunakan vit_item_code_sap sebagai default_code
        for val in values:
            val.update({
                'default_code': self.vit_item_code_sap,
                'vit_is_discount': True,
            })

        return values

    def write(self, vals):
        """Saat update reward, salin vit_item_code_sap ke default_code"""
        res = super().write(vals)
        for reward in self:
            if reward.discount_line_product_id:
                reward.discount_line_product_id.write({
                    'default_code': reward.vit_item_code_sap,
                    'vit_is_discount': True,
                })
        return res

    @api.constrains('vit_item_code_sap')
    def _check_item_code_sap(self):
        """Pastikan field Item Code SAP tidak kosong"""
        for record in self:
            if not record.vit_item_code_sap:
                raise ValidationError("Field 'Item Code SAP' tidak boleh kosong.")

    @api.constrains('description')
    def _check_unique_description(self):
        """Pastikan description tidak duplicate"""
        for record in self:
            duplicate = self.search([
                ('description', '=', record.description),
                ('id', '!=', record.id)
            ], limit=1)
            if duplicate:
                raise ValidationError("Description sudah digunakan oleh reward lain. Harap gunakan description yang berbeda.")
