from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

import logging

_logger = logging.getLogger(__name__)

# Nama operation type yang dipakai WH untuk Transfer Out. Dipakai sebagai default,
# bisa dioverride lewat ir.config_parameter kalau di DB client namanya beda.
# PENTING: endpoint /api/transfer_stock_out/ di dev_pos memfilter
# picking_type_id.name = 'TS Out', jadi kalau nama ini diganti, SAP tidak akan
# menarik Transfer Out yang dibuat dari sini.
DEFAULT_TRANSFER_OUT_PICKING_TYPE = 'TS Out'
PICKING_TYPE_PARAM = 'vit_transfer_request.transfer_out_picking_type_name'


class TransferRequest(models.Model):
    _name = 'transfer.request'
    _description = 'Transfer Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'
    _rec_name = 'doc_num'

    REQUEST_TYPE_SELECTION = [
        ('allocation', 'Alokasi Stock ke Store'),
        ('borrow', 'Peminjaman ke WH'),
    ]

    doc_num = fields.Char(string='Request Number', readonly=True, copy=False, tracking=True)
    request_date = fields.Datetime(string='Request Date', required=True, tracking=True,
                                   default=fields.Datetime.now)
    scheduled_date = fields.Datetime(string='Scheduled Date', tracking=True)
    request_type = fields.Selection(selection=REQUEST_TYPE_SELECTION, string='Request Type',
                                     required=True, default='allocation', tracking=True,
                                     help='Alokasi Stock ke Store: MD mengalokasikan stock WH ke store. '
                                          'Peminjaman ke WH: MD meminta pinjam stock dari WH.')
    transfer_type_id = fields.Many2one('transfer.type', string='Transfer Type', tracking=True,
                                        help='Jenis transaksi. Diteruskan ke Transfer Out yang dibuat dari request ini.')

    # Sumber barang (umumnya WH) dan tujuan barang (store / MD)
    warehouse_id = fields.Many2one('stock.warehouse', string='Source Warehouse', required=True, tracking=True)
    location_id = fields.Many2one('stock.location', string='Source Location', required=True, tracking=True,
                                   domain="[('usage', 'in', ('internal', 'transit'))]")
    warehouse_dest_id = fields.Many2one('stock.warehouse', string='Destination Warehouse', tracking=True)
    location_dest_id = fields.Many2one('stock.location', string='Destination Location', required=True, tracking=True,
                                        domain="[('usage', 'in', ('internal', 'transit'))]")

    requested_by_id = fields.Many2one('res.users', string='Requested By', tracking=True,
                                       default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                  default=lambda self: self.env.company)
    vit_notes = fields.Text(string='Keterangan')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('to_approve', 'To Approve'),
        ('approved', 'Approved'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', required=True, readonly=True, copy=False, tracking=True)

    line_ids = fields.One2many('transfer.request.line', 'request_id', string='Request Lines', copy=True)

    # Dipakai integrasi SAP, mengikuti pola dev_pos
    vit_trxid = fields.Char(string='Transaction ID', default=False, tracking=True)
    is_integrated = fields.Boolean(string='Integrated', default=False, readonly=True, tracking=True)

    picking_ids = fields.One2many('stock.picking', 'vit_transfer_request_id', string='Transfer Out')
    picking_count = fields.Integer(string='Transfer Out Count', compute='_compute_picking_count')
    total_qty_requested = fields.Float(string='Total Requested', compute='_compute_total_qty', digits=(16, 3))
    total_qty_transferred = fields.Float(string='Total Transferred', compute='_compute_total_qty', digits=(16, 3))

    _sql_constraints = [
        ('doc_num_uniq', 'unique(doc_num)', 'Request Number harus unik.'),
    ]

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for record in self:
            record.picking_count = len(record.picking_ids)

    @api.depends('line_ids.product_uom_qty', 'line_ids.qty_transferred')
    def _compute_total_qty(self):
        for record in self:
            record.total_qty_requested = sum(record.line_ids.mapped('product_uom_qty'))
            record.total_qty_transferred = sum(record.line_ids.mapped('qty_transferred'))

    @api.constrains('location_id', 'location_dest_id')
    def _check_locations(self):
        for record in self:
            if record.location_id and record.location_id == record.location_dest_id:
                raise ValidationError(_("Source Location dan Destination Location tidak boleh sama."))

    @api.onchange('warehouse_id')
    def _onchange_warehouse_id(self):
        """Isi otomatis source location dari stock location warehouse."""
        if self.warehouse_id:
            self.location_id = self.warehouse_id.lot_stock_id

    @api.onchange('warehouse_dest_id')
    def _onchange_warehouse_dest_id(self):
        """Isi otomatis destination location. Pakai transit location kalau ada,
        karena konvensi TS Out di repo ini mengirim barang ke transit dulu."""
        if self.warehouse_dest_id:
            self.location_dest_id = self.warehouse_dest_id.location_transit or self.warehouse_dest_id.lot_stock_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('doc_num'):
                vals['doc_num'] = self.env['ir.sequence'].next_by_code('transfer.request.doc.num') or '/'
        return super(TransferRequest, self).create(vals_list)

    def unlink(self):
        for record in self:
            if record.state not in ('draft', 'cancel'):
                raise UserError(_("Transfer Request %s tidak bisa dihapus karena statusnya %s.",
                                  record.doc_num, record.state))
        return super(TransferRequest, self).unlink()

    # ------------------------------------------------------------------
    # Workflow IT-01: MD membuat dan approve Transfer Request
    # ------------------------------------------------------------------
    def action_submit(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_("Hanya request dengan status Draft yang bisa disubmit."))
            if not record.line_ids:
                raise UserError(_("Transfer Request %s belum punya item.", record.doc_num))
            record.state = 'to_approve'

    def action_approve(self):
        for record in self:
            if record.state != 'to_approve':
                raise UserError(_("Hanya request dengan status To Approve yang bisa di-approve."))
            record.state = 'approved'

    def action_cancel(self):
        for record in self:
            if record.state == 'done':
                raise UserError(_("Transfer Request %s sudah Done, tidak bisa dibatalkan.", record.doc_num))
            if record.picking_ids.filtered(lambda p: p.state not in ('cancel',)):
                raise UserError(_("Batalkan dulu Transfer Out yang terkait dengan request %s.", record.doc_num))
            record.state = 'cancel'

    def action_reset_draft(self):
        for record in self:
            if record.state not in ('to_approve', 'approved', 'cancel'):
                raise UserError(_("Request %s tidak bisa dikembalikan ke Draft.", record.doc_num))
            if record.picking_ids:
                raise UserError(_("Request %s sudah punya Transfer Out, tidak bisa dikembalikan ke Draft.",
                                  record.doc_num))
            record.state = 'draft'

    # ------------------------------------------------------------------
    # Workflow IT-02: WH membuat Transfer Out berdasarkan Transfer Request
    # ------------------------------------------------------------------
    def _get_transfer_out_picking_type(self):
        """Cari operation type TS Out milik source warehouse."""
        self.ensure_one()
        picking_type_name = self.env['ir.config_parameter'].sudo().get_param(
            PICKING_TYPE_PARAM, DEFAULT_TRANSFER_OUT_PICKING_TYPE)

        domain = [('name', '=', picking_type_name), ('code', '=', 'internal')]
        picking_type = self.env['stock.picking.type'].search(
            domain + [('warehouse_id', '=', self.warehouse_id.id)], limit=1)
        if not picking_type:
            # fallback: operation type TS Out tanpa warehouse spesifik
            picking_type = self.env['stock.picking.type'].search(domain, limit=1)
        if not picking_type:
            raise UserError(_("Operation Type '%s' tidak ditemukan untuk warehouse %s.",
                              picking_type_name, self.warehouse_id.name))
        return picking_type

    def _prepare_transfer_out_values(self, picking_type, lines):
        """Siapkan vals stock.picking + move lines dari sisa qty request."""
        self.ensure_one()
        move_vals = []
        for line_number, line in enumerate(lines, start=1):
            move_vals.append((0, 0, {
                'name': line.product_id.name,
                'product_id': line.product_id.id,
                'product_uom': line.product_uom_id.id,
                'product_uom_qty': line.qty_remaining,
                'location_id': self.location_id.id,
                'location_dest_id': self.location_dest_id.id,
                'vit_line_number_sap': line_number,
                'vit_transfer_request_line_id': line.id,
            }))

        return {
            'picking_type_id': picking_type.id,
            'location_id': self.location_id.id,
            'location_dest_id': self.location_dest_id.id,
            'scheduled_date': self.scheduled_date or self.request_date,
            'origin': self.doc_num,
            'company_id': self.company_id.id,
            'vit_transfer_type_id': self.transfer_type_id.id,
            'vit_transfer_request_id': self.id,
            'move_ids_without_package': move_vals,
        }

    def action_create_transfer_out(self):
        self.ensure_one()
        if self.state not in ('approved', 'in_progress'):
            raise UserError(_("Transfer Out hanya bisa dibuat dari request yang sudah Approved."))

        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        lines = self.line_ids.filtered(
            lambda l: float_compare(l.qty_remaining, 0.0, precision_digits=precision) > 0)
        if not lines:
            raise UserError(_("Semua item pada request %s sudah ditransfer.", self.doc_num))

        picking_type = self._get_transfer_out_picking_type()
        picking = self.env['stock.picking'].create(
            self._prepare_transfer_out_values(picking_type, lines))

        self.message_post(body=_("Transfer Out %s dibuat dari request ini.", picking.name))
        if self.state == 'approved':
            self.state = 'in_progress'

        return {
            'type': 'ir.actions.act_window',
            'name': _('Transfer Out'),
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_transfer_out(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Transfer Out'),
            'res_model': 'stock.picking',
            'view_mode': 'tree,form',
            'domain': [('vit_transfer_request_id', '=', self.id)],
            'context': {'create': False},
        }

    def _update_fulfilment_state(self):
        """Dipanggil setelah Transfer Out divalidasi, untuk maju ke In Progress / Done."""
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for record in self:
            if record.state not in ('approved', 'in_progress'):
                continue
            lines = record.line_ids
            if not lines:
                continue
            fully_transferred = all(
                float_compare(line.qty_remaining, 0.0, precision_digits=precision) <= 0
                for line in lines)
            if fully_transferred:
                record.state = 'done'
            elif any(not float_is_zero(line.qty_transferred, precision_digits=precision)
                     for line in lines):
                record.state = 'in_progress'


class TransferRequestLine(models.Model):
    _name = 'transfer.request.line'
    _description = 'Transfer Request Line'
    _order = 'request_id, id'

    request_id = fields.Many2one('transfer.request', string='Transfer Request', required=True,
                                  ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True,
                                  domain="[('type', 'in', ('product', 'consu'))]")
    product_code = fields.Char(string='Product Code', related='product_id.default_code', readonly=True)
    product_uom_qty = fields.Float(string='Requested Qty', required=True, default=1.0, digits=(16, 3))
    product_uom_id = fields.Many2one('uom.uom', string='UoM', required=True)
    vit_notes = fields.Char(string='Keterangan')
    vit_line_number_sap = fields.Integer(string='Line Number SAP')

    move_ids = fields.One2many('stock.move', 'vit_transfer_request_line_id', string='Stock Moves')
    qty_transferred = fields.Float(string='Transferred Qty', compute='_compute_qty_transferred',
                                    store=True, digits=(16, 3))
    qty_remaining = fields.Float(string='Remaining Qty', compute='_compute_qty_transferred',
                                  store=True, digits=(16, 3))

    @api.depends('product_uom_qty', 'move_ids.state', 'move_ids.quantity')
    def _compute_qty_transferred(self):
        for line in self:
            done_moves = line.move_ids.filtered(lambda m: m.state == 'done')
            transferred = sum(done_moves.mapped('quantity'))
            line.qty_transferred = transferred
            line.qty_remaining = max(line.product_uom_qty - transferred, 0.0)

    @api.constrains('product_uom_qty')
    def _check_product_uom_qty(self):
        for line in self:
            if line.product_uom_qty <= 0:
                raise ValidationError(_("Requested Qty untuk produk %s harus lebih besar dari 0.",
                                        line.product_id.display_name))

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id
