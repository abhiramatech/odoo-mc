import json
import werkzeug.exceptions
from odoo.exceptions import ValidationError
from odoo import http, _, fields
from odoo.http import request
import pytz
import re
import decimal
from .api_utils import check_authorization, paginate_records, serialize_response, serialize_error_response
import base64

import logging
_logger = logging.getLogger(__name__)

class GETEmployee(http.Controller):
    @http.route(['/api/hr_employee/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_employees(self, employee_code=None, name=None, pageSize=200, page=1, is_sales=None, **params):
        try:
            check_authorization()

            if int(page) == 0:
                return serialize_response([], 0, 0)

            domain = []

            # Filtering
            if employee_code:
                domain.append(('vit_employee_code', '=', employee_code))
            if name:
                domain.append(('name', 'ilike', name))
            if is_sales is not None:
                is_sales_bool = str(is_sales).lower() == 'true'
                domain.append(('is_sales', '=', is_sales_bool))

            pageSize = int(pageSize) if pageSize else 200

            if not employee_code and not name and is_sales is None:
                employees = request.env['hr.employee'].sudo().search([])
                total_records = len(employees)
            else:
                employees = request.env['hr.employee'].sudo().search(domain)
                total_records = len(employees)

            # Apply pagination if not filtering by name
            if not name:
                employees, total_records = paginate_records('hr.employee', domain, pageSize, page)

            data = []
            for emp in employees:
                data.append({
                    'id': emp.id,
                    'employee_code': emp.vit_employee_code,
                    'name': emp.name,
                    'job_title': emp.job_title,
                    'department_id': emp.department_id.id,
                    'department': emp.department_id.name,
                    'work_email': emp.work_email,
                    'work_phone': emp.work_phone,
                    'mobile_phone': emp.mobile_phone,
                    'gender': emp.gender,
                    'birthdate': str(emp.birthdate) if emp.birthdate else None,
                    'is_sales': emp.is_sales,
                    'address_home_id': emp.address_home_id.id if emp.address_home_id else None,
                })

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data, total_records, total_pages)

        except Exception as e:
            return serialize_error_response(str(e))


class PaymentAPI(http.Controller):
    @http.route(['/api/payment_invoice/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_payment_invoices(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None, **params):
        try:
            check_authorization()

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', '=', 'paid'),
            ]

            if q:
                domain += [('name', '=', str(q))]

            pageSize = int(pageSize) if pageSize else 200
            page = int(page)

            # Handle date filtering
            if createdDateFrom or createdDateTo:
                created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()
                domain += [
                    ('create_date', '>=', created_date_from.strftime(date_format)),
                    ('create_date', '<=', created_date_to.strftime(date_format)),
                ]

            # Ambil data invoice (account.move)
            payment_invoices = request.env['account.move'].sudo().search(domain, limit=pageSize, offset=(page - 1) * pageSize)

            jakarta_tz = pytz.timezone('Asia/Jakarta')
            data_payment_invoice = []

            for payment in payment_invoices:
                reference = payment.ref
                if not reference:
                    continue

                # Get POS order details
                order_pos = request.env['pos.order'].sudo().search([
                    ('vit_trxid', '=', reference),
                    ('state', '=', 'invoiced')
                ], limit=1)

                if not order_pos:
                    continue

                # Get location details from picking
                picking = request.env['stock.picking'].sudo().search([
                    ('origin', '=', order_pos.name)
                ], limit=1)

                location_id = picking.location_id.id if picking else False
                location = picking.location_id.complete_name if picking else ''

                # Filter pos.payment sesuai is_integrated parameter
                payment_domain = [('pos_order_id', '=', order_pos.id)]
                if is_integrated is not None:
                    is_integrated_bool = str(is_integrated).lower() == 'true'
                    payment_domain += [('is_integrated', '=', is_integrated_bool)]

                pos_payments = request.env['pos.payment'].sudo().search(payment_domain)

                for payment_line in pos_payments:
                    payment_date_utc = payment_line.payment_date
                    if not payment_date_utc:
                        continue

                    payment_date_jakarta = pytz.utc.localize(payment_date_utc).astimezone(jakarta_tz)

                    payments_data = {
                        'id': payment_line.id,  # ambil dari pos.payment
                        'doc_num': order_pos.name,
                        'is_integrated': payment_line.is_integrated,
                        'invoice': payment.name,
                        'invoice_id': payment.id,
                        'location_id': location_id,
                        'location': location,
                        'customer_id': payment.partner_id.id,
                        'customer_name': payment.partner_id.name,
                        'customer_code': payment.partner_id.customer_code,
                        'payment_date': str(payment_date_jakarta),
                        'amount': payment_line.amount,
                        'create_date': str(payment_date_jakarta),
                        'payment_method_pos_id': payment_line.payment_method_id.id,
                        'payment_method_pos': payment_line.payment_method_id.name,
                        'payment_method_journal_id': payment_line.payment_method_id.journal_id.inbound_payment_method_line_ids.payment_method_id.id,
                        'payment_method_journal_name': payment_line.payment_method_id.journal_id.inbound_payment_method_line_ids.payment_method_id.name,
                    }
                    data_payment_invoice.append(payments_data)

            # Update total_records
            total_records = len(data_payment_invoice)
            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_payment_invoice, total_records, total_pages)

        except ValidationError:
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))

        
class PaymentReturnCreditMemoAPI(http.Controller):
    @http.route(['/api/payment_creditmemo/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_payment_credit_memo(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None, **params):
        try:
            check_authorization()

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [
                ('move_type', '=', 'out_refund'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ['paid', 'in_payment', 'reversed', 'partial'])
            ]

            if q:
                domain += [('name', '=', str(q))]

            pageSize = int(pageSize) if pageSize else 200
            page = int(page)

            # Handle date filtering
            if createdDateFrom or createdDateTo:
                created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()
                domain += [
                    ('create_date', '>=', created_date_from.strftime(date_format)),
                    ('create_date', '<=', created_date_to.strftime(date_format))
                ]

            # Ambil data credit memo (account.move)
            credit_memos = request.env['account.move'].sudo().search(domain, limit=pageSize, offset=(page - 1) * pageSize)

            jakarta_tz = pytz.timezone('Asia/Jakarta')
            data_credit_memo = []

            for credit in credit_memos:
                reference = credit.ref
                if not reference:
                    continue

                # Get POS order details
                order_pos = request.env['pos.order'].sudo().search([
                    ('vit_trxid', '=', reference),
                    ('state', '=', 'invoiced')
                ], limit=1)

                if not order_pos:
                    continue

                # Get location details from picking
                picking = request.env['stock.picking'].sudo().search([
                    ('origin', '=', order_pos.name)
                ], limit=1)

                location_id = picking.location_dest_id.id if picking else False
                location = picking.location_dest_id.complete_name if picking else ''

                # Filter pos.payment sesuai parameter is_integrated
                payment_domain = [('pos_order_id', '=', order_pos.id)]
                if is_integrated is not None:
                    is_integrated_bool = str(is_integrated).lower() == 'true'
                    payment_domain += [('is_integrated', '=', is_integrated_bool)]

                pos_payments = request.env['pos.payment'].sudo().search(payment_domain)

                for payment_line in pos_payments:
                    payment_date_utc = payment_line.payment_date
                    if not payment_date_utc:
                        continue

                    payment_date_jakarta = pytz.utc.localize(payment_date_utc).astimezone(jakarta_tz)

                    payments_data = {
                        'id': payment_line.id,  # ambil dari pos.payment
                        'doc_num': order_pos.name,
                        'is_integrated': payment_line.is_integrated,
                        'invoice': credit.name,
                        'invoice_id': credit.id,
                        'location_id': location_id,
                        'location': location,
                        'customer_id': credit.partner_id.id,
                        'customer_name': credit.partner_id.name,
                        'customer_code': credit.partner_id.customer_code,
                        'payment_date': str(payment_date_jakarta),
                        'amount': payment_line.amount,
                        'create_date': str(payment_date_jakarta),
                        'payment_method_pos_id': payment_line.payment_method_id.id,
                        'payment_method_pos': payment_line.payment_method_id.name,
                        'payment_method_journal_id': payment_line.payment_method_id.journal_id.inbound_payment_method_line_ids.payment_method_id.id,
                        'payment_method_journal_name': payment_line.payment_method_id.journal_id.inbound_payment_method_line_ids.payment_method_id.name
                    }
                    data_credit_memo.append(payments_data)

            # Update total_records
            total_records = len(data_credit_memo)
            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_credit_memo, total_records, total_pages)

        except ValidationError:
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))


      
class MasterUoMAPI(http.Controller):
    @http.route(['/api/master_uom/'], type='http', auth='public', methods=['GET'], csrf=False)
    def master_UoM_get(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, **params):
        try:
            check_authorization()

            # if not q and (not createdDateFrom or not createdDateTo or not pageSize or not page):
            #     raise ValidationError("One or more required parameters are missing.")

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = []  # Initialize domain here

            if q:
                domain += [('name', 'ilike', str(q))]

            if not createdDateFrom and not createdDateTo and not q:
                # Handle the case when no specific filters are provided
                uom_data = request.env['uom.uom'].sudo().search([])
                total_records = len(uom_data)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                          ('create_date', '<=', created_date_to.strftime(date_format))]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                uom_data, total_records = paginate_records('uom.uom', domain, pageSize, page)
            else:
                uom_data = request.env['uom.uom'].sudo().search(domain)
                total_records = len(uom_data)

            data_uom_data = []
            for uom in uom_data:
                uoms_data = {
                    'id': uom.id,
                    'name': uom.name,
                    'category_id': uom.category_id.id,
                    'category': uom.category_id.name,
                    'uom_type': uom.uom_type,
                    'active': uom.active,
                    'create_date': str(uom.create_date),
                    'rounding': uom.rounding,    
                }
                data_uom_data.append(uoms_data)

            if not createdDateFrom and not createdDateTo and not q:
                total_records = len(data_uom_data)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_uom_data, total_records, total_pages)
        
        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))

class MasterMappingGRGIType(http.Controller):
    @http.route(['/api/master_stock_type/'], type='http', auth='public', methods=['GET'], csrf=False)
    def master_stock_type_get(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, **params):
        try:
            check_authorization()

            # if not q and (not createdDateFrom or not createdDateTo or not pageSize or not page):
            #     raise ValidationError("One or more required parameters are missing.")

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = []  # Initialize domain here

            if q:
                domain += [('type_name', 'ilike', str(q))]

            if not createdDateFrom and not createdDateTo and not q:
                # Handle the case when no specific filters are provided
                type_data = request.env['master.type'].sudo().search([])
                total_records = len(type_data)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                          ('create_date', '<=', created_date_to.strftime(date_format))]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                type_data, total_records = paginate_records('master.type', domain, pageSize, page)
            else:
                type_data = request.env['master.type'].sudo().search(domain)
                total_records = len(type_data)

            data_type_data = []
            for rec in type_data:
                jakarta_tz = pytz.timezone('Asia/Jakarta')
                create_date_utc = rec.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)

                uoms_data = {
                    'id': rec.id,
                    'type_name': rec.type_name,
                    'type_code': rec.type_code,
                    'created_date': create_date_jakarta
                }
                data_type_data.append(uoms_data)

            if not createdDateFrom and not createdDateTo and not q:
                total_records = len(data_type_data)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_type_data, total_records, total_pages)
        
        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))

class MasterCurrencyAPI(http.Controller):
    @http.route(['/api/master_currency/'], type='http', auth='public', methods=['GET'], csrf=False)
    def master_currency_get(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, **params):
        try:
            check_authorization()

            # if not q and (not createdDateFrom or not createdDateTo or not pageSize or not page):
            #     raise ValidationError("One or more required parameters are missing.")

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = []  # Initialize domain here

            if q:
                domain += [('name', 'ilike', str(q))]

            if not createdDateFrom and not createdDateTo and not q:
                currency_data = request.env['res.currency'].sudo().search([])
                total_records = len(currency_data)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                          ('create_date', '<=', created_date_to.strftime(date_format))]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                currency_data, total_records = paginate_records('res.currency', domain, pageSize, page)
            else:
                currency_data = request.env['res.currency'].sudo().search(domain)
                total_records = len(currency_data)

            jakarta_tz = pytz.timezone('Asia/Jakarta')
            data_currency_data = []
            for currency in currency_data:
                create_date_utc = currency.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                currencys_data = {
                    'id': currency.id,
                    'name': currency.name,
                    'full_name': currency.full_name,
                    'active': currency.active,
                    'symbol': currency.symbol,
                    'create_date': str(create_date_jakarta),
                    'currency_unit_label': currency.currency_unit_label,
                    'currency_subunit_label': currency.currency_subunit_label,
                    'rounding': currency.rounding,
                    'decimal_places': currency.decimal_places,
                    'posisition': currency.position,
                }
                data_currency_data.append(currencys_data)

            if not createdDateFrom and not createdDateTo and not q:
                total_records = len(data_currency_data)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_currency_data, total_records, total_pages)
        
        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))
              
