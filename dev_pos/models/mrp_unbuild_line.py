from odoo import fields, models, api, _
from odoo.exceptions import UserError

class MrpProductInherit(models.Model):
    _inherit = 'mrp.production'

    vit_trxid = fields.Char(string="Transaction ID", default=False)
    is_integrated = fields.Boolean(string="Integrated", default=False)
    index_store = fields.Many2many('setting.config', string="Index Store", readonly=True)

    def write(self, vals):
        # Cek jika ada perubahan pada move_raw_ids dan status sudah done
        if 'move_raw_ids' in vals and any(record.state == 'done' for record in self):
            # Analisis operasi yang dilakukan pada move_raw_ids
            move_operations = vals.get('move_raw_ids', [])
            
            for operation in move_operations:
                # (0, 0, values) - CREATE new line
                # (2, id, 0) - DELETE existing line
                if operation[0] in (0, 2):
                    raise UserError(_("Cannot add or delete raw material lines when manufacturing order is in Done state."))
        
        # Cek juga untuk move_finished_ids
        if 'move_finished_ids' in vals and any(record.state == 'done' for record in self):
            move_operations = vals.get('move_finished_ids', [])
            
            for operation in move_operations:
                if operation[0] in (0, 2):
                    raise UserError(_("Cannot add or delete finished product lines when manufacturing order is in Done state."))
        
        return super(MrpProductInherit, self).write(vals)

class MrpBoMInherit(models.Model):
    _inherit = 'mrp.bom'

    id_mc = fields.Char(string="ID MC", default=False)
    is_integrated = fields.Boolean(string="Integrated", default=False)
    index_store = fields.Many2many('setting.config', string="Index Store", readonly=True)

    @api.model
    def create(self, vals):
        # Jika field 'code' belum diisi manual
        if not vals.get('code'):
            # Buat sequence otomatis, contoh format: BOM/2025/00001
            sequence = self.env['ir.sequence'].next_by_code('mrp.bom.code') or '/'
            vals['code'] = sequence

        return super(MrpBoMInherit, self).create(vals)

    def write(self, vals):
        # Cek jika ada perubahan pada bom_line_ids dan BoM aktif
        if 'bom_line_ids' in vals and any(record.active for record in self):
            # Analisis operasi yang dilakukan pada bom_line_ids
            line_operations = vals.get('bom_line_ids', [])
            
            for operation in line_operations:
                # (0, 0, values) - CREATE new line
                # (2, id, 0) - DELETE existing line
                if operation[0] in (0, 2):
                    raise UserError(_("Cannot add or delete BOM lines when Bill of Materials is active."))
        
        return super(MrpBoMInherit, self).write(vals)

class MrpUnbuild(models.Model):
    _inherit = 'mrp.unbuild'

    unbuild_line_ids = fields.One2many('mrp.unbuild.line', 'unbuild_id', string='Unbuild Lines')
    vit_trxid = fields.Char(string="Transaction ID", default=False)
    is_integrated = fields.Boolean(string="Integrated", default=False)
    index_store = fields.Many2many('setting.config', string="Index Store", readonly=True)

    def write(self, vals):
        # Cek jika ada perubahan pada unbuild_line_ids dan status sudah done
        if 'unbuild_line_ids' in vals and any(record.state == 'done' for record in self):
            line_operations = vals.get('unbuild_line_ids', [])
            
            for operation in line_operations:
                # (0, 0, values) - CREATE new line
                # (2, id, 0) - DELETE existing line
                if operation[0] in (0, 2):
                    raise UserError(_("Cannot add or delete unbuild lines when unbuild order is in Done state."))
        
        return super(MrpUnbuild, self).write(vals)

    def _generate_produce_moves(self):
        StockLocation = self.env['stock.location']
        virtual_production_location = StockLocation.search([('usage', '=', 'production')], limit=1)
        moves = self.env['stock.move']

        for unbuild in self:
            if not unbuild.unbuild_line_ids:
                raise UserError(_("You must provide unbuild line components before proceeding."))

            for line in unbuild.unbuild_line_ids:
                final_qty = line.product_uom_qty * unbuild.product_qty
                product = line.product_id
                product_uom = line.product_uom

                move = self.env['stock.move'].create({
                    'name': unbuild.name,
                    'date': unbuild.create_date,
                    'product_id': product.id,
                    'product_uom_qty': final_qty,
                    'product_uom': product_uom.id,
                    'procure_method': 'make_to_stock',
                    'location_id': virtual_production_location.id,        # 🔁 VIRTUAL PRODUCTION
                    'location_dest_id': unbuild.location_dest_id.id,      # 🔁 REAL STOCK
                    'warehouse_id': unbuild.location_dest_id.warehouse_id.id,
                    'unbuild_id': unbuild.id,
                    'company_id': unbuild.company_id.id,
                })
                moves |= move

        return moves

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if not self.product_id:
            return

        # Cari BOM berdasarkan produk
        bom = self.env['mrp.bom'].search([('product_tmpl_id', '=', self.product_id.product_tmpl_id.id)], limit=1)
        if not bom:
            return

        lines = []
        for bom_line in bom.bom_line_ids:
            lines.append((0, 0, {
                'product_id': bom_line.product_id.id,
                'location_id': self.location_id.id if self.location_id else False,
                'product_uom_qty': bom_line.product_qty,
                'product_uom': bom_line.product_uom_id.id,
            }))

        self.unbuild_line_ids = lines


class MrpUnbuildLine(models.Model):
    _name = 'mrp.unbuild.line'

    unbuild_id = fields.Many2one('mrp.unbuild', string='Unbuild')
    product_id = fields.Many2one('product.product', string='Product')
    location_id = fields.Many2one('stock.location', string='Location')
    product_uom_qty = fields.Float(string='To Consume')
    product_uom = fields.Many2one('uom.uom', string='Unit of Measure')

    def write(self, vals):
        # Cek jika unbuild order terkait sudah done
        for record in self:
            if record.unbuild_id and record.unbuild_id.state == 'done':
                raise UserError(_("Cannot modify unbuild lines when unbuild order is in Done state."))
        
        return super(MrpUnbuildLine, self).write(vals)
    
    def unlink(self):
        # Cek jika unbuild order terkait sudah done
        for record in self:
            if record.unbuild_id and record.unbuild_id.state == 'done':
                raise UserError(_("Cannot delete unbuild lines when unbuild order is in Done state."))
        
        return super(MrpUnbuildLine, self).unlink()
    
class StockMove(models.Model):
    _inherit = 'stock.move'

    def write(self, vals):
        # Cek jika manufacturing order terkait sudah done
        for record in self:
            if (record.raw_material_production_id and record.raw_material_production_id.state == 'done') or \
               (record.production_id and record.production_id.state == 'done') or \
               (record.unbuild_id and record.unbuild_id.state == 'done'):
                raise UserError(_("Cannot modify stock moves linked to a done manufacturing or unbuild order."))
        
        return super(StockMove, self).write(vals)
    
    def unlink(self):
        # Cek jika manufacturing order terkait sudah done
        for record in self:
            if (record.raw_material_production_id and record.raw_material_production_id.state == 'done') or \
               (record.production_id and record.production_id.state == 'done') or \
               (record.unbuild_id and record.unbuild_id.state == 'done'):
                raise UserError(_("Cannot delete stock moves linked to a done manufacturing or unbuild order."))
        
        return super(StockMove, self).unlink()