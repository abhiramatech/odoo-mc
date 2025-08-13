from odoo import http, fields
from odoo.http import request


class SalesReportDetailController(http.Controller):

    @http.route('/sales/report/detail', type='http', auth='user', website=True)
    def portal_sales_report_detail(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        invoice_no = kw.get('invoice_no')
        pos_order_ref = kw.get('pos_order_ref')

        # Validasi parameter wajib
        if not date_from or not date_to:
            return request.not_found()

        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
        ]

        if invoice_no:
            move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)
            if move:
                domain.append(('account_move', '=', move.id))

        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)

        values = {
            'orders': orders,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
        }
        return request.render('dev_pos.report_sales_detail', values)

    @http.route('/sales/report/recap', type='http', auth='user', website=True)
    def portal_sales_report_recap(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        invoice_no = kw.get('invoice_no')
        pos_order_ref = kw.get('pos_order_ref')

        # Validasi parameter wajib
        if not date_from or not date_to:
            return request.not_found()

        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
        ]

        if invoice_no:
            move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)
            if move:
                domain.append(('account_move', '=', move.id))

        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)

        values = {
            'orders': orders,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
        }
        return request.render('dev_pos.report_sales_recap', values)

    @http.route('/sales/report/spending', type='http', auth='user', website=True)
    def portal_sales_report_spending(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        # invoice_no = kw.get('invoice_no')
        # pos_order_ref = kw.get('pos_order_ref')

        # Validasi parameter wajib
        if not date_from or not date_to:
            return request.not_found()

        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
        ]

        # if invoice_no:
        #     move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)
        #     if move:
        #         domain.append(('account_move', '=', move.id))

        # if pos_order_ref:
        #     domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)

        values = {
            'orders': orders,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
        }
        return request.render('dev_pos.report_sales_spending', values)
    
    @http.route('/sales/report/hourly', type='http', auth='user', website=True)
    def portal_sales_report_hourly(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        # invoice_no = kw.get('invoice_no')
        # pos_order_ref = kw.get('pos_order_ref')

        # Validasi parameter wajib
        if not date_from or not date_to:
            return request.not_found()

        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
        ]

        # if invoice_no:
        #     move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)
        #     if move:
        #         domain.append(('account_move', '=', move.id))

        # if pos_order_ref:
        #     domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)

        values = {
            'orders': orders,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
        }
        return request.render('dev_pos.report_sales_hourly', values)


    @http.route('/sales/report/hourly_category', type='http', auth='user', website=True)
    def portal_sales_report_hourly_category(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        invoice_no = kw.get('invoice_no')
        pos_order_ref = kw.get('pos_order_ref')

        # Validasi parameter wajib
        if not date_from or not date_to:
            return request.not_found()

        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
        ]

        if invoice_no:
            move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)
            if move:
                domain.append(('account_move', '=', move.id))

        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)

        values = {
            'orders': orders,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
        }
        return request.render('dev_pos.report_sales_hourly_category', values)


    @http.route('/sales/report/hourly_payment', type='http', auth='user', website=True)
    def portal_sales_report_hourly_payment(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        invoice_no = kw.get('invoice_no')
        pos_order_ref = kw.get('pos_order_ref')

        # Validasi parameter wajib
        if not date_from or not date_to:
            return request.not_found()

        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
        ]

        if invoice_no:
            move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)
            if move:
                domain.append(('account_move', '=', move.id))

        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)

        values = {
            'orders': orders,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
        }
        return request.render('dev_pos.report_sales_hourly_payment', values)


    @http.route('/sales/report/contribution_by_brand', type='http', auth='user', website=True)
    def portal_sales_report_contribution_by_brand(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        invoice_no = kw.get('invoice_no')
        pos_order_ref = kw.get('pos_order_ref')

        # Validasi parameter wajib
        if not date_from or not date_to:
            return request.not_found()

        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
        ]

        if invoice_no:
            move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)
            if move:
                domain.append(('account_move', '=', move.id))

        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)

        values = {
            'orders': orders,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
        }
        return request.render('dev_pos.report_sales_contribution_by_brand', values)


    @http.route('/sales/report/contribution_by_category', type='http', auth='user', website=True)
    def portal_sales_report_contribution_by_category(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        invoice_no = kw.get('invoice_no')
        pos_order_ref = kw.get('pos_order_ref')

        # Validasi parameter wajib
        if not date_from or not date_to:
            return request.not_found()

        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
        ]

        if invoice_no:
            move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)
            if move:
                domain.append(('account_move', '=', move.id))

        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)

        values = {
            'orders': orders,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
        }
        return request.render('dev_pos.report_sales_contribution_by_category', values)


    