class MasterCategoryItem(http.Controller):
    @http.route(['/api/item_category/'], type='http', auth='public', methods=['GET'], csrf=False)
    def master_category_item_get(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, **params):
        try:
            check_authorization()

            # if not q and (not createdDateFrom or not createdDateTo or not pageSize or not page):
            #     raise ValidationError("One or more required parameters are missing.")

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = []  # Initialize domain here

            if q:
                domain += [('display_name', 'ilike', str(q))]

            if not createdDateFrom and not createdDateTo and not q:
                # Handle the case when no specific filters are provided
                category_data = request.env['product.category'].sudo().search([])
                total_records = len(category_data)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                          ('create_date', '<=', created_date_to.strftime(date_format))]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                category_data, total_records = paginate_records('product.category', domain, pageSize, page)
            else:
                category_data = request.env['product.category'].sudo().search(domain)
                total_records = len(category_data)

            data_category_data = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for category in category_data:
                create_date_utc = category.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                categorys_data = {
                    'id': category.id,
                    'category_name': category.display_name,
                    'parent_category_id': category.parent_id.id if category.parent_id else None,
                    'parent_category': category.parent_id.name if category.parent_id else None,
                    # 'property_account_income_categ_id': category.property_account_income_categ_id.id,
                    # 'property_account_income_categ': category.property_account_income_categ_id.name,
                    # 'property_account_expense_categ_id': category.property_account_expense_categ_id.id,
                    # 'property_account_expense_categ': category.property_account_expense_categ_id.name,
                    'create_date': str(create_date_jakarta),
                    'costing_method': category.property_cost_method,
                    # 'property_valuation': category.property_valuation,
                    # 'property_stock_valuation_account_id': category.property_stock_valuation_account_id.id,
                    # 'property_stock_valuation_account': category.property_stock_valuation_account_id.name,
                    # 'property_stock_journal_id': category.property_stock_journal.id,
                    # 'property_stock_journal': category.property_stock_journal.name,
                    # 'property_stock_account_input_categ_id': category.property_stock_account_input_categ_id.id,
                    # 'property_stock_account_input_categ': category.property_stock_account_input_categ_id.name,
                    # 'property_stock_account_output_categ_id': category.property_stock_account_output_categ_id.id,
                    # 'property_stock_account_output_categ': category.property_stock_account_output_categ_id.name,
                    # 'property_stock_account_production_cost_id': category.property_stock_account_production_cost_id.id,
                    # 'property_stock_account_production_cost': category.property_stock_account_production_cost_id.name,
                }
                data_category_data.append(categorys_data)

            if not createdDateFrom and not createdDateTo and not q:
                total_records = len(data_category_data)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_category_data, total_records, total_pages)
        
        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))
        
class MasterPoSCategoryItem(http.Controller):
    @http.route(['/api/pos_category/'], type='http', auth='public', methods=['GET'], csrf=False)
    def master_pos_category_item_get(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, **params):
        try:
            check_authorization()

            # if not q and (not createdDateFrom or not createdDateTo or not pageSize or not page):
            #     raise ValidationError("One or more required parameters are missing.")

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = []  # Initialize domain here

            if q:
                domain += [('name', 'ilike', str(q))]

            if not createdDateFrom and not createdDateTo and not q:
                # Handle the case when no specific filters are provided
                category_data = request.env['pos.category'].sudo().search([])
                total_records = len(category_data)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                          ('create_date', '<=', created_date_to.strftime(date_format))]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                category_data, total_records = paginate_records('pos.category', domain, pageSize, page)
            else:
                category_data = request.env['pos.category'].sudo().search(domain)
                total_records = len(category_data)

            data_category_data = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for category in category_data:
                create_date_utc = category.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                categorys_data = {
                    'id': category.id,
                    'category_name': category.name,
                    'create_date': str(create_date_jakarta),
                }
                data_category_data.append(categorys_data)

            if not createdDateFrom and not createdDateTo and not q:
                total_records = len(data_category_data)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_category_data, total_records, total_pages)
        
        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))
        
class MasterCustomerAPI(http.Controller):
    @http.route(['/api/master_customer/'], type='http', auth='public', methods=['GET'], csrf=False)
    def master_customer_get(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None, **params):
        try:
            check_authorization()

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = []
            pageSize = int(pageSize) if pageSize else 200

            # Build domain filters
            if q:
                domain += [('customer_code', '=', str(q))]

            if createdDateFrom or createdDateTo:
                created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                        ('create_date', '<=', created_date_to.strftime(date_format))]
            
            # Fix: Properly handle is_integrated filter
            if is_integrated is not None:
                is_integrated_bool = str(is_integrated).lower() == 'true'
                domain += [('is_integrated', '=', is_integrated_bool)]

            # Fetch data with pagination
            if domain or (q is not None):
                customers_data, total_records = paginate_records('res.partner', domain, pageSize, page)
            else:
                customers_data = request.env['res.partner'].sudo().search([])
                total_records = len(customers_data)

            data_master_customer = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            
            for customer in customers_data:
                create_date_utc = customer.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                
                # Fix: Ensure customer_code is always a string or proper value
                customer_code = customer.customer_code if customer.customer_code else ""
                
                customer_data = {
                    'id': customer.id,
                    'create_date': str(create_date_jakarta),
                    'name': customer.name,
                    'street': customer.street,
                    'phone': customer.phone,
                    'mobile': customer.mobile,
                    'email': customer.email,
                    'website': customer.website,
                    'title': customer.title.name if customer.title else "",
                    'is_integrated': customer.is_integrated,
                    'customer_rank': customer.customer_rank,
                    'supplier_rank': customer.supplier_rank,
                    'customer_code': customer_code,
                    'property_product_pricelist_id': customer.property_product_pricelist.id if customer.property_product_pricelist else None,
                    'property_product_pricelist': customer.property_product_pricelist.name if customer.property_product_pricelist else "",
                    'property_account_receivable_id': customer.property_account_receivable_id.id if customer.property_account_receivable_id else None,
                    'property_account_receivable': customer.property_account_receivable_id.name if customer.property_account_receivable_id else "",
                    'property_account_payable_id': customer.property_account_payable_id.id if customer.property_account_payable_id else None,
                    'property_account_payable': customer.property_account_payable_id.name if customer.property_account_payable_id else "",
                    'property_stock_customer_id': customer.property_stock_customer.id if customer.property_stock_customer else None,
                    'property_stock_customer': customer.property_stock_customer.name if customer.property_stock_customer else "",
                    'property_stock_supplier_id': customer.property_stock_supplier.id if customer.property_stock_supplier else None,
                    'property_stock_supplier': customer.property_stock_supplier.name if customer.property_stock_supplier else ""
                }
                data_master_customer.append(customer_data)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_master_customer, total_records, total_pages)
        
        except ValidationError as ve:
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))
        
class MasterLocationAPI(http.Controller):
    @http.route(['/api/master_location/'], type='http', auth='public', methods=['GET'], csrf=False)
    def master_location_get(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, **params):
        try:
            check_authorization()

            # if not q and (not createdDateFrom or not createdDateTo or not pageSize or not page):
            #     raise ValidationError("One or more required parameters are missing.")

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = []  # Initialize domain here

            if q:
                domain += [('complete_name', 'ilike', str(q))]

            if not createdDateFrom and not createdDateTo and not q:
                # Handle the case when no specific filters are provided
                location_data = request.env['stock.location'].sudo().search([])
                total_records = len(location_data)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                          ('create_date', '<=', created_date_to.strftime(date_format))]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                location_data, total_records = paginate_records('stock.location', domain, pageSize, page)
            else:
                location_data = request.env['stock.location'].sudo().search(domain)
                total_records = len(location_data)

            data_master_location = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for location in location_data:
                create_date_utc = location.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                locations_data = {
                    'id': location.id,
                    'name': location.complete_name,
                    'create_date': str(create_date_jakarta),
                    'location_id': location.location_id.id,
                    'location': location.location_id.name,
                    'usage': location.usage,
                    'scrap_location': location.scrap_location,
                    'return_location': location.return_location,
                    'replenish_location': location.replenish_location,
                    'last_inventory_date': str(location.last_inventory_date),
                    'next_inventory_date': str(location.next_inventory_date),
                    
                }
                data_master_location.append(locations_data)

            if not createdDateFrom and not createdDateTo and not q:
                total_records = len(data_master_location)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_master_location, total_records, total_pages)
        
        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))
        
class MasterOperationType(http.Controller):
    @http.route(['/api/master_operation_type/'], type='http', auth='public', methods=['GET'], csrf=False)
    def master_operation_type_get(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, **params):
        try:
            check_authorization()

            # if not q and (not createdDateFrom or not createdDateTo or not pageSize or not page):
            #     raise ValidationError("One or more required parameters are missing.")

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = []  # Initialize domain here

            if q:
                domain += [('name', 'ilike', str(q))]

            if not createdDateFrom and not createdDateTo and not q:
                operation_type_data = request.env['stock.picking.type'].sudo().search(domain)
                total_records = len(operation_type_data)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                          ('create_date', '<=', created_date_to.strftime(date_format))]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                operation_type_data, total_records = paginate_records('stock.picking.type', domain, pageSize, page)
            else:
                operation_type_data = request.env['stock.picking.type'].sudo().search(domain)
                total_records = len(operation_type_data)

            data_master_operation_type = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for op in operation_type_data:
                create_date_utc =op.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                operations_data = {
                    'id': op.id,
                    'name': op.name,
                    'code': op.code,
                    'create_date': str(create_date_jakarta),
                    'sequence_id': op.sequence_id.id,
                    'sequence': op.sequence_id.name,
                    'sequence_code': op.sequence_code,
                    'warehouse_id': op.warehouse_id.id,
                    'warehouse': op.warehouse_id.name,
                    'warehouse_code': op.code,
                    'return_picking_type_id': op.return_picking_type_id.id,
                    'return_picking_type': op.return_picking_type_id.name,
                    'default_location_return_id': op.default_location_return_id.id,
                    'default_location_return': op.default_location_return_id.complete_name,
                    'create_backorder': op.create_backorder,
                    'default_location_src_id': op.default_location_src_id.id,
                    'default_location_src': op.default_location_src_id.complete_name,
                    'default_location_dest_id': op.default_location_dest_id.id,
                    'default_location_dest': op.default_location_dest_id.complete_name,       
                }
                data_master_operation_type.append(operations_data)

            if not createdDateFrom and not createdDateTo and not q:
                total_records = len(data_master_operation_type)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_master_operation_type, total_records, total_pages)
        
        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))
        
class MasterProductItemAPI(http.Controller):
    @http.route(['/api/master_item/'], type='http', auth='public', methods=['GET'], csrf=False)
    def master_product_get(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None, **params):
        try:
            # check_authorization()

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = []  # Initialize domain here

            if q:
                domain += [('default_code', '=', str(q))]

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                product_data = request.env['product.template'].sudo().search([])
                total_records = len(product_data)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                            ('create_date', '<=', created_date_to.strftime(date_format))]
                    
                if is_integrated is not None:
                    is_integrated_bool = str(is_integrated).lower() == 'true'
                    domain += [('is_integrated', '=', is_integrated_bool)]

                pageSize = int(pageSize) if pageSize else 200

                if not q:
                    product_data, total_records = paginate_records('product.template', domain, pageSize, page)
                else:
                    product_data = request.env['product.template'].sudo().search(domain)
                    total_records = len(product_data)

            data_master_product = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for product in product_data:
                create_date_utc = product.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                pos_categ_ids = [{'id': pos_categ.id, 'name': pos_categ.name} for pos_categ in product.pos_categ_ids]
                vendor_taxes_ids = [{'id': vendor_taxes.id, 'name': vendor_taxes.name} for vendor_taxes in product.supplier_taxes_id]
                taxes_ids = [{'id': taxes.id, 'name': taxes.name} for taxes in product.taxes_id]
                categ_id = [{'id': product.categ_id.id, 'name': product.categ_id.complete_name}]

                product_data = {
                    'id': product.id,
                    'product_name': product.name,
                    'product_code': product.default_code,
                    'detailed_type': product.detailed_type,
                    'invoice_policy': product.invoice_policy,
                    'uom_id': product.uom_id.id,
                    'uom': product.uom_id.name,
                    'uom_po_id': product.uom_po_id.id,
                    'uom_po': product.uom_po_id.name,
                    'list_price': product.list_price,
                    'standard_price': product.standard_price,
                    'categ_id': product.categ_id.id,
                    'categ': product.categ_id.complete_name,
                    'pos_categ_ids': pos_categ_ids,
                    'taxes_id': taxes_ids,
                    'supplier_taxes_id': vendor_taxes_ids,
                    # 'pos_categ_name': product.pos_categ_ids.name,
                    'create_date': str(create_date_jakarta),
                    'is_integrated': product.is_integrated,
                    # 'image_1920': base64.b64encode(product.image_1920).decode('utf-8') if product.image_1920 else None
                    'vit_sub_div': product.vit_sub_div,
                    'vit_item_kel': product.vit_item_kel,
                    'vit_item_type': product.vit_item_type,
                    'vit_item_brand': product.vit_item_brand,
                    'brand': product.brand
                }
                data_master_product.append(product_data)

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                total_records = len(data_master_product)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_master_product, total_records, total_pages)
        
        except ValidationError as ve:
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))
        
