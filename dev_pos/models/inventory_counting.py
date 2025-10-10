from odoo import models, fields, api
from pytz import timezone
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError

class InventoryStock(models.Model):
    _name = "inventory.stock"
    _description = "Inventory Stock"
    _rec_name = 'doc_num'

    doc_num = fields.Char(string="Internal Reference")
    warehouse_id = fields.Many2one('stock.warehouse', string="Warehouse")
    location_id = fields.Many2one('stock.location', string="Location")
    company_id = fields.Many2one('res.company', string="Company")
    create_date = fields.Datetime(string="Created Date")
    from_date = fields.Datetime(string="From Date")
    to_date = fields.Datetime(string="To Date")
    inventory_date = fields.Datetime(string="Inventory Date")
    total_qty = fields.Float(string="Total Product Quantity", _compute='_compute_total_quantity')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('counted', 'Counted'),
    ], string='Status', default='draft', required=True, readonly=True, copy=False, tracking=True)
    inventory_counting_ids = fields.One2many('inventory.counting', 'inventory_counting_id', string='Inventory Countings')

    barcode_input = fields.Char(string="Scan Barcode", readonly=False)
    vit_notes = fields.Text(string="Keterangan", readonly=False, tracking=True)

    # inventory_count = fields.Integer(string='Count', compute='_compute_stock_count')

    def action_closed(self):
        """Ubah status menjadi closed, data tidak bisa diubah lagi"""
        for record in self:
            if record.state != 'counted':
                raise ValidationError("Hanya inventory dengan status 'Counted' yang bisa di-closed.")
            
            record.state = 'closed'
            for line in record.inventory_counting_ids:
                line.state = 'closed'
        
        return True

    @api.model
    def default_get(self, fields_list):
        """Override default_get to automatically populate certain fields when creating a new record."""
        res = super(InventoryStock, self).default_get(fields_list)
        
        # Set default create_date and inventory_date to current datetime
        current_datetime = fields.Datetime.now()
        if 'create_date' in fields_list:
            res['create_date'] = current_datetime
        if 'inventory_date' in fields_list:
            res['inventory_date'] = current_datetime
        
        # Set default company_id to the user's current company
        if 'company_id' in fields_list:
            res['company_id'] = self.env.company.id
        
        # Set default warehouse - get the first warehouse associated with the current company
        if 'warehouse_id' in fields_list:
            warehouse = self.env['stock.warehouse'].search([
                ('company_id', '=', self.env.company.id)
            ], limit=1)
            if warehouse:
                res['warehouse_id'] = warehouse.id
                
                # Also trigger location setting if warehouse is set and location is in fields_list
                if 'location_id' in fields_list and warehouse.view_location_id:
                    # Find stock location under this warehouse's view_location
                    stock_location = self.env['stock.location'].search([
                        ('location_id', '=', warehouse.view_location_id.id),
                        ('name', '=', 'Stock')
                    ], limit=1)
                    if stock_location:
                        res['location_id'] = stock_location.id
        
        return res
    
    @api.onchange('warehouse_id')
    def _onchange_warehouse_id(self):
        """Isi otomatis location_id berdasarkan warehouse_id dan parent location."""
        if self.warehouse_id:
            # Ambil root lokasi dari warehouse
            root_location = self.warehouse_id.view_location_id
            
            if root_location:
                # Cari semua lokasi dengan parent = root_location.id
                child_locations = self.env['stock.location'].search([
                    ('location_id', '=', root_location.id),
                    ('name', '=', "Stock")
                ])
                self.location_id = child_locations
            else:
                self.location_id = False
        else:
            self.location_id = False

    def action_in_progress(self):
        for record in self:
            record.state = 'in_progress'
            record.barcode_input = ''  # Reset input dulu

            for line in record.inventory_counting_ids:
                line.write({'state': 'in_progress'})
    def action_start_counting(self):
        """Update qty_hand for each inventory.counting line based on the balance_stock table."""
        for record in self:
            record.state = 'counted' 
            for line in record.inventory_counting_ids:
                line.state = 'counted'

class InventoryCounting(models.Model):
    _name = "inventory.counting"
    _description = "Inventory Counting"

    inventory_counting_id = fields.Many2one('inventory.stock', string="Inventory Counting")
    inventory_stock_id = fields.Many2one('inventory.stock', string="Inventory Stock", ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Product")
    location_id = fields.Many2one('stock.location', string="Location")
    inventory_date = fields.Datetime(string="Inventory Date")
    lot_id = fields.Many2one('stock.lot', string="Lot/Serial Number")
    expiration_date = fields.Datetime(string="Expiration Date")
    qty_hand = fields.Float(string="On Hand", store=True)
    counted_qty = fields.Float(string="Counted", store=True)
    difference_qty = fields.Float(string="Difference", store=True)
    uom_id = fields.Many2one('uom.uom', string="UOM")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('counted', 'Counted'),
    ], string='Status', default='draft', required=True, readonly=True, copy=False, tracking=True)
    is_edit = fields.Boolean(string="Edit")

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """
        When product_id is filled, automatically set location_id 
        from the parent inventory.stock record
        """
        if self.product_id and self.inventory_counting_id:
            if self.inventory_counting_id.location_id:
                self.location_id = self.inventory_counting_id.location_id
                self.uom_id = self.product_id.uom_id.id
