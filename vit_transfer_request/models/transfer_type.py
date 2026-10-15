from odoo import models, fields


class TransferType(models.Model):
    """Master data jenis transaksi untuk Transfer Out.

    ToBeDesign CDK Sales v1.0, bab 5 Requirement Tambahan no. 3:
    "Penambahan inputan transfer type pada Transfer Out POSVIT".

    Isinya sengaja cuma jenis transaksinya saja, tanpa keterangan/skenario.
    """
    _name = 'transfer.type'
    _description = 'Transfer Type'
    _order = 'name'

    name = fields.Char(string='Jenis Transaksi', required=True)
    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Jenis Transaksi ini sudah ada.'),
    ]
