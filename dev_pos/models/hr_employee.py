# -*- coding: utf-8 -*-
from odoo import fields, models


class HREmployeeInherit(models.Model):
    _inherit = 'hr.employee'
    
    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    index_store = fields.Many2many('setting.config', string="Index Store", readonly=True)
    is_sales = fields.Boolean(string="Sales", default=False)
    is_cashier = fields.Boolean(string="Cashier", default=False)
    is_pic = fields.Boolean(string="PIC", default=False)
    vit_employee_code = fields.Char(string="Employee Code", default=False, tracking=True)