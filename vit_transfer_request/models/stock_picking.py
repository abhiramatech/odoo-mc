from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare

TS_IN_GROUP = 'vit_transfer_request.group_ts_in_creator'
TS_OUT_NAME = 'TS Out'
TS_IN_NAME = 'TS In'


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    vit_transfer_request_id = fields.Many2one('transfer.request', string='Transfer Request',
                                               readonly=True, index=True, copy=False,
                                               help='Transfer Request (MD) yang menjadi dasar Transfer Out ini.')
    vit_transfer_type_id = fields.Many2one('transfer.type', string='Transfer Type',
                                            help='Jenis transaksi untuk Transfer Out.')
    transfer_out_id = fields.Many2one('stock.picking', string='TS Out Reference',
                                       domain="[('picking_type_id.name', '=', 'TS Out')]",
                                       index=True, copy=False,
                                       help='Dokumen TS Out yang menjadi dasar TS In ini. '
                                            'Wajib diisi pada dokumen TS In.')
    vit_is_ts_in = fields.Boolean(string='Is TS In', compute='_compute_vit_is_ts_in',
                                   help='Technical: dokumen ini memakai operation type TS In.')
    vit_is_ts_out = fields.Boolean(string='Is TS Out', compute='_compute_vit_is_ts_out',
                                    help='Technical: dokumen ini memakai operation type TS Out.')
    ts_in_ids = fields.One2many('stock.picking', 'transfer_out_id', string='TS In')
    ts_in_count = fields.Integer(string='TS In', compute='_compute_ts_in_count')

    @staticmethod
    def _vit_normalize_type_name(name):
        """Samakan nama operation type: abaikan huruf besar/kecil dan spasi
        berlebih/tersembunyi (termasuk non-breaking space)."""
        return ' '.join((name or '').split()).casefold()

    def _vit_type_matches(self, picking_type, target):
        """True kalau nama operation type == target (toleran: huruf besar/kecil, spasi,
        dan dicek di bahasa user + en_US karena name translatable)."""
        wanted = self._vit_normalize_type_name(target)
        names = {
            self._vit_normalize_type_name(picking_type.name),
            self._vit_normalize_type_name(picking_type.with_context(lang='en_US').name),
        }
        return wanted in names

    @api.depends('picking_type_id.name')
    def _compute_vit_is_ts_in(self):
        for picking in self:
            picking.vit_is_ts_in = self._vit_type_matches(picking.picking_type_id, TS_IN_NAME)

    @api.depends('picking_type_id.name')
    def _compute_vit_is_ts_out(self):
        for picking in self:
            picking.vit_is_ts_out = self._vit_type_matches(picking.picking_type_id, TS_OUT_NAME)

    @api.depends('ts_in_ids.state')
    def _compute_ts_in_count(self):
        for picking in self:
            picking.ts_in_count = len(picking.ts_in_ids.filtered(lambda p: p.state != 'cancel'))

    # ------------------------------------------------------------------
    # TS Out -> TS In
    # ------------------------------------------------------------------
    def _check_ts_in_access(self):
        if not self.env.user.has_group(TS_IN_GROUP):
            raise AccessError(_("Kamu tidak punya hak akses untuk membuat / melihat dokumen TS In."))

    def _get_ts_in_picking_type(self):
        """Operation type TS In; utamakan milik warehouse tujuan TS Out."""
        self.ensure_one()
        # filter di Python (bukan ilike) supaya nama dengan spasi tersembunyi tetap ketemu;
        # jumlah operation type kecil, jadi aman.
        types = self.env['stock.picking.type'].search([]).filtered(
            lambda t: self._vit_type_matches(t, TS_IN_NAME))
        if not types:
            raise UserError(_("Operation Type '%s' tidak ditemukan.", TS_IN_NAME))
        dest_warehouse = self.location_dest_id.warehouse_id
        preferred = types.filtered(lambda t: t.warehouse_id == dest_warehouse) if dest_warehouse else types.browse()
        return (preferred or types)[:1]

    def _prepare_ts_in_values(self, picking_type, move_vals):
        self.ensure_one()
        dest_location = picking_type.default_location_dest_id or picking_type.warehouse_id.lot_stock_id
        if not dest_location:
            raise UserError(_("Operation Type %s belum punya Default Destination Location / warehouse.",
                              picking_type.display_name))
        if dest_location == self.location_dest_id:
            raise UserError(_("Lokasi tujuan TS In (%s) sama dengan lokasi asalnya (tujuan TS Out). "
                              "Cek Default Destination Location pada Operation Type %s.",
                              dest_location.display_name, picking_type.display_name))
        for _cmd, _id, vals in move_vals:
            vals['location_dest_id'] = dest_location.id
        return {
            'picking_type_id': picking_type.id,
            'location_id': self.location_dest_id.id,
            'location_dest_id': dest_location.id,
            'origin': self.name,
            'company_id': self.company_id.id,
            'vit_transfer_type_id': self.vit_transfer_type_id.id,
            'transfer_out_id': self.id,
            'move_ids_without_package': move_vals,
        }

    def action_create_ts_in(self):
        """Buat TS In dari TS Out (sisa qty yang belum dibuatkan TS In)."""
        self.ensure_one()
        self._check_ts_in_access()
        if not self.vit_is_ts_out:
            raise UserError(_("TS In hanya bisa dibuat dari dokumen TS Out."))
        if self.state in ('done', 'cancel'):
            raise UserError(_("TS In hanya bisa dibuat selagi TS Out belum Done / Cancel."))

        out_moves = self.move_ids.filtered(lambda m: m.state != 'cancel')
        existing = self.env['stock.move'].search([
            ('vit_ts_out_move_id', 'in', out_moves.ids), ('state', '!=', 'cancel')])
        taken = {}
        for move in existing:
            taken[move.vit_ts_out_move_id.id] = taken.get(move.vit_ts_out_move_id.id, 0.0) + move.product_uom_qty

        move_vals = []
        for line_number, move in enumerate(out_moves, start=1):
            remaining = move.product_uom_qty - taken.get(move.id, 0.0)
            if float_compare(remaining, 0.0, precision_rounding=move.product_uom.rounding) <= 0:
                continue
            move_vals.append((0, 0, {
                'name': move.product_id.display_name,
                'product_id': move.product_id.id,
                'product_uom': move.product_uom.id,
                'product_uom_qty': remaining,
                'location_id': self.location_dest_id.id,
                'location_dest_id': self.location_dest_id.id,  # ditimpa di _prepare_ts_in_values
                'vit_line_number_sap': line_number,
                'vit_ts_out_move_id': move.id,
            }))
        if not move_vals:
            raise UserError(_("Semua item pada %s sudah dibuatkan TS In.", self.name))

        picking_type = self._get_ts_in_picking_type()
        ts_in = self.env['stock.picking'].create(self._prepare_ts_in_values(picking_type, move_vals))
        self.message_post(body=_("TS In %s dibuat dari dokumen ini.", ts_in.name))
        return {
            'type': 'ir.actions.act_window',
            'name': _('TS In'),
            'res_model': 'stock.picking',
            'res_id': ts_in.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_ts_in(self):
        self.ensure_one()
        self._check_ts_in_access()
        return {
            'type': 'ir.actions.act_window',
            'name': _('TS In'),
            'res_model': 'stock.picking',
            'view_mode': 'tree,form',
            'domain': [('transfer_out_id', '=', self.id)],
            'context': {'create': False},
        }


class StockMove(models.Model):
    _inherit = 'stock.move'

    vit_transfer_request_line_id = fields.Many2one('transfer.request.line', string='Transfer Request Line',
                                                    readonly=True, index=True, copy=False)
    vit_ts_out_move_id = fields.Many2one('stock.move', string='TS Out Move',
                                          readonly=True, index=True, copy=False,
                                          help='Move pada TS Out yang menjadi dasar move TS In ini.')

    def _action_done(self, *args, **kwargs):
        """Hook di move, bukan di button_validate, supaya progress request tetap benar
        walaupun Transfer Out-nya lewat wizard backorder / immediate transfer (IT-02)."""
        moves_done = super(StockMove, self)._action_done(*args, **kwargs)
        requests = moves_done.vit_transfer_request_line_id.request_id
        if requests:
            requests._update_fulfilment_state()
        return moves_done