class MasterStockTypeAPI(http.Controller):
    @http.route(['/api/master_type/'], type='http', auth='public', methods=['GET'], csrf=False)
    def master_type_get(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, **params):
        try:
            check_authorization()

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = []  # Initialize domain here

            if q:
                domain += [('type_code', '=', str(q))]

            if not createdDateFrom and not createdDateTo and not q:
                type_data = request.env['master.type'].sudo().search([])
                total_records = len(type_data)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                            ('create_date', '<=', created_date_to.strftime(date_format))]

                pageSize = int(pageSize) if pageSize else 200

                if not q:
                    type_data, total_records = paginate_records('master.type', domain, pageSize, page)
                else:
                    type_data = request.env['master.type'].sudo().search(domain)
                    total_records = len(type_data)

            data_master_type = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for types in type_data:
                create_date_utc = types.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)

                product_data = {
                    'id': types.id,
                    'type_name': types.type_name,
                    'type_code': types.type_code,
                    'create_date': str(create_date_jakarta),
                }
                data_master_type.append(product_data)

            if not createdDateFrom and not createdDateTo and not q:
                total_records = len(data_master_type)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_master_type, total_records, total_pages)
        
        except ValidationError as ve:
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))
       
class MasterPricelistAPI(http.Controller):
    @http.route(['/api/master_pricelist/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_pricelists(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None, **params):
        try:
            check_authorization()
            
            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = []  # Initialize domain here

            if q:
                domain += [('name', 'ilike', str(q))]

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                pricelist = request.env['product.pricelist'].sudo().search([])
                total_records = len(pricelist)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                          ('create_date', '<=', created_date_to.strftime(date_format))]
                    
                if is_integrated is not None:
                    is_integrated_bool = str(is_integrated).lower() == 'true'
                    domain += [('is_integrated', '=', is_integrated_bool)]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                pricelist, total_records = paginate_records('product.pricelist', domain, pageSize, page)
            else:
                pricelist = request.env['product.pricelist'].sudo().search(domain)
                total_records = len(pricelist)

            data_pricelists = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for order in pricelist:
                create_date_utc = order.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                order_data = {
                    'id': order.id,
                    'name': order.name,
                    'currency_id': order.currency_id.id,
                    'create_date': str(order.create_date),
                    'is_integrated': order.is_integrated
                }
                data_pricelists.append(order_data)

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                total_records = len(data_pricelists)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_pricelists, total_records, total_pages)

        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))

    @http.route(['/api/pricelist_line/<int:order_id>'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_pricelist_lines(self, order_id, **params):
        try:
            check_authorization()

            pricelists = request.env['product.pricelist'].sudo().browse(order_id)
            if not pricelists:
                raise werkzeug.exceptions.NotFound(_("Pricelist not found"))

            pricelist_lines = pricelists.item_ids
            pricelist_name = pricelists.name
            currency_id = pricelists.currency_id.id
            currency = pricelists.currency_id.name
            
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            create_date_utc = pricelists.create_date
            create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
            created_date = str(create_date_jakarta)

            data_currency_lines = []
            for line_number, line in enumerate(pricelist_lines, start=1):
                date_start_utc = line.date_start
                date_start_jakarta = pytz.utc.localize(date_start_utc).astimezone(jakarta_tz)
                date_start = str(date_start_jakarta)

                date_end_utc = line.date_end
                date_end_jakarta = pytz.utc.localize(date_end_utc).astimezone(jakarta_tz)
                date_end = str(date_end_jakarta)

                def remove_currency_symbol(price):
                    # Menggunakan regular expression untuk menghapus karakter non-digit
                    return re.sub(r'[^\d.]', '', str(price))
      
                line_data = {
                    'line_number': line_number,
                    'id': line.id,
                    'product_id': line.product_tmpl_id.id,
                    'product_name': line.product_tmpl_id.name,
                    'product_code': line.product_tmpl_id.default_code,
                    'applicable_on': line.name,
                    'min_quantity': line.min_quantity,
                    'price': remove_currency_symbol(line.price),
                    'date_start': date_start,
                    'date_end': date_end
                }
                data_currency_lines.append(line_data)


            response_data = {
                'status': 200,
                'message': 'success',
                'price_list_name': pricelist_name,
                'currency_id': currency_id,
                'currency_name': currency,
                'create_date': created_date,
                'items': data_currency_lines
            }
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            return serialize_error_response(str(e))

class SaleOrderAPI(http.Controller):
    @http.route(['/api/sale_order/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_sale_orders(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None, **params):
        try:
            check_authorization()

            # if not q and (not createdDateFrom or not createdDateTo or not pageSize or not page):
            #     raise ValidationError("One or more required parameters are missing.")
            
            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [('state', '=', 'sale')]  # Initialize domain here

            if q:
                domain += [('name', 'ilike', str(q))]

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                # Handle the case when no specific filters are provided
                domain = [('name', 'ilike', str(q))] if q else [('state', '=', 'sale')]
                sale_orders = request.env['sale.order'].sudo().search(domain)
                total_records = len(sale_orders)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                          ('create_date', '<=', created_date_to.strftime(date_format)),
                          ('state', '=', 'sale')]
                    
                if is_integrated is not None:
                    is_integrated_bool = str(is_integrated).lower() == 'true'
                    domain += [('is_integrated', '=', is_integrated_bool)]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                sale_orders, total_records = paginate_records('sale.order', domain, pageSize, page)
            else:
                sale_orders = request.env['sale.order'].sudo().search(domain)
                total_records = len(sale_orders)

            data_sale_orders = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for order in sale_orders:
                create_date_utc = order.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                order_data = {
                    'id': order.id,
                    'doc_num': order.name,
                    'customer_id': order.partner_id.id,
                    'customer_name': order.partner_id.name,
                    'pricelist_id': order.pricelist_id.id,
                    'create_date': str(create_date_jakarta),
                    'validity_date': str(order.validity_date),
                    'date_order': str(order.date_order),
                    'state': order.state,
                    'is_integrated': order.is_integrated
                }
                data_sale_orders.append(order_data)

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                total_records = len(data_sale_orders)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_sale_orders, total_records, total_pages)

        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))

    @http.route(['/api/sale_order_line/<int:order_id>'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_sale_order_lines(self, order_id, **params):
        try:
            check_authorization()

            sale_order = request.env['sale.order'].sudo().browse(order_id)
            if not sale_order:
                raise werkzeug.exceptions.NotFound(_("Sale Order not found"))

            sale_order_lines = sale_order.order_line
            customer_name = sale_order.partner_id.name
            customer_id = sale_order.partner_id.id
            
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            create_date_utc = sale_order.create_date
            create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
            created_date = str(create_date_jakarta)
            
            date_order = str(sale_order.date_order)
            validity_date = str(sale_order.validity_date)
            amount_total = sale_order.amount_total
            doc_num = sale_order.name

            data_sale_order_lines = []
            for line_number, line in enumerate(sale_order_lines, start=1):
                line_data = {
                    'line_number': line_number,
                    'id': line.id,
                    'doc_no': doc_num,
                    'order_id': line.order_id.id,
                    'product_id': line.product_id.id,
                    'product_code': line.product_id.default_code,
                    'product_name': line.product_id.name,
                    'quantity': line.product_uom_qty,
                    'price_unit': line.price_unit,
                }
                data_sale_order_lines.append(line_data)


            response_data = {
                'status': 200,
                'message': 'success',
                'doc_num': doc_num,
                'customer_id': customer_id,
                'customer_name': customer_name,
                'created_date': str(created_date),
                'date_order': date_order,
                'validity_date': validity_date,
                'items': data_sale_order_lines,
                'amount_total': amount_total
            }
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            return serialize_error_response(str(e))
        
class POSOrder(http.Controller):
    @http.route(['/api/pos_order/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_pos_order(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None, **params):
        try:
            check_authorization()

            # if not q and (not createdDateFrom or not createdDateTo or not pageSize or not page):
            #     raise ValidationError("One or more required parameters are missing.")

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [('state', '=', 'done')]  # Initialize domain here

            if q:
                domain += [('name', 'ilike', str(q))]

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                # Handle the case when no specific filters are provided
                domain = [('name', 'ilike', str(q))] if q else [('state', '=', 'done')]
                invoice_orders = request.env['pos.order'].sudo().search(domain)
                total_records = len(invoice_orders)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                          ('create_date', '<=', created_date_to.strftime(date_format)),
                          ('state', '=', 'done')]
                    
                if is_integrated is not None:
                    is_integrated_bool = str(is_integrated).lower() == 'true'
                    domain += [('is_integrated', '=', is_integrated_bool)]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                invoice_orders, total_records = paginate_records('pos.order', domain, pageSize, page)
            else:
                invoice_orders = request.env['pos.order'].sudo().search(domain)
                total_records = len(invoice_orders)

            data_invoice_orders = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for order in invoice_orders:
                create_date_utc = order.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                order_data = {
                    'id': order.id,
                    'doc_num': order.name,
                    'customer_id': order.partner_id.id,
                    'customer_name': order.partner_id.name,
                    'create_date': str(create_date_jakarta),
                    'date_order': str(order.date_order),
                    'session_id': order.session_id.id,
                    'session': order.session_id.name,
                    'user_id': order.user_id.id,
                    'user': order.user_id.name,
                    'is_integrated': order.is_integrated
                }
                data_invoice_orders.append(order_data)

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                total_records = len(data_invoice_orders)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_invoice_orders, total_records, total_pages)

        except Exception as e:
            return serialize_error_response(str(e))
        
    @http.route(['/api/pos_order_line/<int:order_id>'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_pos_order_lines(self, order_id, **params):
        try:
            check_authorization()

            pos_order = request.env['pos.order'].sudo().browse(order_id)
            if not pos_order:
                raise werkzeug.exceptions.NotFound(_("Invoice Order not found"))

            pos_order_lines = pos_order.lines
            customer_name = pos_order.partner_id.name
            customer_id = pos_order.partner_id.id
            doc_num = pos_order.name
            date = str(pos_order.date_order)
            session_id = pos_order.session_id.id
            session = pos_order.session_id.name
            user_id = pos_order.user_id.id
            user = pos_order.user_id.name

            data_pos_order_lines = []
            for line_number, line in enumerate(pos_order_lines, start=1):
                line_data = {
                    'line_number': line_number,
                    'id': line.id,
                    'doc_no': doc_num,
                    'product_id': line.product_id.id,
                    'product_name': line.full_product_name,
                    'product_code': line.product_id.default_code,
                    'location_id': line.product_id.property_stock_inventory.id,
                    'location': line.product_id.property_stock_inventory.name,
                    'qty': line.qty,
                    'uom_id': line.product_uom_id.id,
                    'uom': line.product_uom_id.name,
                    'discount': line.discount,
                    'price_subtotal': line.price_subtotal,
                    'price_subtotal_incl': line.price_subtotal_incl,
                }
                data_pos_order_lines.append(line_data)

            response_data = {
                'status': 200,
                'message': 'success',
                'doc_num': doc_num,
                'customer_id': customer_id,
                'customer_name': customer_name,
                'date' : date,
                'session_id' : session_id,
                'session' : session,
                'user_id' : user_id,
                'user' : user,
                'order_line': data_pos_order_lines
            }
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            return serialize_error_response(str(e))

class UnbuildOrder(http.Controller):
    @http.route(['/api/unbuild_order/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_unbuild_order(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None,**params):
        try:
            check_authorization()

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [('state', '=', 'done')]

            if q:
                domain += [('name', 'ilike', str(q)), ('state', '=', 'done')]


            if createdDateFrom or createdDateTo:
                created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                           ('create_date', '<=', created_date_to.strftime(date_format)),
                           ('state', '=', 'done')]
                
            if is_integrated is not None:
                is_integrated_bool = str(is_integrated).lower() == 'true'
                domain += [('is_integrated', '=', is_integrated_bool)]

            pageSize = int(pageSize) if pageSize else 200

            unbuild_order, total_records = paginate_records('mrp.unbuild', domain, pageSize, page)

            data_unbuild_order = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for order in unbuild_order:
                create_date_utc = order.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                order_data = {
                    'id': order.id,
                    'doc_num': order.name,
                    'source_document': order.vit_trxid,
                    'product_id': order.product_id.id,
                    'product_code': order.product_id.default_code,
                    'product_qty': order.product_qty,
                    'bom_id': order.bom_id.id,
                    'location_id': order.location_id.id,
                    'location_name': order.location_id.complete_name,
                    'location_dest_id': order.location_dest_id.id,
                    'location_dest': order.location_dest_id.complete_name,
                    'create_date': str(create_date_jakarta),
                    'state': order.state,
                    'is_integrated': order.is_integrated
                }
                data_unbuild_order.append(order_data)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_unbuild_order, total_records, total_pages)

        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))

    @http.route(['/api/unbuild_order_line/<int:order_id>'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_unbuild_order_lines(self, order_id, **params):
        try:
            check_authorization()

            unbuild_order = request.env['mrp.unbuild'].sudo().browse(order_id)
            if not unbuild_order:
                raise werkzeug.exceptions.NotFound(_("Unbuild Order not found"))

            unbuild_order_lines = unbuild_order.unbuild_line_ids
            doc_num = unbuild_order.name

            jakarta_tz = pytz.timezone('Asia/Jakarta')
            create_date_utc = unbuild_order.create_date
            create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
            created_date = str(create_date_jakarta)

            data_unbuild_order_lines = []
            for line_number, line in enumerate(unbuild_order_lines, start=1):
                line_data = {
                    'line_number': line_number,
                    'id': line.id,
                    'doc_no': doc_num,
                    'product_id': line.product_id.id,
                    'product_code': line.product_id.default_code,
                    'location_id': line.location_id.id,
                    'location': line.location_id.complete_name,
                    'product_uom_qty': line.product_uom_qty,
                }
                data_unbuild_order_lines.append(line_data)

            response_data = {
                'status': 200,
                'message': 'success',
                'doc_num':  unbuild_order.name,
                'source_document': unbuild_order.vit_trxid,
                'product_id': unbuild_order.product_id.id,
                'product_code': unbuild_order.product_id.default_code,
                'product_qty': unbuild_order.product_qty,
                'bom_id': unbuild_order.bom_id.id,
                'location_id': unbuild_order.location_id.id,
                'location_name': unbuild_order.location_id.complete_name,
                'location_dest_id': unbuild_order.location_dest_id.id,
                'location_dest': unbuild_order.location_dest_id.complete_name,
                'create_date': str(create_date_jakarta),
                'unbuild_lines': data_unbuild_order_lines
            }
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            return serialize_error_response(str(e))
        
class ManufacturingOrderAPI(http.Controller):
    @http.route(['/api/manufacture_order/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_manufacturing_order(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None,**params):
        try:
            check_authorization()

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [('picking_type_id.name', '=', 'Manufacturing'), ('state', '=', 'done')]

            if q:
                domain += [('name', 'ilike', str(q))]

            if createdDateFrom or createdDateTo:
                created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                           ('create_date', '<=', created_date_to.strftime(date_format)),
                           ('picking_type_id.name', '=', 'Manufacturing'), ('state', '=', 'done')]
                
            if is_integrated is not None:
                is_integrated_bool = str(is_integrated).lower() == 'true'
                domain += [('is_integrated', '=', is_integrated_bool)]

            pageSize = int(pageSize) if pageSize else 200

            manufacture_order, total_records = paginate_records('mrp.production', domain, pageSize, page)

            data_manufacture_order = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for order in manufacture_order:
                create_date_utc = order.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                order_data = {
                    'id': order.id,
                    'doc_num': order.name,
                    'product_id': order.product_id.id,
                    'product': order.product_id.name,
                    'quantity': order.product_qty,
                    'bom_id': order.bom_id.id,
                    'bom': order.bom_id.product_tmpl_id.name,
                    # 'location_id': order.location_id.id,
                    # 'location': order.location_id.name,
                    'location_id': order.location_src_id.id,
                    'location_name': order.location_src_id.complete_name,
                    'location_dest_id': order.location_dest_id.id,
                    'location_dest': order.location_dest_id.complete_name,
                    'picking_type_id': order.picking_type_id.id,
                    'picking_type': order.picking_type_id.name,
                    'start_date': str(order.date_start),
                    'end_date': str(order.date_finished),
                    'create_date': str(create_date_jakarta),
                    'is_integrated': order.is_integrated
                }
                data_manufacture_order.append(order_data)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_manufacture_order, total_records, total_pages)

        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))

    @http.route(['/api/manufacture_order_line/<int:order_id>'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_manufacture_order_lines(self, order_id, **params):
        try:
            check_authorization()

            manufacture_order = request.env['mrp.production'].sudo().browse(order_id)
            if not manufacture_order:
                raise werkzeug.exceptions.NotFound(_("Manufacturing order not found"))
            
            # Ensure the order is a 'Return' type
            if manufacture_order.picking_type_id.name != 'Manufacturing':
                raise werkzeug.exceptions.NotFound(_("Manufacturing is not a Manufacturing"))

            manufacture_order_lines = manufacture_order.move_raw_ids
            doc_num = manufacture_order.name
            product_id = manufacture_order.product_id.id,
            product = manufacture_order.product_id.name,
            quantity = manufacture_order.product_qty,
            bom_id = manufacture_order.bom_id.id,
            bom =  manufacture_order.bom_id.product_tmpl_id.name,
            location_id = manufacture_order.location_src_id.id
            location = manufacture_order.location_src_id.complete_name
            location_dest_id = manufacture_order.location_dest_id.id
            location_dest = manufacture_order.location_dest_id.complete_name
            picking_type_id = manufacture_order.picking_type_id.id
            picking_type = manufacture_order.picking_type_id.name
            start_date = str(manufacture_order.date_start),
            end_date = str(manufacture_order.date_finished),

            jakarta_tz = pytz.timezone('Asia/Jakarta')
            create_date_utc = manufacture_order.create_date
            create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
            created_date = str(create_date_jakarta)

            data_manufacture_order_lines = []
            for line_number, line in enumerate(manufacture_order_lines, start=1):
                line_data = {
                    'line_number': line_number,
                    'id': line.id,
                    'doc_no': doc_num,
                    'location_id': line.location_id.id,
                    'location': line.location_id.complete_name,
                    'location_dest_id': line.location_dest_id.id,
                    'location_dest': line.location_dest_id.complete_name,
                    'product_id': line.product_id.id,
                    'product_code': line.product_id.default_code or "",
                    'product_name': line.product_id.name,
                    'to_consume_qty': line.product_uom_qty,
                    'quantity': line.quantity,
                    'product_uom': line.product_uom.name,
                    'picked': line.picked
                }
                data_manufacture_order_lines.append(line_data)

            response_data = {
                'status': 200,
                'message': 'success',
                'doc_num': doc_num,
                'product_id': product_id,
                'product': product,
                'quantity': quantity,
                'bom_id': bom_id,
                'bom': bom,
                'location_id': location_dest_id,
                'location': location_dest,
                'location_dest_id': location_id,
                'location_dest': location,
                'picking_type_id': picking_type_id,
                'picking_type': picking_type,
                'created_date': created_date,
                'start_date': start_date,
                'end_date': end_date,
                'items': data_manufacture_order_lines
            }
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            return serialize_error_response(str(e))
        
class InvoiceOrder(http.Controller):
    @http.route(['/api/invoice_order/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_invoices_order(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None, **params):
        try:
            check_authorization()

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [('state', '=', 'posted'), ('payment_state', '=', 'paid'), ('move_type', '=', 'out_invoice'), ('partner_id.customer_code', '!=', False)]
            pageSize = int(pageSize) if pageSize else 200

            if q:
                domain += [('name', 'ilike', str(q))]

            if createdDateFrom or createdDateTo:
                created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                            ('create_date', '<=', created_date_to.strftime(date_format))]

            if is_integrated is not None:
                is_integrated_bool = str(is_integrated).lower() == 'true'
                domain += [('is_integrated', '=', is_integrated_bool)]

            # Fetch data
            if domain or q:
                invoice_accounting, total_records = paginate_records('account.move', domain, pageSize, page)
            else:
                invoice_accounting = request.env['account.move'].sudo().search(domain)
                total_records = len(invoice_accounting)

            data_invoice_accounting = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')

            for order in invoice_accounting:
                try:
                    order_pos = request.env['pos.order'].sudo().search([('vit_trxid', '=', order.ref), ('state', '=', 'invoiced')], limit=1)
                    location_id = location = location_dest_id = location_dest = None

                    if order_pos:
                        pickings = request.env['stock.picking'].sudo().search([('origin', '=', order_pos.name)], limit=1)
                        if pickings:
                            location_id = pickings.location_id.id
                            location = pickings.location_id.complete_name
                            location_dest_id = pickings.location_dest_id.id
                            location_dest = pickings.location_dest_id.complete_name

                    create_date_utc = order.create_date
                    create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)

                    order_data = {
                        'id': order.id,
                        'pos_order_id': order.pos_order_ids[0].id if order.pos_order_ids else None,
                        'doc_num': order.name,
                        'ref_num': order.ref or "",
                        'customer_id': order.partner_id.id,
                        'customer_name': order.partner_id.name,
                        'customer_code': order.partner_id.customer_code or "",
                        'location_id': location_id or -1,
                        'location': location or "",
                        'location_dest_id': location_dest_id or -1,
                        'location_dest': location_dest or "",
                        'is_integrated': order.is_integrated,
                        'create_date': str(create_date_jakarta),
                        'invoice_date': str(order.invoice_date),
                        'invoice_date_due': str(order.invoice_date_due),
                        'payment_reference': order.payment_reference or "",
                        'journal_id': order.journal_id.id,
                        'journal': order.journal_id.name,
                        'company_id': order.company_id.id,
                        'company': order.company_id.name,
                    }
                    data_invoice_accounting.append(order_data)
                except Exception as line_error:
                    _logger.warning(f"Error processing invoice {order.id}: {str(line_error)}")
                    continue

            total_records = int(total_records)
            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_invoice_accounting, total_records, total_pages)

        except Exception as e:
            _logger.error(f"Error in get_invoices_order: {str(e)}")
            return serialize_error_response(str(e))

    @http.route(['/api/invoice_order_line/<int:order_id>'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_invoice_order_lines(self, order_id, **params):
        try:
            check_authorization()

            invoicing = request.env['account.move'].sudo().search([
                ('id', '=', order_id),
                ('state', '=', 'posted'),
                ('payment_state', '=', 'paid'),
                ('move_type', '=', 'out_invoice'),
                ('partner_id.customer_code', '!=', False)
            ], limit=1)

            if not invoicing:
                return werkzeug.wrappers.Response(
                    status=404,
                    content_type='application/json; charset=utf-8',
                    response=json.dumps({'status': 404, 'message': 'Invoice Order not found'})
                )

            invoice_lines = invoicing.invoice_line_ids
            partner = invoicing.partner_id
            company = invoicing.company_id

            jakarta_tz = pytz.timezone('Asia/Jakarta')
            create_date_utc = invoicing.create_date
            create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)

            # Cari tax PPNK sekali saja
            tax_ppnk = request.env['account.tax'].sudo().search([('name', 'ilike', 'PPNK')], limit=1)

            data_invoice_lines = []
            line_number = 0
            
            _logger.info(f"=== Starting to process {len(invoice_lines)} invoice lines for invoice {invoicing.name} ===")
            
            for line in invoice_lines:
                try:
                    _logger.info(f"Checking line {line.id}: product={line.product_id.default_code if line.product_id else 'NO_PRODUCT'}, qty={line.quantity}, price={line.price_unit}, display_type={line.display_type if hasattr(line, 'display_type') else 'N/A'}")
                    
                    # Skip line yang bukan produk (tidak ada product_id)
                    if not line.product_id:
                        _logger.info(f"Skipping line {line.id} - no product_id")
                        continue
                    
                    # Skip hanya jika quantity 0
                    if line.quantity == 0:
                        _logger.info(f"Skipping line {line.id} - quantity is 0")
                        continue
                    
                    line_number += 1

                    # Inisialisasi variabel location
                    location_id = location = location_dest_id = location_dest = None
                    
                    # Cek tipe produk - gunakan detailed_type atau type sebagai fallback
                    product_type = 'product'  # default
                    try:
                        if hasattr(line.product_id, 'detailed_type'):
                            product_type = line.product_id.detailed_type
                        elif hasattr(line.product_id, 'type'):
                            product_type = line.product_id.type
                    except Exception as type_error:
                        _logger.warning(f"Error getting product type for line {line.id}: {str(type_error)}")
                    
                    is_service = product_type in ['service', 'consu']  # consu juga tidak punya stock move
                    
                    _logger.info(f"Processing line {line.id}: product={line.product_id.default_code}, type={product_type}, is_service={is_service}, qty={line.quantity}")
                    
                    # Cari location - wrap dalam try-catch
                    try:
                        if not is_service:
                            # Untuk produk storable/consumable, cari picking seperti biasa
                            pickings = request.env['stock.picking'].sudo().search([
                                ('pos_order_id', '=', invoicing.pos_order_ids[0].id if invoicing.pos_order_ids else False),
                                ('origin', '=', invoicing.ref),
                                ('move_ids_without_package.product_id', '=', line.product_id.id)
                            ], limit=1)

                            if pickings:
                                location_id = pickings.location_id.id
                                location = pickings.location_id.complete_name
                                location_dest_id = pickings.location_dest_id.id
                                location_dest = pickings.location_dest_id.complete_name
                            elif invoicing.pos_order_ids:
                                pos_order = invoicing.pos_order_ids[0]
                                if hasattr(pos_order, 'vit_pos_store') and pos_order.vit_pos_store:
                                    location_id = pos_order.vit_pos_store.id
                                    location = pos_order.vit_pos_store.name
                                    location_dest_id = pos_order.vit_pos_store.id
                                    location_dest = pos_order.vit_pos_store.name
                        else:
                            # Untuk produk service:
                            # 1. Tetap cari di stock.picking untuk location_id dan location_dest_id
                            # 2. Gunakan vit_pos_store untuk location dan location_dest (string)
                            _logger.info(f"Line {line.id} is SERVICE type, processing location")
                            
                            # Cari picking dulu untuk dapat location_id
                            pickings = request.env['stock.picking'].sudo().search([
                                ('pos_order_id', '=', invoicing.pos_order_ids[0].id if invoicing.pos_order_ids else False),
                                ('origin', '=', invoicing.ref)
                            ], limit=1)
                            
                            if pickings:
                                location_id = pickings.location_id.id
                                location_dest_id = pickings.location_dest_id.id
                                _logger.info(f"Service line {line.id}: Found picking with location_id {location_id}")
                            
                            # Gunakan vit_pos_store untuk location name
                            if invoicing.pos_order_ids:
                                pos_order = invoicing.pos_order_ids[0]
                                if hasattr(pos_order, 'vit_pos_store') and pos_order.vit_pos_store:
                                    # vit_pos_store adalah char field, bukan many2one
                                    location = pos_order.vit_pos_store
                                    location_dest = pos_order.vit_pos_store
                                    _logger.info(f"Service line {line.id}: Using vit_pos_store '{location}'")
                                    
                                    # Jika belum ada location_id dari picking, set None
                                    if not location_id:
                                        location_id = None
                                        location_dest_id = None
                            
                            # Jika tidak ada vit_pos_store dan tidak ada picking
                            if not location and not location_id:
                                _logger.info(f"Service line {line.id}: No location found, setting to None")
                    except Exception as location_error:
                        _logger.warning(f"Error finding location for line {line.id}: {str(location_error)}")
                        # Set default None values - sudah di-initialize di atas

                    # Cek tax, jika kosong isi dengan PPNK
                    tax_data = []
                    try:
                        taxes = line.tax_ids if line.tax_ids else (tax_ppnk if tax_ppnk else [])
                        tax_data = [{'id': tax.id, 'tax_name': tax.name, 'amount': tax.amount} for tax in taxes]
                    except Exception as tax_error:
                        _logger.warning(f"Error processing taxes for line {line.id}: {str(tax_error)}")

                    # Get user info safely
                    user_id = None
                    user_name = ""
                    user_code = ""
                    try:
                        if hasattr(line, 'user_id') and line.user_id:
                            user_id = line.user_id.id
                            user_name = line.user_id.name
                            if hasattr(line.user_id, 'vit_employee_code'):
                                user_code = line.user_id.vit_employee_code or ""
                    except Exception as user_error:
                        _logger.warning(f"Error processing user for line {line.id}: {str(user_error)}")

                    line_data = {
                        'line_number': line_number,
                        'id': line.id,
                        'doc_no': invoicing.name,
                        'sales_id': user_id,
                        'sales': user_name,
                        'sales_code': user_code,
                        'product_id': line.product_id.id,
                        'product_name': line.name,
                        'product_code': line.product_id.default_code or "",
                        'product_type': product_type,
                        'location_id': location_id,
                        'location': location or "",
                        'location_dest_id': location_dest_id,
                        'location_dest': location_dest or "",
                        'quantity': line.quantity,
                        'uom_id': line.product_uom_id.id,
                        'uom': line.product_uom_id.name,
                        'tax_ids': tax_data,
                        'price_unit': line.price_unit,
                    }
                    data_invoice_lines.append(line_data)
                    _logger.info(f"Successfully added line {line.id} to response")
                    
                except Exception as line_error:
                    _logger.error(f"Error processing invoice line {line.id}: {str(line_error)}", exc_info=True)
                    continue

            _logger.info(f"Total lines processed: {len(data_invoice_lines)} from {len(invoice_lines)} invoice lines")

            response_data = {
                'status': 200,
                'message': 'success',
                'doc_num': invoicing.name,
                'customer_id': partner.id,
                'customer_name': partner.name,
                'create_date': str(create_date_jakarta),
                'invoice_date': str(invoicing.invoice_date),
                'invoice_date_due': str(invoicing.invoice_date_due),
                'is_integrated': invoicing.is_integrated,
                'payment_reference': invoicing.payment_reference or "",
                'journal_id': invoicing.journal_id.id,
                'journal': invoicing.journal_id.name,
                'company_id': company.id,
                'company': company.name,
                'order_line': data_invoice_lines,
                'amount': invoicing.amount_total,
            }
            
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            _logger.error(f"Error in get_invoice_order_lines for order_id {order_id}: {str(e)}", exc_info=True)
            return werkzeug.wrappers.Response(
                status=500,
                content_type='application/json; charset=utf-8',
                response=json.dumps({'status': 500, 'message': f'Internal Server Error: {str(e)}'})
            )

class ReturOrderAPI(http.Controller):
    @http.route(['/api/return_order/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_return_orders(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None, **params):
        try:
            check_authorization()

            # if not q and (not createdDateFrom or not createdDateTo or not pageSize or not page):
            #     raise ValidationError("One or more required parameters are missing.")
            
            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [('picking_type_id.name', '=', 'Return'), ('state', '=', 'done')]  # Initialize domain here

            if q:
                domain += [('name', 'ilike', str(q))]

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                # Handle the case when no specific filters are provided
                domain = [('name', 'ilike', str(q))] if q else [('state', '=', 'done'), ('picking_type_id.name', '=', 'Return')]
                return_orders = request.env['stock.picking'].sudo().search(domain)
                total_records = len(return_orders)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                          ('create_date', '<=', created_date_to.strftime(date_format)),
                          ('picking_type_id.name', '=', 'Return'),
                          ('state', '=', 'done')]
                    
                if is_integrated is not None:
                    is_integrated_bool = str(is_integrated).lower() == 'true'
                    domain += [('is_integrated', '=', is_integrated_bool)]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                return_orders, total_records = paginate_records('stock.picking', domain, pageSize, page)
            else:
                return_orders = request.env['stock.picking'].sudo().search(domain)
                total_records = len(return_orders)

            data_return_orders = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for order in return_orders:
                create_date_utc = order.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                order_data = {
                    'id': order.id,
                    'doc_num': order.name,
                    'source_document': order.origin,
                    'customer_id': order.partner_id.id,
                    'location_id': order.location_id.id,
                    'location': order.location_id.name,
                    'location_destination_id': order.location_dest_id.id,
                    'location_destination': order.location_dest_id.name,
                    'picking_type_id': order.picking_type_id.id,
                    'picking_type': order.picking_type_id.name,
                    'create_date': str(create_date_jakarta),
                    'scheduled_date': str(order.scheduled_date),
                    'date_done': str(order.date_done),
                    'state': order.state,
                    'is_integrated': order.is_integrated
                }
                data_return_orders.append(order_data)

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                total_records = len(data_return_orders)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_return_orders, total_records, total_pages)

        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))

    @http.route(['/api/return_order_line/<int:order_id>'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_return_order_lines(self, order_id, **params):
        try:
            check_authorization()

            return_order = request.env['stock.picking'].sudo().browse(order_id)
            if not return_order:
                raise werkzeug.exceptions.NotFound(_("Sale Order not found"))
            
            # Ensure the order is a 'Return' type
            if return_order.picking_type_id.name != 'Return':
                raise werkzeug.exceptions.NotFound(_("Order is not a Return Order"))

            return_order_lines = return_order.move_ids_without_package
            doc_num = return_order.name
            customer_name = return_order.partner_id.name
            customer_id = return_order.partner_id.id
            location_id = return_order.location_id.id
            location = return_order.location_id.name
            location_dest_id = return_order.location_dest_id.id
            location_dest = return_order.location_dest_id.name
            picking_type_id = return_order.picking_type_id.id
            picking_type = return_order.picking_type_id.name
            scheduled_date = str(return_order.scheduled_date)

            jakarta_tz = pytz.timezone('Asia/Jakarta')
            create_date_utc = return_order.create_date
            create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
            created_date = str(create_date_jakarta)
            date_done = str(return_order.date_done)

            data_return_order_lines = []
            for line_number, line in enumerate(return_order_lines, start=1):
                line_data = {
                    'line_number': line_number,
                    'id': line.id,
                    'doc_no': doc_num,
                    'location_id': line.location_id.id,
                    'location': line.location_id.name,
                    'location_dest_id': line.location_dest_id.id,
                    'location_dest': line.location_dest_id.name,
                    'product_id': line.product_id.id,
                    'product_code': line.product_id.default_code or "",
                    'product_name': line.product_id.name,
                    'demand_qty': line.product_uom_qty,
                    'quantity': line.quantity,
                    'product_uom': line.product_uom.name,
                }
                data_return_order_lines.append(line_data)


            response_data = {
                'status': 200,
                'message': 'success',
                'doc_num': doc_num,
                'customer_id': customer_id,
                'customer_name': customer_name,
                'location_id': location_id,
                'location': location,
                'location_destination_id': location_dest_id,
                'location_destination': location_dest,
                'picking_type_id': picking_type_id,
                'picking_type': picking_type,
                'created_date': created_date,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'items': data_return_order_lines,
            }
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            return serialize_error_response(str(e))
        
class CrediNoteAPI(http.Controller):
    @http.route(['/api/credit_memo/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_credit_memo(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None, **params):
        try:
            check_authorization()

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [('state', '=', 'posted'), ('payment_state', 'in', ['paid', 'in_payment', 'reversed', 'partial']), ('move_type', '=', 'out_refund'), ('partner_id.customer_code', '!=', False)]  # Initialize domain here

            if q:
                domain += [('name', 'ilike', str(q)), ('state', '=', 'posted'), ('payment_state', 'in', ['paid', 'in_payment', 'reversed', 'partial']), ('move_type', '=', 'out_refund'), ('partner_id.customer_code', '!=', False)]

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                # If no parameters are provided, fetch all records
                invoice_accounting = request.env['account.move'].sudo().search([('state', '=', 'posted'), ('payment_state', 'in', ['paid', 'in_payment', 'reversed', 'partial']), ('move_type', '=', 'out_refund'), ('partner_id.customer_code', '!=', False)])
                total_records = len(invoice_accounting)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                                ('create_date', '<=', created_date_to.strftime(date_format)),
                                ('state', '=', 'posted'), ('payment_state', 'in', ['paid', 'in_payment', 'reversed', 'partial']), ('move_type', '=', 'out_refund'), ('partner_id.customer_code', '!=', False)]

                if is_integrated is not None:
                    is_integrated_bool = str(is_integrated).lower() == 'true'
                    domain += [('state', '=', 'posted'), ('payment_state', 'in', ['paid', 'in_payment', 'reversed', 'partial']), ('move_type', '=', 'out_refund'), ('partner_id.customer_code', '!=', False), ('is_integrated', '=', is_integrated_bool)]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                invoice_accounting, total_records = paginate_records('account.move', domain, pageSize, page)
            else:
                invoice_accounting = request.env['account.move'].sudo().search(domain)
                total_records = len(invoice_accounting)

            data_invoice_accounting = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            location_id = None
            location = None

            for order in invoice_accounting:
                order_pos = request.env['pos.order'].sudo().search([('vit_trxid', '=', order.ref), ('state', '=', 'invoiced')], limit=1)
                
                if not order_pos:  # Skip if no related pos.order is found
                    continue

                for record in order_pos:
                    pickings = request.env['stock.picking'].sudo().search([('origin', '=', record.name)], limit=1)
                    if pickings:
                        location_id = pickings.location_dest_id.id
                        location = pickings.location_dest_id.complete_name
                    else:
                        location_id = None
                        location = None

                create_date_utc = order.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)

                order_data = {
                    'id': order.id,
                    'doc_num': order.name,
                    'ref_num': order.ref.split(": ")[-1] if order.ref else None,
                    'customer_id': order.partner_id.id,
                    'customer_name': order.partner_id.name,
                    'customer_code': order.partner_id.customer_code,
                    'location_id': location_id or int(-1),
                    'location': location,
                    'is_integrated': order.is_integrated,
                    'create_date': str(create_date_jakarta),
                    'invoice_date': str(order.invoice_date),
                    'invoice_date_due': str(order.invoice_date_due),
                    'payment_reference': order.payment_reference,
                    'journal_id': order.journal_id.id,
                    'journal': order.journal_id.name,
                    'company_id': order.company_id.id,
                    'company': order.company_id.name,
                }
                data_invoice_accounting.append(order_data)


            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                total_records = len(data_invoice_accounting)

            total_records = int(total_records)
            pageSize = int(pageSize)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_invoice_accounting, total_records, total_pages)

        except Exception as e:
            return serialize_error_response(str(e))

        
    @http.route(['/api/credit_memo_line/<int:order_id>'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_credit_memo_lines(self, order_id, **params):
        try:
            check_authorization()

            invoicing = request.env['account.move'].sudo().search([
                ('id', '=', order_id),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ['paid', 'in_payment', 'reversed', 'partial']),
                ('move_type', '=', 'out_refund'),
                ('partner_id.customer_code', '!=', False)
            ], limit=1)

            if not invoicing:
                raise werkzeug.exceptions.NotFound(_("Credit Note is not found"))

            invoice_lines = invoicing.invoice_line_ids
            partner = invoicing.partner_id
            company = invoicing.company_id

            jakarta_tz = pytz.timezone('Asia/Jakarta')
            create_date_utc = invoicing.create_date
            create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)

            # Cari tax PPNK sekali saja
            tax_ppnk = request.env['account.tax'].sudo().search([('name', 'ilike', 'PPNK')], limit=1)

            data_invoice_lines = []
            line_number = 0
            
            _logger.info(f"=== Starting to process {len(invoice_lines)} credit memo lines for {invoicing.name} ===")
            
            for line in invoice_lines:
                try:
                    _logger.info(f"Checking line {line.id}: product={line.product_id.default_code if line.product_id else 'NO_PRODUCT'}, qty={line.quantity}, price={line.price_unit}, display_type={line.display_type if hasattr(line, 'display_type') else 'N/A'}")
                    
                    # Skip line yang bukan produk (tidak ada product_id)
                    if not line.product_id:
                        _logger.info(f"Skipping line {line.id} - no product_id")
                        continue
                    
                    # Skip hanya jika quantity 0
                    if line.quantity == 0:
                        _logger.info(f"Skipping line {line.id} - quantity is 0")
                        continue
                    
                    line_number += 1

                    # Inisialisasi variabel location
                    location_id = location = location_dest_id = location_dest = None
                    
                    # Cek tipe produk - gunakan detailed_type atau type sebagai fallback
                    product_type = 'product'  # default
                    try:
                        if hasattr(line.product_id, 'detailed_type'):
                            product_type = line.product_id.detailed_type
                        elif hasattr(line.product_id, 'type'):
                            product_type = line.product_id.type
                    except Exception as type_error:
                        _logger.warning(f"Error getting product type for line {line.id}: {str(type_error)}")
                    
                    is_service = product_type in ['service', 'consu']  # consu juga tidak punya stock move
                    
                    _logger.info(f"Processing line {line.id}: product={line.product_id.default_code}, type={product_type}, is_service={is_service}, qty={line.quantity}")
                    
                    # Cari location - wrap dalam try-catch
                    try:
                        if not is_service:
                            # Untuk produk storable/consumable, cari picking seperti biasa
                            pickings = request.env['stock.picking'].sudo().search([
                                ('pos_order_id', '=', invoicing.pos_order_ids[0].id if invoicing.pos_order_ids else False),
                                ('origin', '=', invoicing.ref),
                                ('move_ids_without_package.product_id', '=', line.product_id.id)
                            ], limit=1)

                            if pickings:
                                location_id = pickings.location_id.id
                                location = pickings.location_id.complete_name
                                location_dest_id = pickings.location_dest_id.id
                                location_dest = pickings.location_dest_id.complete_name
                            elif invoicing.pos_order_ids:
                                pos_order = invoicing.pos_order_ids[0]
                                if hasattr(pos_order, 'vit_pos_store') and pos_order.vit_pos_store:
                                    location_id = pos_order.vit_pos_store.id
                                    location = pos_order.vit_pos_store.name
                                    location_dest_id = pos_order.vit_pos_store.id
                                    location_dest = pos_order.vit_pos_store.name
                        else:
                            # Untuk produk service:
                            # 1. Tetap cari di stock.picking untuk location_id dan location_dest_id
                            # 2. Gunakan vit_pos_store untuk location dan location_dest (string)
                            _logger.info(f"Line {line.id} is SERVICE type, processing location")
                            
                            # Cari picking dulu untuk dapat location_id
                            pickings = request.env['stock.picking'].sudo().search([
                                ('pos_order_id', '=', invoicing.pos_order_ids[0].id if invoicing.pos_order_ids else False),
                                ('origin', '=', invoicing.ref)
                            ], limit=1)
                            
                            if pickings:
                                location_id = pickings.location_id.id
                                location_dest_id = pickings.location_dest_id.id
                                _logger.info(f"Service line {line.id}: Found picking with location_id {location_id}")
                            
                            # Gunakan vit_pos_store untuk location name
                            if invoicing.pos_order_ids:
                                pos_order = invoicing.pos_order_ids[0]
                                if hasattr(pos_order, 'vit_pos_store') and pos_order.vit_pos_store:
                                    # vit_pos_store adalah char field, bukan many2one
                                    location = pos_order.vit_pos_store
                                    location_dest = pos_order.vit_pos_store
                                    _logger.info(f"Service line {line.id}: Using vit_pos_store '{location}'")
                                    
                                    # Jika belum ada location_id dari picking, set None
                                    if not location_id:
                                        location_id = None
                                        location_dest_id = None
                            
                            # Jika tidak ada vit_pos_store dan tidak ada picking
                            if not location and not location_id:
                                _logger.info(f"Service line {line.id}: No location found, setting to None")
                    except Exception as location_error:
                        _logger.warning(f"Error finding location for line {line.id}: {str(location_error)}")
                        # Set default None values - sudah di-initialize di atas

                    # Cek tax, jika kosong isi dengan PPNK
                    tax_data = []
                    try:
                        taxes = line.tax_ids if line.tax_ids else (tax_ppnk if tax_ppnk else [])
                        tax_data = [{'id': tax.id, 'tax_name': tax.name, 'amount': tax.amount} for tax in taxes]
                    except Exception as tax_error:
                        _logger.warning(f"Error processing taxes for line {line.id}: {str(tax_error)}")

                    line_data = {
                        'line_number': line_number,
                        'id': line.id,
                        'doc_no': invoicing.name,
                        'product_id': line.product_id.id,
                        'product_name': line.name,
                        'product_code': line.product_id.default_code or "",
                        'product_type': product_type,
                        'location_id': location_id,
                        'location': location or "",
                        'location_dest_id': location_dest_id,
                        'location_dest': location_dest or "",
                        'quantity': line.quantity,
                        'uom_id': line.product_uom_id.id,
                        'uom': line.product_uom_id.name,
                        'tax_ids': tax_data,
                        'price_unit': line.price_unit,
                    }
                    data_invoice_lines.append(line_data)
                    _logger.info(f"Successfully added line {line.id} to response")
                    
                except Exception as line_error:
                    _logger.error(f"Error processing credit memo line {line.id}: {str(line_error)}", exc_info=True)
                    continue

            _logger.info(f"Total lines processed: {len(data_invoice_lines)} from {len(invoice_lines)} credit memo lines")

            response_data = {
                'status': 200,
                'message': 'success',
                'doc_num': invoicing.name,
                'customer_id': partner.id,
                'customer_name': partner.name,
                'create_date': str(create_date_jakarta),
                'invoice_date': str(invoicing.invoice_date),
                'invoice_date_due': str(invoicing.invoice_date_due),
                'is_integrated': invoicing.is_integrated,
                'payment_reference': invoicing.payment_reference or "",
                'journal_id': invoicing.journal_id.id,
                'journal': invoicing.journal_id.name,
                'company_id': company.id,
                'company': company.name,
                'order_line': data_invoice_lines,
                'amount': invoicing.amount_total,
            }
            
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            _logger.error(f"Error in get_credit_memo_lines for order_id {order_id}: {str(e)}", exc_info=True)
            return werkzeug.wrappers.Response(
                status=500,
                content_type='application/json; charset=utf-8',
                response=json.dumps({'status': 500, 'message': f'Internal Server Error: {str(e)}'})
            )

class PurchaseOrder(http.Controller):
    @http.route(['/api/purchase_order/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_purchase_order(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated = None, **params):
        try:
            check_authorization()

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [('state', '=', 'purchase'), ('partner_id.customer_code', '!=', False)]  # Initialize domain here

            if q:
                domain += [('vit_trxid', 'ilike', str(q)), ('state', '=', 'purchase'), ('partner_id.customer_code', '!=', False)]

            # if is_integrated:
            #     domain += [('is_integrated', '=', is_integrated)]

            if not createdDateFrom and not createdDateTo and not q and not is_integrated:
                # If no parameters are provided, fetch all records
                purchase_order = request.env['purchase.order'].sudo().search([('state', '=', 'purchase'), ('partner_id.customer_code', '!=', False)])
                total_records = len(purchase_order)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                              ('create_date', '<=', created_date_to.strftime(date_format)), 
                              ('state', '=', 'purchase'), ('partner_id.customer_code', '!=', False)]

                if is_integrated is not None:
                    is_integrated_bool = str(is_integrated).lower() == 'true'
                    domain += [('is_integrated', '=', is_integrated_bool)]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                purchase_order, total_records = paginate_records('purchase.order', domain, pageSize, page)
            else:
                purchase_order = request.env['purchase.order'].sudo().search(domain)
                total_records = len(purchase_order)

            data_purchase_order = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            location_id = None
            location = None
            location_dest_id = None
            location_dest = None
            for order in purchase_order:
                pickings = request.env['stock.picking'].sudo().search([('origin', '=', order.name)], limit=1)
                location_id = pickings.location_id.id
                location = pickings.location_id.complete_name
                location_dest_id = pickings.location_dest_id.id
                location_dest = pickings.location_dest_id.complete_name

                create_date_utc = order.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                    
                order_data = {
                    'id': order.id,
                    'doc_num': order.name,
                    'transaction_id': order.vit_trxid,
                    'vendor_id': order.partner_id.id,
                    'vendor_name': order.partner_id.name,
                    'vendor_code': order.partner_id.customer_code,
                    'vendor_ref': order.partner_ref,
                    'location_id': location_id,
                    'location': location,
                    'location_dest_id': location_dest_id,
                    'location_dest': location_dest,
                    'created_date': str(create_date_jakarta),
                    'date_approve': str(order.date_approve),
                    'date_planned': str(order.date_planned),
                    'effective_date': str(order.effective_date),
                    'is_integrated': order.is_integrated,
                    'deliver_to_id': order.picking_type_id.id,
                    'deliver_to': order.picking_type_id.id,
                    'company_id': order.company_id.id,
                    'company': order.company_id.name,
                }
                data_purchase_order.append(order_data)

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                total_records = len(data_purchase_order)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_purchase_order, total_records, total_pages)

        except Exception as e:
            return serialize_error_response(str(e))

        
    @http.route(['/api/purchase_order_line/<int:order_id>'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_purchase_order_lines(self, order_id, **params):
        try:
            check_authorization()  # Uncomment and implement this if necessary

            purchase_order = request.env['purchase.order'].sudo().search([('id', '=', order_id), ('state', '=', 'purchase'), ('partner_id.customer_code', '!=', False)], limit=1)
            if not purchase_order:
                raise werkzeug.exceptions.NotFound(_("Purchase Order not found"))

            # Get the first picking related to the invoice
            purchase_lines = purchase_order.order_line
            doc_num = purchase_order.name
            
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            create_date_utc = purchase_order.create_date
            create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
            create_date = str(create_date_jakarta)

            data_po_lines = []
            for line_number, line in enumerate(purchase_lines, start=1):
                pickings = request.env['stock.picking'].sudo().search([('origin', '=', purchase_order.name), ('move_ids_without_package.product_id', '=', line.product_id.id)], limit=1)
                location_id = pickings.location_id.id if pickings else None
                location = pickings.location_id.complete_name if pickings else None
                location_dest_id = pickings.location_dest_id.id if pickings else None
                location_dest = pickings.location_dest_id.complete_name if pickings else None
                vit_line_number_sap = line.vit_line_number_sap

                tax_data = []
                for tax in line.taxes_id:
                    tax_data.append({
                        'id': tax.id,
                        'tax_code': tax.description
                    })
                
                line_data = {
                    'line_number': line_number,
                    'line_number_sap': vit_line_number_sap,
                    'id': line.id,
                    'doc_no': doc_num,
                    'product_id': line.product_id.id,
                    'product_name': line.name,
                    'product_code': line.product_id.default_code or "",
                    'location_id': location_id or int(-1),
                    'location': location or int(-1),
                    'location_dest_id': location_dest_id or int(-1),
                    'location_dest': location_dest or int(-1),
                    'quantity': line.product_qty,
                    'uom_id': line.product_uom.id,
                    'uom': line.product_uom.name,
                    'taxes_id': tax_data,
                    'price_unit': line.price_unit,
                }
                data_po_lines.append(line_data)

            response_data = {
                'status': 200,
                'message': 'success',
                'id': purchase_order.id,
                'doc_num': purchase_order.name,
                'transaction_id': purchase_order.vit_trxid,
                'vendor_id': purchase_order.partner_id.id,
                'vendor_name': purchase_order.partner_id.name,
                'vendor_code': purchase_order.partner_id.customer_code,
                'vendor_ref': purchase_order.partner_ref,
                'location_id': location_id,
                'location': location,
                'location_dest_id': location_dest_id,
                'location_dest': location_dest,
                'created_date': str(create_date),
                'date_approve': str(purchase_order.date_approve),
                'date_planned': str(purchase_order.date_planned),
                'effective_date': str(purchase_order.effective_date),
                'is_integrated': purchase_order.is_integrated,
                'deliver_to_id': purchase_order.picking_type_id.id,
                'deliver_to': purchase_order.picking_type_id.id,
                'company_id': purchase_order.company_id.id,
                'company': purchase_order.company_id.name,
                'order_line': data_po_lines,
                'amount_tax': purchase_order.amount_tax,
                'amount_total': purchase_order.amount_total,
                'amount_untaxed': purchase_order.amount_untaxed
            }
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            return self.serialize_error_response(str(e))
        
class GoodsReceiptAPI(http.Controller):
    @http.route(['/api/goods_receipt/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_goods_receipts(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None,**params):
        try:
            check_authorization()

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [('picking_type_id.name', '=', 'Goods Receipts'), ('state', '=', 'done')]

            if q:
                domain += [('name', 'ilike', str(q))]

            if createdDateFrom or createdDateTo:
                created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                           ('create_date', '<=', created_date_to.strftime(date_format)),
                           ('picking_type_id.name', '=', 'Goods Receipts'), ('state', '=', 'done')]
                
            if is_integrated is not None:
                is_integrated_bool = str(is_integrated).lower() == 'true'
                domain += [('is_integrated', '=', is_integrated_bool)]

            pageSize = int(pageSize) if pageSize else 200

            goods_receipt, total_records = paginate_records('stock.picking', domain, pageSize, page)

            data_goods_receipt = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for order in goods_receipt:
                create_date_utc = order.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                order_data = {
                    'id': order.id,
                    'doc_num': order.name,
                    'source_document': order.origin,
                    'customer_id': order.partner_id.id,
                    'stock_type_id': order.stock_type.type_code or int(-1),
                    'stock_type': order.stock_type.type_name or '',
                    # 'location_id': order.location_id.id,
                    # 'location': order.location_id.name,
                    'location_id': order.location_dest_id.id,
                    'location_name': order.location_dest_id.complete_name,
                    'location_dest_id': order.location_id.id,
                    'location_dest': order.location_id.complete_name,
                    'picking_type_id': order.picking_type_id.id,
                    'picking_type': order.picking_type_id.name,
                    'create_date': str(create_date_jakarta),
                    'scheduled_date': str(order.scheduled_date),
                    'date_done': str(order.date_done),
                    'state': order.state,
                    'is_integrated': order.is_integrated
                }
                data_goods_receipt.append(order_data)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_goods_receipt, total_records, total_pages)

        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))

    @http.route(['/api/goods_receipt_line/<int:order_id>'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_goods_receipt_lines(self, order_id, **params):
        try:
            check_authorization()

            goods_receipt = request.env['stock.picking'].sudo().browse(order_id)
            if not goods_receipt:
                raise werkzeug.exceptions.NotFound(_("Goods Receipt not found"))
            
            # Ensure the order is a 'Return' type
            if goods_receipt.picking_type_id.name != 'Goods Receipts':
                raise werkzeug.exceptions.NotFound(_("Goods Receipt is not a Goods Receipt"))

            goods_receipt_lines = goods_receipt.move_ids_without_package
            doc_num = goods_receipt.name
            customer_name = goods_receipt.partner_id.name
            customer_id = goods_receipt.partner_id.id
            stock_type_id = goods_receipt.stock_type.type_code
            stock_type = goods_receipt.stock_type.type_name
            location_id = goods_receipt.location_id.id
            location = goods_receipt.location_id.complete_name
            location_dest_id = goods_receipt.location_dest_id.id
            location_dest = goods_receipt.location_dest_id.complete_name
            picking_type_id = goods_receipt.picking_type_id.id
            picking_type = goods_receipt.picking_type_id.name
            scheduled_date = str(goods_receipt.scheduled_date)

            jakarta_tz = pytz.timezone('Asia/Jakarta')
            create_date_utc = goods_receipt.create_date
            create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
            created_date = str(create_date_jakarta)
            date_done = str(goods_receipt.date_done)

            data_goods_receipt_lines = []
            for line_number, line in enumerate(goods_receipt_lines, start=1):
                line_data = {
                    'line_number': line_number,
                    'id': line.id,
                    'doc_no': doc_num,
                    # 'location_id': line.location_id.id,
                    # 'location': line.location_id.name,
                    'location_id': line.location_dest_id.id,
                    'location': line.location_dest_id.complete_name,
                    'location_dest_id': line.location_id.id,
                    'location_dest': line.location_id.complete_name,
                    'product_id': line.product_id.id,
                    'product_code': line.product_id.default_code or "",
                    'product_name': line.product_id.name,
                    'demand_qty': line.product_uom_qty,
                    'quantity': line.quantity,
                    'product_uom': line.product_uom.name,
                }
                data_goods_receipt_lines.append(line_data)

            response_data = {
                'status': 200,
                'message': 'success',
                'doc_num': doc_num,
                'customer_id': customer_id or "",
                'customer_name': customer_name,
                'stock_type_id': stock_type_id,
                'stock_type': stock_type,
                # 'location_id': location_id,
                # 'location': location,
                'location_id': location_dest_id,
                'location': location_dest,
                'location_dest_id': location_id,
                'location_dest': location,
                'picking_type_id': picking_type_id,
                'picking_type': picking_type,
                'created_date': created_date,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'items': data_goods_receipt_lines,
            }
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            return serialize_error_response(str(e))
        
class GoodsIssueAPI(http.Controller):
    @http.route(['/api/goods_issue/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_goods_issue(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None, **params):
        try:
            check_authorization()

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [('picking_type_id.name', '=', 'Goods Issue'), ('state', '=', 'done')]

            if q:
                domain += [('name', 'ilike', str(q))]

            if createdDateFrom or createdDateTo:
                created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                           ('create_date', '<=', created_date_to.strftime(date_format)),
                           ('picking_type_id.name', '=', 'Goods Issue'), ('state', '=', 'done')]
                
            if is_integrated is not None:
                is_integrated_bool = str(is_integrated).lower() == 'true'
                domain += [('is_integrated', '=', is_integrated_bool)]

            pageSize = int(pageSize) if pageSize else 200

            goods_issue, total_records = paginate_records('stock.picking', domain, pageSize, page)

            data_goods_issue = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for order in goods_issue:
                create_date_utc = order.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                order_data = {
                    'id': order.id,
                    'doc_num': order.name,
                    'source_document': order.origin,
                    'customer_id': order.partner_id.id or "",
                    'stock_type_id': order.stock_type.type_code or int(-1),
                    'stock_type': order.stock_type.type_name or '',
                    'location_id': order.location_id.id,
                    'location_name': order.location_id.complete_name,
                    'location_dest_id': order.location_dest_id.id,
                    'location_dest': order.location_dest_id.complete_name,
                    'picking_type_id': order.picking_type_id.id,
                    'picking_type': order.picking_type_id.name,
                    'create_date': str(create_date_jakarta),
                    'scheduled_date': str(order.scheduled_date),
                    'date_done': str(order.date_done),
                    'state': order.state,
                    'is_integrated': order.is_integrated
                }
                data_goods_issue.append(order_data)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_goods_issue, total_records, total_pages)

        except ValidationError as ve:
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))


    @http.route(['/api/goods_issue_line/<int:order_id>'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_goods_issue_lines(self, order_id, **params):
        try:
            check_authorization()

            goods_issue = request.env['stock.picking'].sudo().browse(order_id)
            if not goods_issue:
                raise werkzeug.exceptions.NotFound(_("Goods Issue not found"))
            
            # Ensure the order is a 'Return' type
            if goods_issue.picking_type_id.name != 'Goods Issue':
                raise werkzeug.exceptions.NotFound(_("Goods Issue is not a Goods Receipt"))

            goods_issue_lines = goods_issue.move_ids_without_package
            doc_num = goods_issue.name
            customer_name = goods_issue.partner_id.name
            customer_id = goods_issue.partner_id.id
            stock_type_id = goods_issue.stock_type.type_code or int(-1)
            stock_type = goods_issue.stock_type.type_name or ''
            location_id = goods_issue.location_id.id
            location = goods_issue.location_id.complete_name
            location_dest_id = goods_issue.location_dest_id.id
            location_dest = goods_issue.location_dest_id.name
            picking_type_id = goods_issue.picking_type_id.id
            picking_type = goods_issue.picking_type_id.name
            scheduled_date = str(goods_issue.scheduled_date)
            
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            create_date_utc = goods_issue.create_date
            create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
            created_date = str(create_date_jakarta)
            date_done = str(goods_issue.date_done)

            data_goods_issue_lines = []
            for line_number, line in enumerate(goods_issue_lines, start=1):
                line_data = {
                    'line_number': line_number,
                    'id': line.id,
                    'doc_no': doc_num,
                    'location_id': line.location_id.id,
                    'location': line.location_id.complete_name,
                    'location_dest_id': line.location_dest_id.id,
                    'location_dest': line.location_dest_id.complete_name,
                    'product_id': line.product_id.id,
                    'product_code': line.product_id.default_code or "",
                    'product_name': line.product_id.name,
                    'demand_qty': line.product_uom_qty,
                    'quantity': line.quantity,
                    'product_uom': line.product_uom.name,
                }
                data_goods_issue_lines.append(line_data)

            response_data = {
                'status': 200,
                'message': 'success',
                'doc_num': doc_num,
                'customer_id': customer_id or "",
                'customer_name': customer_name,
                'stock_type_id': stock_type_id,
                'stock_type': stock_type,
                'location_id': location_id,
                'location': location,
                'location_dest_id': location_dest_id,
                'location_dest': location_dest,
                'picking_type_id': picking_type_id,
                'picking_type': picking_type,
                'created_date': created_date,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'items': data_goods_issue_lines,
            }
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            return serialize_error_response(str(e))
        
class GRPO(http.Controller):
    @http.route(['/api/grpo_transfer/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_goods_receipts_po(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None, is_closed=None,**params):
        try:
            check_authorization()

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [('picking_type_id.name', '=', 'GRPO'), ('state', '=', 'done')]

            if q:
                domain += [('vit_trxid', 'ilike', str(q))]

            if createdDateFrom or createdDateTo:
                created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                           ('create_date', '<=', created_date_to.strftime(date_format)),
                           ('picking_type_id.name', '=', 'GRPO'), ('state', '=', 'done')]
                
            if is_integrated is not None:
                is_integrated_bool = str(is_integrated).lower() == 'true'
                domain += [('is_integrated', '=', is_integrated_bool)]

            if is_closed is not None:
                is_closed_bool = str(is_closed).lower() == 'true'
                domain += [('is_closed', '=', is_closed_bool)]

            pageSize = int(pageSize) if pageSize else 200

            goods_receipt, total_records = paginate_records('stock.picking', domain, pageSize, page)

            data_goods_receipt = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for order in goods_receipt:
                create_date_utc = order.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                order_data = {
                    'id': order.id,
                    'doc_num': order.name,
                    'source_document': order.origin or '',
                    'vit_trxid': order.vit_trxid or '',
                    'customer_id': order.partner_id.id,
                    # 'stock_type_id': order.stock_type.code or int(-1),
                    # 'stock_type': order.stock_type.type_code or '',
                    'location_id': order.location_id.id or int(-1),
                    'location_name': order.location_id.complete_name or '',
                    'location_id': order.location_dest_id.id,
                    'location': order.location_dest_id.complete_name,
                    'picking_type_id': order.picking_type_id.id,
                    'picking_type': order.picking_type_id.name,
                    'create_date': str(create_date_jakarta),
                    'scheduled_date': str(order.scheduled_date),
                    'date_done': str(order.date_done),
                    'state': order.state,
                    'is_integrated': order.is_integrated,
                    'is_closed': order.is_closed
                }
                data_goods_receipt.append(order_data)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_goods_receipt, total_records, total_pages)

        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))

    @http.route(['/api/grpo_transfer_line/<int:order_id>'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_goods_receipt_grpo_lines(self, order_id, **params):
        try:
            check_authorization()

            goods_receipt = request.env['stock.picking'].sudo().browse(order_id)
            if not goods_receipt:
                raise werkzeug.exceptions.NotFound(_("GRPO not found"))
            
            # Ensure the order is a 'Return' type
            if goods_receipt.picking_type_id.name != 'GRPO':
                raise werkzeug.exceptions.NotFound(_("GRPO is not a GRPO"))

            goods_receipt_lines = goods_receipt.move_ids_without_package
            doc_num = goods_receipt.name
            source_document = goods_receipt.origin
            vit_trxid = goods_receipt.vit_trxid
            customer_name = goods_receipt.partner_id.name
            customer_id = goods_receipt.partner_id.id
            stock_type_id = goods_receipt.stock_type.id
            stock_type = goods_receipt.stock_type.type_code
            location_id = goods_receipt.location_id.id
            location = goods_receipt.location_id.complete_name
            location_dest_id = goods_receipt.location_dest_id.id
            location_dest = goods_receipt.location_dest_id.complete_name
            picking_type_id = goods_receipt.picking_type_id.id
            picking_type = goods_receipt.picking_type_id.name
            scheduled_date = str(goods_receipt.scheduled_date)

            jakarta_tz = pytz.timezone('Asia/Jakarta')
            create_date_utc = goods_receipt.create_date
            create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
            created_date = str(create_date_jakarta)
            date_done = str(goods_receipt.date_done)

            data_goods_receipt_lines = []
            for line_number, line in enumerate(goods_receipt_lines, start=1):
                line_data = {
                    'line_number': line_number,
                    'line_number_sap': line.vit_line_number_sap,
                    'id': line.id,
                    'doc_num': doc_num,
                    'source_document': source_document,
                    'vit_trxid': vit_trxid,
                    'location_id': line.location_id.id,
                    'location': line.location_id.complete_name,
                    'location_dest_id': line.location_dest_id.id,
                    'location_dest': line.location_dest_id.complete_name,
                    'product_id': line.product_id.id,
                    'product_code': line.product_id.default_code or "",
                    'product_name': line.product_id.name,
                    'demand_qty': line.product_uom_qty,
                    'quantity': line.quantity,
                    'product_uom': line.product_uom.name,
                }
                data_goods_receipt_lines.append(line_data)

            response_data = {
                'status': 200,
                'message': 'success',
                'doc_num': doc_num,
                'source_document': source_document,
                'vit_trxid': vit_trxid,
                'customer_id': customer_id,
                'customer_name': customer_name,
                # 'stock_type_id': stock_type_id or int(-1),
                # 'stock_type': stock_type or '',
                'location_id': location_id or int(-1),
                'location': location or '',
                'location_dest_id': location_dest_id or int(-1),
                'location_dest': location_dest or '',
                'picking_type_id': picking_type_id,
                'picking_type': picking_type,
                'created_date': created_date,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'items': data_goods_receipt_lines,
            }
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            return serialize_error_response(str(e))

class InternalTransferAPI(http.Controller):
    @http.route(['/api/internal_transfers/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_internal_transfer(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None, **params):
        try:
            check_authorization()

            # if not q and (not createdDateFrom or not createdDateTo or not pageSize or not page):
            #     raise ValidationError("One or more required parameters are missing.")
            
            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [('picking_type_id.name', '=', 'Internal Transfers'), ('state', '=', 'done')]  # Initialize domain here

            if q:
                domain += [('name', 'ilike', str(q))]

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None: 
                # Handle the case when no specific filters are provided
                # domain = [('name', 'ilike', str(q))] if q else [('state', '=', 'done'), ('picking_type_id.name', '=', 'Internal Transfers')]
                internal_transfers = request.env['stock.picking'].sudo().search(domain)
                total_records = len(internal_transfers)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                          ('create_date', '<=', created_date_to.strftime(date_format)),
                          ('picking_type_id.name', '=', 'Internal Transfers'), ('state', '=', 'done')]
                    
                if is_integrated is not None:
                    is_integrated_bool = str(is_integrated).lower() == 'true'
                    domain += [('is_integrated', '=', is_integrated_bool)]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                internal_transfers, total_records = paginate_records('stock.picking', domain, pageSize, page)
            else:
                internal_transfers = request.env['stock.picking'].sudo().search(domain)
                total_records = len(internal_transfers)

            data_internal_transfers = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for order in internal_transfers:
                create_date_utc = order.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                order_data = {
                    'id': order.id,
                    'doc_num': order.name,
                    'source_document': order.origin,
                    'customer_id': order.partner_id.id or "",
                    'location_id': order.location_id.id,
                    'location': order.location_id.complete_name,
                    'location_dest_id': order.location_dest_id.id,
                    'location_dest': order.location_dest_id.complete_name,
                    'picking_type_id': order.picking_type_id.id,
                    'picking_type': order.picking_type_id.name,
                    'create_date': str(create_date_jakarta),
                    'scheduled_date': str(order.scheduled_date),
                    'date_done': str(order.date_done),
                    'state': order.state,
                    'is_integrated': order.is_integrated
                }
                data_internal_transfers.append(order_data)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_internal_transfers, total_records, total_pages)

        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))

    @http.route(['/api/internal_transfers_line/<int:order_id>'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_internal_transfer_lines(self, order_id, **params):
        try:
            check_authorization()

            internal_transfers = request.env['stock.picking'].sudo().browse(order_id)
            if not internal_transfers:
                raise werkzeug.exceptions.NotFound(_("Internal Transfers not found"))
            
            # Ensure the order is a 'Return' type
            if internal_transfers.picking_type_id.name != 'Internal Transfers':
                raise werkzeug.exceptions.NotFound(_("Internal Transfers is not a Internal Transfers"))

            internal_transfers_lines = internal_transfers.move_ids_without_package
            doc_num = internal_transfers.name
            customer_name = internal_transfers.partner_id.name
            customer_id = internal_transfers.partner_id.id
            location_id = internal_transfers.location_id.id
            location = internal_transfers.location_id.complete_name
            location_dest_id = internal_transfers.location_dest_id.id
            location_dest = internal_transfers.location_dest_id.complete_name
            picking_type_id = internal_transfers.picking_type_id.id
            picking_type = internal_transfers.picking_type_id.name
            scheduled_date = str(internal_transfers.scheduled_date)

            jakarta_tz = pytz.timezone('Asia/Jakarta')
            create_date_utc = internal_transfers.create_date
            create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
            created_date = str(create_date_jakarta)
            date_done = str(internal_transfers.date_done)

            data_internal_transfers_lines = []
            for line_number, line in enumerate(internal_transfers_lines, start=1):
                line_data = {
                    'line_number': line_number,
                    'id': line.id,
                    'doc_no': doc_num,
                    'location_id': line.location_id.id,
                    'location': line.location_id.complete_name,
                    'location_dest_id': line.location_dest_id.id,
                    'location_dest': line.location_dest_id.complete_name,
                    'product_id': line.product_id.id,
                    'product_code': line.product_id.default_code or "",
                    'product_name': line.product_id.name,
                    'demand_qty': line.product_uom_qty,
                    'quantity': line.quantity,
                    'product_uom': line.product_uom.name,
                }
                data_internal_transfers_lines.append(line_data)

            response_data = {
                'status': 200,
                'message': 'success',
                'doc_num': doc_num,
                'customer_id': customer_id,
                'customer_name': customer_name,
                'location_id': location_id,
                'location': location,
                'location_dest_id': location_dest_id,
                'location_dest': location_dest,
                'picking_type_id': picking_type_id,
                'picking_type': picking_type,
                'created_date': created_date,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'items': data_internal_transfers_lines,
            }
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            return serialize_error_response(str(e))
        
class TsOutAPI(http.Controller):
    @http.route(['/api/transfer_stock_out/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_transit_out(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None, **params):
        try:
            check_authorization()

            # if not q and (not createdDateFrom or not createdDateTo or not pageSize or not page):
            #     raise ValidationError("One or more required parameters are missing.")
            
            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [('picking_type_id.name', '=', 'TS Out'), ('state', '=', 'done')]  # Initialize domain here

            if q:
                domain += [('name', 'ilike', str(q))]

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                # Handle the case when no specific filters are provided
                # domain = [('name', 'ilike', str(q))] if q else [('state', '=', 'done'), ('picking_type_id.name', '=', 'TS Out')]
                transit_out = request.env['stock.picking'].sudo().search(domain)
                total_records = len(transit_out)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                          ('create_date', '<=', created_date_to.strftime(date_format)),
                          ('picking_type_id.name', '=', 'TS Out'), ('state', '=', 'done')]
                    
                if is_integrated is not None:
                    is_integrated_bool = str(is_integrated).lower() == 'true'
                    domain += [('is_integrated', '=', is_integrated_bool)]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                transit_out, total_records = paginate_records('stock.picking', domain, pageSize, page)
            else:
                transit_out = request.env['stock.picking'].sudo().search(domain)
                total_records = len(transit_out)

            data_transit_out = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for order in transit_out:
                create_date_utc = order.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                order_data = {
                    'id': order.id,
                    'doc_num': order.name,
                    'transaction_id': order.vit_trxid,
                    'source_document': order.origin,
                    'customer_id': order.partner_id.id or "",
                    'location_id': order.location_id.id,
                    'location': order.location_id.complete_name,
                    'location_dest_id': order.location_dest_id.id,
                    'location_dest': order.location_dest_id.complete_name,
                    'picking_type_id': order.picking_type_id.id,
                    'picking_type': order.picking_type_id.name,
                    'create_date': str(create_date_jakarta),
                    'scheduled_date': str(order.scheduled_date),
                    'date_done': str(order.date_done),
                    'state': order.state
                }
                data_transit_out.append(order_data)

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                total_records = len(data_transit_out)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_transit_out, total_records, total_pages)

        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))

    @http.route(['/api/transfer_stock_out_line/<int:order_id>'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_transit_out_lines(self, order_id, **params):
        try:
            check_authorization()

            transit_out = request.env['stock.picking'].sudo().browse(order_id)
            if not transit_out:
                raise werkzeug.exceptions.NotFound(_("Transfer Out"))
            
            # Ensure the order is a 'Return' type
            if transit_out.picking_type_id.name != 'TS Out':
                raise werkzeug.exceptions.NotFound(_("Transfer is not in TS Out"))

            transit_out_lines = transit_out.move_ids_without_package
            doc_num = transit_out.name
            vit_trxid = transit_out.vit_trxid
            customer_name = transit_out.partner_id.name
            customer_id = transit_out.partner_id.id
            location_id = transit_out.location_id.id
            location = transit_out.location_id.complete_name
            location_dest_id = transit_out.location_dest_id.id
            location_dest = transit_out.location_dest_id.complete_name
            picking_type_id = transit_out.picking_type_id.id
            picking_type = transit_out.picking_type_id.name
            scheduled_date = str(transit_out.scheduled_date)

            jakarta_tz = pytz.timezone('Asia/Jakarta')
            create_date_utc = transit_out.create_date
            create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
            created_date = str(create_date_jakarta)
            date_done = str(transit_out.date_done)

            data_transit_out_lines = []
            for line_number, line in enumerate(transit_out_lines, start=1):
                line_data = {
                    'line_number': line_number,
                    'id': line.id,
                    'doc_no': doc_num,
                    'location_id': line.location_id.id,
                    'location_name': line.location_id.complete_name,
                    'location_dest_id': line.location_dest_id.id,
                    'location_dest': line.location_dest_id.complete_name,
                    'product_id': line.product_id.id,
                    'product_code': line.product_id.default_code or "",
                    'product_name': line.product_id.name,
                    'demand_qty': line.product_uom_qty,
                    'quantity': line.quantity,
                    'product_uom': line.product_uom.name,
                }
                data_transit_out_lines.append(line_data)

            response_data = {
                'status': 200,
                'message': 'success',
                'doc_num': doc_num,
                'transaction_id': vit_trxid, 
                'customer_id': customer_id or "",
                'customer_name': customer_name,
                'location_id': location_id,
                'location': location,
                'location_dest_id': location_dest_id,
                'location_dest': location_dest,
                'picking_type_id': picking_type_id,
                'picking_type': picking_type,
                'created_date': created_date,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'items': data_transit_out_lines,
            }
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            return serialize_error_response(str(e))
        
class TsInAPI(http.Controller):
    @http.route(['/api/transfer_stock_in/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_transit_in(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1, q=None, is_integrated=None, **params):
        try:
            check_authorization()

            # if not q and (not createdDateFrom or not createdDateTo or not pageSize or not page):
            #     raise ValidationError("One or more required parameters are missing.")
            
            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [('picking_type_id.name', '=', 'TS In'), ('state', '=', 'done')]  # Initialize domain here

            if q:
                domain += [('name', 'ilike', str(q))]

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                transit_in = request.env['stock.picking'].sudo().search(domain)
                total_records = len(transit_in)
            else:
                if createdDateFrom or createdDateTo:
                    created_date_from = fields.Date.from_string(createdDateFrom) if createdDateFrom else fields.Date.today()
                    created_date_to = fields.Date.from_string(createdDateTo) if createdDateTo else fields.Date.today()

                    domain += [('create_date', '>=', created_date_from.strftime(date_format)),
                          ('create_date', '<=', created_date_to.strftime(date_format)),
                          ('picking_type_id.name', '=', 'TS In'), ('state', '=', 'done')]

                if is_integrated is not None:
                    is_integrated_bool = str(is_integrated).lower() == 'true'
                    domain += [('is_integrated', '=', is_integrated_bool)]

                pageSize = int(pageSize) if pageSize else 200

            if not q:  # Check if q is provided
                transit_in, total_records = paginate_records('stock.picking', domain, pageSize, page)
            else:
                transit_in = request.env['stock.picking'].sudo().search(domain)
                total_records = len(transit_in)

            data_transit_in = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for order in transit_in:
                create_date_utc = order.create_date
                create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
                order_data = {
                    'id': order.id,
                    'doc_num': order.name,
                    'transaction_id': order.vit_trxid,
                    'source_document': order.origin,
                    'customer_id': order.partner_id.id or "",
                    'location_id': order.location_id.id,
                    'location_name': order.location_id.complete_name,
                    'location_dest_id': order.location_dest_id.id,
                    'location_dest': order.location_dest_id.complete_name,
                    'picking_type_id': order.picking_type_id.id,
                    'picking_type': order.picking_type_id.name,
                    'create_date': str(create_date_jakarta),
                    'scheduled_date': str(order.scheduled_date),
                    'date_done': str(order.date_done),
                    'state': order.state
                }
                data_transit_in.append(order_data)

            if not createdDateFrom and not createdDateTo and not q and is_integrated is None:
                total_records = len(data_transit_in)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_transit_in, total_records, total_pages)

        except ValidationError as ve:
            # If any required parameter is missing, return HTTP 500 error
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))

    @http.route(['/api/transfer_stock_in_line/<int:order_id>'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_transit_in_lines(self, order_id, **params):
        try:
            check_authorization()

            transit_in = request.env['stock.picking'].sudo().browse(order_id)
            if not transit_in:
                raise werkzeug.exceptions.NotFound(_("TS In not found"))
            
            # Ensure the order is a 'Return' type
            if transit_in.picking_type_id.name != 'TS In':
                raise werkzeug.exceptions.NotFound(_("Transfer Is Not In TS In"))

            transit_in_lines = transit_in.move_ids_without_package
            doc_num = transit_in.name
            transaction_id = transit_in.vit_trxid
            customer_name = transit_in.partner_id.name
            customer_id = transit_in.partner_id.id
            location_id = transit_in.location_id.id
            location = transit_in.location_id.complete_name
            location_dest_id = transit_in.location_dest_id.id
            location_dest = transit_in.location_dest_id.complete_name
            picking_type_id = transit_in.picking_type_id.id
            picking_type = transit_in.picking_type_id.name
            scheduled_date = str(transit_in.scheduled_date)

            jakarta_tz = pytz.timezone('Asia/Jakarta')
            create_date_utc = transit_in.create_date
            create_date_jakarta = pytz.utc.localize(create_date_utc).astimezone(jakarta_tz)
            created_date = str(create_date_jakarta)
            date_done = str(transit_in.date_done)

            data_transit_in_lines = []
            for line_number, line in enumerate(transit_in_lines, start=1):
                line_data = {
                    'line_number': line_number,
                    'id': line.id,
                    'doc_no': doc_num,
                    'location_id': line.location_id.id,
                    'location': line.location_id.complete_name,
                    'location_dest_id': line.location_dest_id.id,
                    'location_dest': line.location_dest_id.complete_name,
                    'product_id': line.product_id.id,
                    'product_code': line.product_id.default_code or "",
                    'product_name': line.product_id.name,
                    'demand_qty': line.product_uom_qty,
                    'quantity': line.quantity,
                    'product_uom': line.product_uom.name,
                }
                data_transit_in_lines.append(line_data)

            response_data = {
                'status': 200,
                'message': 'success',
                'doc_num': doc_num,
                'transaction_id': transaction_id,
                'customer_id': customer_id or "",
                'customer_name': customer_name,
                'location_id': location_id,
                'location': location,
                'location_dest_id': location_dest_id,
                'location_dest': location_dest,
                'picking_type_id': picking_type_id,
                'picking_type': picking_type,
                'created_date': created_date,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'items': data_transit_in_lines,
            }
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            return serialize_error_response(str(e))