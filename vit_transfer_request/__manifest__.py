{
    'name': 'VIT Transfer Request MC',
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'sequence': 1,
    'summary': """Belong to VIT""",
    'description': """
Transfer Request untuk Master Console (MC).

Mengacu ToBeDesign CDK Sales v1.0, bab 6.4.1 (Proses Alokasi dan peminjaman dari WH):
    IT-01  MD  membuat Transfer Request                 -> SAP: Transfer Request
    IT-02  WH  membuat Transfer Out dari Transfer Request -> SAP: Inventory Transfer
    IT-03  Store/MD membuat Transfer In                  -> sisi Store Server (di luar scope)

Termasuk juga bab 5 Requirement Tambahan no. 3: master data Transfer Type
(jenis transaksi) dan inputannya pada Transfer Out.

Modul ini hanya menambah di sisi MC, tidak ada perubahan di POSVIT Store.
    """,
    'author': 'Visi Intech',
    'company': 'Visi Intech',
    'maintainer': 'Visi Intech',
    'website': "https://www.Visi-Intech.com",
    'depends': ['base', 'stock', 'dev_pos'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_transfer_request.xml',
        'views/transfer_type_view.xml',
        'views/transfer_request_view.xml',
        'views/stock_picking_view.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
