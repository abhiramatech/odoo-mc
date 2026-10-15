from odoo import models, fields


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    vit_transfer_request_id = fields.Many2one('transfer.request', string='Transfer Request',
                                               readonly=True, index=True, copy=False,
                                               help='Transfer Request (MD) yang menjadi dasar Transfer Out ini.')
    vit_transfer_type_id = fields.Many2one('transfer.type', string='Transfer Type',
                                            help='Jenis transaksi untuk Transfer Out.')


class StockMove(models.Model):
    _inherit = 'stock.move'

    vit_transfer_request_line_id = fields.Many2one('transfer.request.line', string='Transfer Request Line',
                                                    readonly=True, index=True, copy=False)

    def _action_done(self, *args, **kwargs):
        """Hook di move, bukan di button_validate, supaya progress request tetap benar
        walaupun Transfer Out-nya lewat wizard backorder / immediate transfer (IT-02)."""
        moves_done = super(StockMove, self)._action_done(*args, **kwargs)
        requests = moves_done.vit_transfer_request_line_id.request_id
        if requests:
            requests._update_fulfilment_state()
        return moves_done
