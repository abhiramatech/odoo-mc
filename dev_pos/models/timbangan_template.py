import base64
import csv
from io import StringIO
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class ExportTimbanganLine(models.TransientModel):
    _name = 'export.timbangan.line'
    _description = 'Timbangan Detail Line'

    wizard_id = fields.Many2one('export.timbangan.wizard', string="Wizard", ondelete='cascade')
    item_code = fields.Char(string='Item Code')
    barcode = fields.Char(string='Barcode')
    item_name = fields.Char(string='Item Name')
    uom_id = fields.Many2one('uom.uom', string='UOM')
    price_unit = fields.Float(string='Price')
    berat_timbangan = fields.Float(string='Berat Timbangan')


class ExportTimbanganWizard(models.TransientModel):
    _name = 'export.timbangan.wizard'
    _description = 'Export Timbangan CSV'

    export_type = fields.Selection([
        ('single', 'Single Barcode'),
        ('multi', 'Multiple Barcode')
    ], string='Barcode Mode', required=True)

    line_ids = fields.One2many('export.timbangan.line', 'wizard_id', string="Lines")
    export_file = fields.Binary('Exported File')
    file_name = fields.Char('Filename')

    def action_generate_all_products(self):
        if not self.export_type:
            raise ValidationError("Silakan pilih Barcode Mode terlebih dahulu.")

        self.line_ids.unlink()

        products = self.env['product.product'].with_context(active_test=False).search([
            ('to_weight', '=', True)
        ])
        product_data = products.read(['id', 'default_code', 'barcode', 'name', 'uom_id', 'lst_price'])

        BATCH_SIZE = 1000
        for i in range(0, len(product_data), BATCH_SIZE):
            batch = product_data[i:i + BATCH_SIZE]
            vals_list = []

            for prod in batch:
                prod_id = prod['id']
                barcode = ''

                if self.export_type == 'single':
                    barcode = prod.get('barcode') or ''
                elif self.export_type == 'multi':
                    multi_barcodes = self.env['multiple.barcode'].search([('product_id', '=', prod_id)])
                    barcode = '|'.join(multi_barcodes.mapped('barcode'))

                vals_list.append({
                    'item_code': prod.get('default_code'),
                    'barcode': barcode,
                    'item_name': prod.get('name'),
                    'uom_id': prod['uom_id'][0] if prod.get('uom_id') else False,
                    'price_unit': prod.get('lst_price'),
                    'berat_timbangan': 100,
                })

            self.write({'line_ids': [(0, 0, val) for val in vals_list]})

        # ✅ This keeps the wizard open
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'export.timbangan.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }


    def action_export(self):
        """Export data to CSV"""
        if not self.line_ids:
            raise UserError("Tidak ada data untuk diekspor.")

        csv_buffer = StringIO()
        writer = csv.writer(csv_buffer)
        
        # Format: Barcode,Item_Code,Item_Name,Berat+UOM,Price
        for rec in self.line_ids:
            # Gabungkan berat dengan UOM (capital, tanpa koma)
            uom_name = rec.uom_id.name.upper() if rec.uom_id else 'G'
            berat_int = int(rec.berat_timbangan or 100)  # Convert to int to remove decimal
            berat_uom = f"{berat_int}{uom_name}"
            
            # Price as integer (tanpa koma)
            price_int = int(rec.price_unit or 0)
            
            writer.writerow([
                rec.barcode or '',  # Column A: Barcode
                rec.item_code or '',  # Column B: Item code
                rec.item_name or '',  # Column C: Item name
                berat_uom,  # Column D: Berat + UOM (100G)
                price_int  # Column E: Price (100)
            ])

        self.export_file = base64.b64encode(csv_buffer.getvalue().encode())
        
        # Generate filename with sequence directly in action_export
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d")
        
        # Get or create sequence for timbangan export
        sequence = self.env['ir.sequence'].sudo().search([
            ('code', '=', 'timbangan.export'),
            ('company_id', 'in', [self.env.company.id, False])
        ], limit=1)
        
        if not sequence:
            # Create sequence if it doesn't exist
            sequence = self.env['ir.sequence'].sudo().create({
                'name': 'Timbangan Export Sequence',
                'code': 'timbangan.export',
                'prefix': 'TIM',
                'suffix': '',
                'padding': 4,
                'number_increment': 1,
                'number_next': 1,
                'company_id': self.env.company.id,
            })
        
        # Get next sequence number
        seq_number = sequence.next_by_id()
        
        # Generate filename: timbangan_export_YYYYMMDD_TIM0001.csv
        self.file_name = f"Timbangan_Template_{date_str}_{seq_number}.csv"
        
        csv_buffer.close()

        return {
            'type': 'ir.actions.act_url',
            'url': f"/web/content/?model=export.timbangan.wizard&id={self.id}&field=export_file&download=true&filename={self.file_name}",
            'target': 'self',
        }