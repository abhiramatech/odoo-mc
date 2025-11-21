from odoo import http, api, SUPERUSER_ID
from concurrent.futures import ThreadPoolExecutor, as_completed
from odoo.http import request
import requests
from datetime import datetime
import json
import logging
import base64
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


# ==================== CUSTOMER GROUP API ====================

def is_customer_group_pricelist_enabled():
    """Check if vit_cust_group_pricelist is enabled"""
    config = request.env['ir.config_parameter'].sudo()
    return config.get_param('pos.vit_cust_group_pricelist') == 'True'

def is_customer_group_pricelist_enabled():
    config = request.env['ir.config_parameter'].sudo()
    return config.get_param('pos.vit_cust_group_pricelist') == 'True'


class POSTCustomerGroup(http.Controller):

    @http.route('/api/master_customer_group', type='json', auth='none', methods=['POST'], csrf=False)
    def post_customer_group(self, **kw):
        try:
            # 🔐 Cek fitur aktif
            if not is_customer_group_pricelist_enabled():
                return {
                    'status': 'Failed',
                    'code': 403,
                    'message': 'Customer Group Pricelist feature is not enabled. Enable in POS Settings.'
                }

            # 🔐 Authentication
            config = request.env['setting.config'].sudo().search(
                [('vit_config_server', '=', 'mc')], limit=1
            )
            if not config:
                return {'status': 'Failed', 'code': 500, 'message': "Configuration not found."}

            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)

            # JSON Input
            data = request.get_json_data()
            items = data.get('items', [])

            # Normalize input → harus list
            if isinstance(items, dict):
                items = [items]
            elif not isinstance(items, list):
                return {
                    'status': 'Failed',
                    'code': 400,
                    'message': "'items' must be a list or object."
                }

            created = []
            failed = []

            # 🚀 Process each group
            for row in items:
                try:
                    name = row.get('group_name')
                    pricelist_id = row.get('pricelist_id')

                    if not name:
                        failed.append({'data': row, 'message': "Missing group_name", 'id': None})
                        continue

                    if not pricelist_id:
                        failed.append({'data': row, 'message': "Missing pricelist_id", 'id': None})
                        continue

                    # Cek duplikat
                    existing = env['customer.group'].sudo().search(
                        [('vit_group_name', '=', name)], limit=1
                    )
                    if existing:
                        failed.append({
                            'data': row,
                            'message': f"Duplicate customer group '{name}'",
                            'id': existing.id
                        })
                        continue

                    # Validasi pricelist
                    pricelist = env['product.pricelist'].sudo().browse(pricelist_id)
                    if not pricelist.exists():
                        failed.append({
                            'data': row,
                            'message': f"Pricelist ID {pricelist_id} not found",
                            'id': None
                        })
                        continue

                    # Create
                    vals = {
                        'vit_group_name': name,
                        'vit_pricelist_id': pricelist_id,
                        'create_uid': uid,
                    }

                    group = env['customer.group'].sudo().create(vals)

                    created.append({
                        'id': group.id,
                        'group_name': group.vit_group_name,
                        'pricelist_id': group.vit_pricelist_id.id,
                        'pricelist_name': group.vit_pricelist_id.name,
                    })

                except Exception as e:
                    failed.append({
                        'data': row,
                        'message': f"Error: {str(e)}",
                        'id': None
                    })

            return {
                'code': 200 if not failed else 207,
                'status': 'success' if not failed else 'partial_success',
                'created_groups': created,
                'failed_groups': failed
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to create customer groups: {str(e)}", exc_info=True)
            return {
                'status': 'Failed',
                'code': 500,
                'message': f"Failed to create customer groups: {str(e)}"
            }
        
class PATCHCustomerGroup(http.Controller):

    @http.route('/api/master_customer_group', type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_customer_group(self, **kwargs):
        try:
            # 🔐 Cek fitur aktif
            if not is_customer_group_pricelist_enabled():
                return {
                    'status': 'Failed',
                    'code': 403,
                    'message': 'Customer Group Pricelist feature is not enabled. Enable in POS Settings.'
                }

            # 🔐 Authentication
            config = request.env['setting.config'].sudo().search(
                [('vit_config_server', '=', 'mc')], limit=1
            )
            if not config:
                return {'status': 'Failed', 'code': 500, 'message': "Configuration not found."}

            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)

            # JSON Input
            data = request.get_json_data()
            items = data.get('items', [])

            # Normalize → harus list
            if isinstance(items, dict):
                items = [items]
            elif not isinstance(items, list):
                return {
                    'status': 'Failed',
                    'code': 400,
                    'message': "'items' must be a list or object."
                }

            updated = []
            failed = []

            # 🚀 Process each update
            for row in items:
                try:
                    group_id = row.get('id')
                    if not group_id:
                        failed.append({'id': None, 'message': "Missing customer group ID"})
                        continue

                    group = env['customer.group'].sudo().browse(group_id)
                    if not group.exists():
                        failed.append({'id': group_id, 'message': "Customer group not found"})
                        continue

                    vals = {}

                    # Update name
                    if 'group_name' in row:
                        vals['vit_group_name'] = row['group_name']

                    # Update pricelist
                    if 'pricelist_id' in row:
                        pricelist = env['product.pricelist'].sudo().browse(row['pricelist_id'])
                        if not pricelist.exists():
                            failed.append({
                                'id': group_id,
                                'message': f"Pricelist ID {row['pricelist_id']} not found"
                            })
                            continue
                        vals['vit_pricelist_id'] = row['pricelist_id']

                    vals['write_uid'] = uid

                    # Clean None
                    vals = {k: v for k, v in vals.items() if v is not None}

                    group.sudo().write(vals)

                    updated.append({
                        'id': group.id,
                        'group_name': group.vit_group_name,
                        'pricelist_id': group.vit_pricelist_id.id,
                        'pricelist_name': group.vit_pricelist_id.name,
                    })

                except Exception as e:
                    failed.append({
                        'id': row.get('id'),
                        'message': f"Error: {str(e)}"
                    })

            return {
                'code': 200 if not failed else 207,
                'status': 'success' if not failed else 'partial_success',
                'updated_groups': updated,
                'failed_groups': failed
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Error updating customer group: {str(e)}", exc_info=True)
            return {
                'code': 500,
                'status': 'Failed',
                'message': f"Error updating customer groups: {str(e)}"
            }

class POSTMasterTax(http.Controller):

    @http.route('/api/master_tax', type='json', auth='none', methods=['POST'], csrf=False)
    def post_master_tax(self, **kw):
        try:
            # 🔐 Authentication
            config = request.env['setting.config'].sudo().search(
                [('vit_config_server', '=', 'mc')], limit=1
            )
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found."
                }

            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            # Use admin user to avoid access issues
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            items = data.get('items', [])

            if not isinstance(items, list):
                return {'status': "Failed", 'code': 400, 'message': "'items' must be a list."}

            created = []
            failed = []

            # 🧾 Process each tax item
            for tax_data in items:
                try:
                    name = tax_data.get('name')

                    # Cek duplicate by name
                    existing_tax = env['account.tax'].sudo().search(
                        [('name', '=', name)], limit=1
                    )

                    if existing_tax:
                        failed.append({
                            'data': tax_data,
                            'message': f"Tax '{name}' already exists.",
                            'id': existing_tax.id
                        })
                        continue

                    # Build tax fields
                    vals = {
                        'name': name,
                        'description': tax_data.get('description'),
                        'amount_type': 'percent',
                        'active': tax_data.get('active', True),
                        'amount': tax_data.get('amount', 0),
                        'invoice_label': tax_data.get('invoice_label'),
                    }

                    tax = env['account.tax'].sudo().create(vals)

                    created.append({
                        'id': tax.id,
                        'name': tax.name,
                        'amount': tax.amount,
                        'active': tax.active,
                    })

                except Exception as e:
                    failed.append({
                        'data': tax_data,
                        'message': f"Error: {str(e)}",
                        'id': None
                    })

            return {
                'code': 200,
                'status': 'success',
                'created_taxes': created,
                'failed_taxes': failed
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to create taxes: {str(e)}", exc_info=True)
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Failed to create taxes: {str(e)}"
            }

class POSTEmployee(http.Controller):
    @http.route('/api/hr_employee', type='json', auth='none', methods=['POST'], csrf=False)
    def post_employee(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = request.get_json_data()

            # Validate 'items' must be a list
            items = data.get('items', [])
            if not isinstance(items, list):
                return {'status': "Failed", 'code': 400, 'message': "'items' must be a list."}

            created = []  # To store successfully created employees
            failed = []   # To store failed employees

            # Process each item
            for data in items:
                try:
                    # Validate department
                    department_id = data.get('department_id')
                    department = env['hr.department'].sudo().browse(department_id)

                    # Check if employee name already exists
                    existing_employee = env['hr.employee'].sudo().search([('name', '=', data.get('name'))], limit=1)
                    if existing_employee:
                        failed.append({
                            'data': data,
                            'message': f"Employee with name '{data.get('name')}' already exists.",
                            'id': existing_employee.id  # Provide the existing employee's ID
                        })
                        continue

                    # Create employee
                    employee_data = {
                        'vit_employee_code': data.get('employee_code'),
                        'name': data.get('name'),
                        'work_email': data.get('work_email'),
                        'work_phone': data.get('work_phone'),
                        'mobile_phone': data.get('mobile_phone'),
                        'create_uid': uid,
                        'private_street': data.get('address_home_id'),
                        'gender': data.get('gender'),
                        'birthday': data.get('birthdate'),
                        'is_sales': data.get('is_sales', False)
                    }

                    employee = env['hr.employee'].sudo().create(employee_data)

                    created.append({
                        'id': employee.id,
                        'employee_code': employee.vit_employee_code,
                        'name': employee.name,
                    })

                except Exception as e:
                    failed.append({
                        'data': data,
                        'message': f"Error: {str(e)}",
                        'id': None  # ID is not created, so set it to None
                    })

            # Return response
            return {
                'code': 200,
                'status': 'success',
                'created_employees': created,  # List of successfully created employees
                'failed_employees': failed    # List of employees that failed to create with ID and reason
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to create employees: {str(e)}", exc_info=True)
            return {
                'status': "Failed", 
                'code': 500, 
                'message': f"Failed to create employees: {str(e)}"
            }


class POSTMasterBoM(http.Controller):
    @http.route('/api/master_bom', type='json', auth='none', methods=['POST'], csrf=False)
    def post_master_bom(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = request.get_json_data()
            product_tmpl_id = data.get('product_tmpl_id')
            product_id = data.get('product_id')
            quantity = data.get('quantity')
            reference = data.get('reference')
            type = data.get('type')
            move_lines = data.get('move_lines', [])

            # Validate picking type
            product_tmpl = env['product.template'].sudo().search([('default_code', '=', product_tmpl_id)], limit=1)
            if not product_tmpl:
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Product Template '{product_tmpl.name}' not found."
                }
            
            product_variant = env['product.product'].sudo().search([('default_code', '=', product_id)], limit=1)
            if not product_variant:
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Product Variant '{product_variant.name}' not found."
                }

            # Validate all products first before creating Goods Receipt
            missing_products = []
            for line in move_lines:
                product_code = line.get('product_code')
                product_id = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
                if not product_id:
                    missing_products.append(product_code)

            if missing_products:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': f"Products with codes {', '.join(missing_products)} not found. Goods Receipt creation cancelled."
                }

            # Create BoM
            bom_master = env['mrp.bom'].sudo().create({
                'product_tmpl_id': product_tmpl.id,
                'product_id': product_variant.id,
                'product_qty': quantity,
                'code': reference,
                'type': type,
            })

            # Update goods receipt with move lines
            bom_master.write({
                'bom_line_ids': [(0, 0, line) for line in move_lines]
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'BoM created and validated successfully',
                'id': bom_master.id,
                'doc_num': bom_master.product_id.name
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to create BoM: {str(e)}", exc_info=True)
            return {
                'status': "Failed", 
                'code': 500, 
                'message': f"Failed to create BoM: {str(e)}"
            }

class POSTMasterItem(http.Controller):
    @http.route('/api/master_item', type='json', auth='none', methods=['POST'], csrf=False)
    def post_master_item(self, **kw):
        try:
            # 🔐 Autentikasi
            config = request.env['setting.config'].sudo().search(
                [('vit_config_server', '=', 'mc')], limit=1
            )
            if not config:
                return {'code': 500, 'status': 'Failed', 'message': 'Configuration not found.'}

            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {'code': 401, 'status': 'Failed', 'message': 'Authentication failed.'}

            json_data = request.get_json_data()
            items = json_data.get('items', [])
            if isinstance(items, dict):
                items = [items]

            vals_list, created, errors = [], [], []

            # 💾 CACHE untuk menghindari banyak search
            cache_categories = {}
            cache_uom = {}
            cache_pos = {}
            cache_tax = {}

            model_category = request.env['product.category'].sudo()
            model_uom = request.env['uom.uom'].sudo()
            model_pos = request.env['pos.category'].sudo()
            model_tax = request.env['account.tax'].sudo()
            model_product = request.env['product.template'].sudo()

            BATCH_SIZE = 50  # ⬅ untuk mencegah overloading create()

            # 🔹 Validasi & Siapkan data
            for data in items:
                try:
                    product_code = data.get('product_code')
                    if not product_code:
                        errors.append({'id': -1, 'product_code': None, 'message': "Missing product_code"})
                        continue

                    # Duplicate check
                    existing_product = model_product.search(
                        [('default_code', '=', product_code)], limit=1
                    )
                    if existing_product:
                        errors.append({
                            'id': existing_product.id,
                            'product_code': product_code,
                            'message': f"Duplicate item code: {product_code}"
                        })
                        continue

                    # CATEGORY CACHE
                    category_name = data.get('category_name')
                    if not category_name:
                        errors.append({'id': -1, 'product_code': product_code, 'message': "category_name missing"})
                        continue

                    if category_name in cache_categories:
                        category = cache_categories[category_name]
                    else:
                        category = model_category.search([('complete_name', '=', category_name)], limit=1)
                        cache_categories[category_name] = category

                    if not category:
                        errors.append({'id': -1, 'product_code': product_code,
                                       'message': f"Category '{category_name}' not found."})
                        continue

                    # POS CATEGORY CACHE
                    pos_categ_command = []
                    pos_data = data.get('pos_categ_ids', data.get('pos_categ_id', []))
                    if not isinstance(pos_data, list):
                        pos_data = [pos_data]

                    for cid in pos_data:
                        if cid in cache_pos:
                            pos_obj = cache_pos[cid]
                        else:
                            pos_obj = model_pos.search([('id', '=', cid)], limit=1)
                            cache_pos[cid] = pos_obj

                        if pos_obj:
                            pos_categ_command.append((4, cid))
                        else:
                            errors.append({'id': -1, 'product_code': product_code,
                                           'message': f"POS category ID {cid} not found."})

                    # TAX CACHE
                    tax_command = []
                    tax_names = data.get('taxes_names', [])
                    if not isinstance(tax_names, list):
                        tax_names = [tax_names]

                    for tax_name in tax_names:
                        if tax_name in cache_tax:
                            tax = cache_tax[tax_name]
                        else:
                            tax = model_tax.search([('name', '=', tax_name)], limit=1)
                            cache_tax[tax_name] = tax

                        if tax:
                            tax_command.append((4, tax.id))
                        else:
                            errors.append({'id': -1, 'product_code': product_code,
                                           'message': f"Tax '{tax_name}' not found."})

                    # UOM CACHE
                    uom_name = data.get('uom_name')
                    if not uom_name:
                        errors.append({'id': -1, 'product_code': product_code, 'message': "uom_name missing"})
                        continue

                    if uom_name in cache_uom:
                        uom = cache_uom[uom_name]
                    else:
                        uom = model_uom.search([('name', '=', uom_name)], limit=1)
                        cache_uom[uom_name] = uom

                    if not uom:
                        errors.append({'id': -1, 'product_code': product_code, 'message': f"UoM '{uom_name}' not found."})
                        continue

                    # UOM PO CACHE
                    uom_po_name = data.get('uom_po_name')
                    if not uom_po_name:
                        errors.append({'id': -1, 'product_code': product_code, 'message': "uom_po_name missing"})
                        continue

                    if uom_po_name in cache_uom:
                        uom_po = cache_uom[uom_po_name]
                    else:
                        uom_po = model_uom.search([('name', '=', uom_po_name)], limit=1)
                        cache_uom[uom_po_name] = uom_po

                    if not uom_po:
                        errors.append({'id': -1, 'product_code': product_code,
                                       'message': f"Purchase UoM '{uom_po_name}' not found."})
                        continue

                    # Cek kategori uom = wajib sama
                    if uom.category_id.id != uom_po.category_id.id:
                        errors.append({'id': -1, 'product_code': product_code,
                                       'message': "Default UoM and Purchase UoM must match."})
                        continue

                    # Append vals
                    cost = data.get('standard_price', data.get('cost', 0.0))

                    vals_list.append({
                        'name': data.get('product_name'),
                        'active': data.get('active'),
                        'default_code': product_code,
                        'detailed_type': data.get('product_type'),
                        'invoice_policy': data.get('invoice_policy'),
                        'list_price': data.get('sales_price'),
                        'standard_price': cost,
                        'uom_id': uom.id,
                        'uom_po_id': uom_po.id,
                        'pos_categ_ids': pos_categ_command,
                        'categ_id': category.id,
                        'taxes_id': tax_command,
                        'available_in_pos': data.get('available_in_pos'),
                        'barcode': data.get('barcode'),
                        'image_1920': data.get('image_1920'),
                        'create_uid': uid,
                    })

                    # ⏳ Create batch per 50 item
                    if len(vals_list) >= BATCH_SIZE:
                        products = model_product.create(vals_list)
                        for rec in products:
                            created.append({'id': rec.id, 'product_code': rec.default_code, 'name': rec.name})
                        vals_list = []  # kosongkan batch

                except Exception as e:
                    errors.append({'id': -1, 'product_code': data.get('product_code'), 'message': str(e)})

            # Create sisa batch
            if vals_list:
                products = model_product.create(vals_list)
                for rec in products:
                    created.append({'id': rec.id, 'product_code': rec.default_code, 'name': rec.name})

            return {
                'code': 200 if not errors else 207,
                'status': 'success' if not errors else 'partial_success',
                'created_items': created,
                'errors': errors
            }

        except Exception as e:
            request.env.cr.rollback()
            return {'status': 'Failed', 'code': 500, 'message': str(e)}



class POSTMasterPricelist(http.Controller):
    @http.route('/api/master_pricelist', type='json', auth='none', methods=['POST'], csrf=False)
    def post_pricelist(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = request.get_json_data()
            
            # Validate required fields
            required_fields = ['name', 'currency_id', 'pricelist_ids']
            missing_fields = [field for field in required_fields if not data.get(field)]
            if missing_fields:
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Missing required fields: {', '.join(missing_fields)}"
                }

            name = data.get('name')
            currency_id = data.get('currency_id')

            # Validate currency
            currency = env['res.currency'].sudo().browse(currency_id)
            if not currency.exists():
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Currency with ID {currency_id} not found."
                }

            # Check for duplicate pricelist
            existing_pricelist = env['product.pricelist'].sudo().search([('name', '=', name)], limit=1)
            if existing_pricelist:
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Pricelist with name '{name}' already exists.",
                    'id': existing_pricelist.id
                }

            # Validate all products first
            missing_products = []
            invalid_dates = []
            items_lines_data = []

            for line in data.get('pricelist_ids', []):
                product_code = line.get('product_code')
                if not product_code:
                    return {
                        'status': "Failed", 
                        'code': 400, 
                        'message': "Product code is required for all pricelist items."
                    }

                product = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
                if not product:
                    missing_products.append(product_code)
                    continue

                # Validate and parse dates
                date_start = line.get('date_start')
                date_end = line.get('date_end')
                
                try:
                    if date_start:
                        date_start = datetime.strptime(date_start.split('.')[0], '%Y-%m-%d %H:%M:%S')
                    if date_end:
                        date_end = datetime.strptime(date_end.split('.')[0], '%Y-%m-%d %H:%M:%S')
                        
                    if date_start and date_end and date_start > date_end:
                        invalid_dates.append(product_code)
                        continue
                except ValueError as e:
                    return {
                        'status': "Failed", 
                        'code': 400, 
                        'message': f"Invalid date format for product {product_code}: {str(e)}"
                    }

                # Validate pricing fields
                compute_price = line.get('compute_price')
                if compute_price == 'percentage' and not line.get('percent_price'):
                    return {
                        'status': "Failed", 
                        'code': 400, 
                        'message': f"Percent price is required for percentage computation for product {product_code}"
                    }
                elif compute_price == 'fixed' and not line.get('fixed_price'):
                    return {
                        'status': "Failed", 
                        'code': 400, 
                        'message': f"Fixed price is required for fixed computation for product {product_code}"
                    }

                items_lines_data.append({
                    'product_tmpl_id': product.product_tmpl_id.id,
                    'applied_on': line.get('conditions'),
                    'compute_price': compute_price,
                    'percent_price': line.get('percent_price'),
                    'fixed_price': line.get('fixed_price'),
                    'min_quantity': line.get('quantity', 1),
                    'price': line.get('price'),
                    'date_start': date_start,
                    'date_end': date_end,
                })

            if missing_products:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': f"Products with codes {', '.join(missing_products)} not found. Pricelist creation cancelled."
                }

            if invalid_dates:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': f"Invalid date range for products: {', '.join(invalid_dates)}"
                }

            try:
                # Create pricelist
                pricelist_data = {
                    'name': name,
                    'currency_id': currency_id,
                    'create_uid': uid,
                    'item_ids': [(0, 0, line_data) for line_data in items_lines_data],
                }

                pricelist = env['product.pricelist'].sudo().create(pricelist_data)

            except Exception as create_error:
                request.env.cr.rollback()
                _logger.error(f"Failed to create pricelist: {str(create_error)}", exc_info=True)
                return {
                    'status': "Failed", 
                    'code': 500, 
                    'message': f"Failed to create pricelist: {str(create_error)}"
                }

            return {
                'code': 200,
                'status': 'success',
                'message': 'Price List created successfully',
                'id': pricelist.id,
                'name': pricelist.name
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to create Pricelist: {str(e)}", exc_info=True)
            return {
                'status': "Failed", 
                'code': 500, 
                'message': f"Failed to create Pricelist: {str(e)}"
            }
        
class POSTMasterUoM(http.Controller):
    @http.route('/api/master_uom', type='json', auth='none', methods=['POST'], csrf=False)
    def post_master_uom(self, **kw):
        try:
            # 🔐 Autentikasi
            config = request.env['setting.config'].sudo().search(
                [('vit_config_server', '=', 'mc')], limit=1
            )
            if not config:
                return {
                    'status': 'Failed',
                    'code': 500,
                    'message': 'Configuration not found.'
                }

            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {
                    'status': 'Failed',
                    'code': 401,
                    'message': 'Authentication failed.'
                }

            json_data = request.get_json_data()
            items = json_data.get('items')

            # ✅ Bisa single dict atau list
            if isinstance(items, dict):
                items = [items]
            elif items is None and isinstance(json_data, dict):
                items = [json_data]
            elif not isinstance(items, list):
                return {
                    'status': 'Failed',
                    'code': 400,
                    'message': "'items' must be a list or object."
                }

            vals_list, created, errors = [], [], []

            # 🔍 Validasi & kumpulkan data
            for data in items:
                try:
                    name = data.get('name')
                    uom_type = data.get('uom_type')
                    category_id = data.get('category_id')

                    if not name or not uom_type or not category_id:
                        errors.append({
                            'name': name,
                            'message': "Missing required field: name, uom_type, or category_id"
                        })
                        continue

                    # Cek duplikat berdasarkan name & category_id
                    existing = request.env['uom.uom'].sudo().search([
                        ('name', '=', name),
                        ('category_id', '=', category_id)
                    ], limit=1)
                    if existing:
                        errors.append({
                            'id': existing.id,
                            'name': name,
                            'message': f"Duplicate UoM with name '{name}' in this category"
                        })
                        continue

                    vals_list.append({
                        'name': name,
                        'uom_type': uom_type,
                        'category_id': category_id,
                        'rounding': data.get('rounding', 1.0),
                        'ratio': data.get('ratio', 1.0),
                        'active': data.get('active', True),
                        'factor': data.get('factor', 1.0),
                        'factor_inv': data.get('factor_inv', 1.0),
                    })

                except Exception as e:
                    errors.append({
                        'name': data.get('name'),
                        'message': f"Exception: {str(e)}"
                    })

            # 🚀 Bulk create
            if vals_list:
                uoms = request.env['uom.uom'].sudo().create(vals_list)
                for rec in uoms:
                    created.append({
                        'id': rec.id,
                        'name': rec.name,
                        'uom_type': rec.uom_type,
                        'category_id': rec.category_id.id,
                        'category': rec.category_id.name,
                        'status': 'success'
                    })

            return {
                'code': 200 if not errors else 207,
                'status': 'success' if not errors else 'partial_success',
                'created_uoms': created,
                'errors': errors
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to create UoMs: {str(e)}")
            return {
                'status': 'Failed',
                'code': 500,
                'message': f"Failed to create UoMs: {str(e)}"
            }


class POSTMasterCustomer(http.Controller):
    @http.route('/api/master_customer', type='json', auth='none', methods=['POST'], csrf=False)
    def post_master_customer(self, **kw):
        try:
            # Autentikasi
            config = request.env['setting.config'].sudo().search(
                [('vit_config_server', '=', 'mc')], limit=1
            )
            if not config:
                return {
                    'status': 'Failed',
                    'code': 500,
                    'message': 'Configuration not found.'
                }

            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {
                    'status': 'Failed',
                    'code': 401,
                    'message': 'Authentication failed.'
                }

            json_data = request.get_json_data()
            items = json_data.get('items')

            # ✅ Bisa single dict atau list
            if isinstance(items, dict):
                items = [items]
            elif items is None and isinstance(json_data, dict):
                items = [json_data]
            elif not isinstance(items, list):
                return {
                    'status': 'Failed',
                    'code': 400,
                    'message': "'items' must be a list or object."
                }

            vals_list, created, errors = [], [], []

            # 🔹 Validasi & kumpulkan data
            for data in items:
                try:
                    customer_code = data.get('customer_code')
                    if not customer_code:
                        errors.append({
                            'id': None,
                            'customer_code': None,
                            'message': "Missing customer_code"
                        })
                        continue

                    # Cek duplikat
                    existing = request.env['res.partner'].sudo().search(
                        [('customer_code', '=', customer_code)], limit=1
                    )
                    if existing:
                        errors.append({
                            'id': existing.id,
                            'customer_code': customer_code,
                            'message': f"Duplicate Customer code: {customer_code}"
                        })
                        continue

                    # Data customer
                    vals_list.append({
                        'name': data.get('name'),
                        'customer_code': customer_code,
                        'street': data.get('street'),
                        'phone': data.get('phone'),
                        'email': data.get('email'),
                        'mobile': data.get('mobile'),
                        'website': data.get('website'),
                        'create_uid': uid,
                        ''
                        'customer_rank': 1,  # supaya otomatis dianggap customer
                    })

                except Exception as e:
                    errors.append({
                        'id': data.get('id'),
                        'customer_code': data.get('customer_code'),
                        'message': f"Exception: {str(e)}"
                    })

            # 🔹 Bulk create kalau ada data valid
            if vals_list:
                customers = request.env['res.partner'].sudo().create(vals_list)
                for rec in customers:
                    created.append({
                        'id': rec.id,
                        'customer_code': rec.customer_code,
                        'name': rec.name,
                        'email': rec.email,
                        'status': 'success'
                    })

            return {
                'code': 200 if not errors else 207,
                'status': 'success' if not errors else 'partial_success',
                'created_customers': created,
                'errors': errors
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to create customers: {str(e)}")
            return {
                'status': 'Failed',
                'code': 500,
                'message': f"Failed to create customers: {str(e)}"
            }
    
class POSTMasterWarehouse(http.Controller):
    @http.route('/api/master_warehouse', type='json', auth='none', methods=['POST'], csrf=False)
    def post_master_warehouse(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = data = request.get_json_data()
            code = data.get('code')

            if env['stock.warehouse'].sudo().search([('code', '=', code)], limit=1):
                return {'status': "Failed", 'code': 400, 'message': f"Duplicate Warehouse code: {code}"}

            warehouse_data = {
                'name': data.get('name'),
                'code': code,
                'create_uid': uid
            }

            warehouse = env['stock.warehouse'].sudo().create(warehouse_data)
            
            return {
                'code': 200,
                'status': 'success',
                'message': 'Warehouse created successfully',
                'id': warehouse.id,
            }
        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to create Warehouse: {str(e)}")
            return {'status': "Failed", 'code': 500, 'message': f"Failed to create Warehouse: {str(e)}"}
    
class POSTItemCategory(http.Controller):
    @http.route('/api/item_category', type='json', auth='none', methods=['POST'], csrf=False)
    def post_item_group(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = data = request.get_json_data()
            category_name = data.get('category_name')

            if env['product.category'].sudo().search([('name', '=', category_name)], limit=1):
                return {'status': "Failed", 'code': 400, 'message': f"Duplicate category name: {category_name}."}

            category_data = {
                'name': category_name,
                'parent_id': data.get('parent_category_id'),
                'property_cost_method': data.get('costing_method'),
                'create_date': data.get('create_date'),
                'create_uid': uid
            }

            category = env['product.category'].sudo().create(category_data)
            
            return {
                'code': 200,
                'status': 'success',
                'message': 'Item Category created successfully',
                'id': category.id,
            }
        
        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to create Category: {str(e)}")
            return {'status': "Failed", 'code': 500, 'message': f"Failed to create Category: {str(e)}"}

class POSTItemPoSCategory(http.Controller):
    @http.route('/api/pos_category', type='json', auth='none', methods=['POST'], csrf=False)
    def post_pos_category(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = data = request.get_json_data()
            category_name = data.get('category_name')

            if env['pos.category'].sudo().search([('name', '=', category_name)], limit=1):
                return {'status': "Failed", 'code': 400, 'message': f"Duplicate PoS category name: {category_name}."}

            category_data = {
                'name': category_name,
                'create_date': data.get('create_date'),
                'create_uid': uid
            }

            category = env['pos.category'].sudo().create(category_data)
            
            return {
                'code': 200,
                'status': 'success',
                'message': 'PoS Category created successfully',
                'id': category.id,
            }
        
        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to create PoS Category: {str(e)}")
            return {'status': "Failed", 'code': 500, 'message': f"Failed to create PoS Category: {str(e)}"}
        
class POSTGoodsReceipt(http.Controller):
    @http.route('/api/goods_receipt', type='json', auth='none', methods=['POST'], csrf=False)
    def post_goods_receipt(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = request.get_json_data()
            picking_type_name = data.get('picking_type')
            location_id = data.get('location_id')
            location_dest_id = data.get('location_dest_id')
            scheduled_date = data.get('scheduled_date')
            date_done = data.get('date_done')
            transaction_id = data.get('transaction_id')
            move_type = data.get('move_type')
            move_lines = data.get('move_lines', [])

            # Validate if Goods Receipt already exists
            existing_goods_receipts = env['stock.picking'].sudo().search([
                ('vit_trxid', '=', transaction_id), 
                ('picking_type_id.name', '=', 'Goods Receipts')
            ], limit=1)
            
            if existing_goods_receipts:   
                return {
                    'code': 400,
                    'status': 'failed',
                    'message': 'Goods Receipt already exists',
                    'id': existing_goods_receipts.id,
                    'doc_num': existing_goods_receipts.name
                }

            # Validate picking type
            picking_type = env['stock.picking.type'].sudo().search([('name', '=', picking_type_name)], limit=1)
            if not picking_type:
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Picking type '{picking_type_name}' not found."
                }

            # Validate locations
            source_location = env['stock.location'].sudo().browse(location_id)
            dest_location = env['stock.location'].sudo().browse(location_dest_id)
            
            if not source_location.exists():
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Source location with ID {location_id} not found."
                }
            
            if not dest_location.exists():
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Destination location with ID {location_dest_id} not found."
                }

            # Validate all products first before creating Goods Receipt
            missing_products = []
            for line in move_lines:
                product_code = line.get('product_code')
                product_id = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
                if not product_id:
                    missing_products.append(product_code)

            if missing_products:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': f"Products with codes {', '.join(missing_products)} not found. Goods Receipt creation cancelled."
                }

            # Create Goods Receipt
            goods_receipt = env['stock.picking'].sudo().create({
                'picking_type_id': picking_type.id,
                'location_id': location_dest_id,
                'location_dest_id': location_id,
                'move_type': move_type,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'vit_trxid': transaction_id,
                'create_uid': uid,
                # 'immediate_transfer': True  # Added to ensure immediate transfer
            })

            # Create move lines
            move_line_vals = []
            for line in move_lines:
                product_code = line.get('product_code')
                product_uom_qty = line.get('product_uom_qty')
                product_id = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)

                move_vals = {
                    'name': product_id.name,
                    'product_id': product_id.id,
                    'product_uom': product_id.uom_id.id,  # Added product UOM
                    'product_uom_qty': float(product_uom_qty),
                    'quantity': float(product_uom_qty),  # Added to ensure validation
                    'picking_id': goods_receipt.id,
                    'location_id': location_id,
                    'location_dest_id': location_dest_id,
                    'state': 'draft',
                }
                move_line_vals.append((0, 0, move_vals))

            # Update goods receipt with move lines
            goods_receipt.write({
                'move_ids_without_package': move_line_vals
            })

            try:
                # Validate the goods receipt
                goods_receipt.button_validate()
            except Exception as validate_error:
                env.cr.rollback()
                # If validation fails, delete the goods receipt and return error
                goods_receipt.sudo().unlink()
                raise Exception(f"Failed to validate Goods Receipt: {str(validate_error)}")

            return {
                'code': 200,
                'status': 'success',
                'message': 'Goods Receipt created and validated successfully',
                'id': goods_receipt.id,
                'doc_num': goods_receipt.name
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to create Goods Receipt: {str(e)}", exc_info=True)
            return {
                'status': "Failed", 
                'code': 500, 
                'message': f"Failed to create Goods Receipt: {str(e)}"
            }

class POSTGoodsIssue(http.Controller):
    @http.route('/api/goods_issue', type='json', auth='none', methods=['POST'], csrf=False)
    def post_goods_issue(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = request.get_json_data()
            picking_type_name = data.get('picking_type')
            location_id = data.get('location_id')
            location_dest_id = data.get('location_dest_id')
            scheduled_date = data.get('scheduled_date')
            date_done = data.get('date_done')
            transaction_id = data.get('transaction_id')
            move_type = data.get('move_type')
            move_lines = data.get('move_lines', [])

            # Validate if Goods Issue already exists
            existing_goods_issue = env['stock.picking'].sudo().search([
                ('vit_trxid', '=', transaction_id), 
                ('picking_type_id.name', '=', 'Goods Issue')
            ], limit=1)
            
            if existing_goods_issue:    
                return {
                    'code': 400,
                    'status': 'failed',
                    'message': 'Goods Issue already exists',
                    'id': existing_goods_issue.id,
                    'doc_num': existing_goods_issue.name
                }         

            # Validate picking type
            picking_type = env['stock.picking.type'].sudo().search([('name', '=', picking_type_name)], limit=1)
            if not picking_type:
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Picking type '{picking_type_name}' not found."
                }

            # Validate locations
            source_location = env['stock.location'].sudo().browse(location_id)
            dest_location = env['stock.location'].sudo().browse(location_dest_id)
            
            if not source_location.exists():
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Source location with ID {location_id} not found."
                }
            
            if not dest_location.exists():
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Destination location with ID {location_dest_id} not found."
                }

            # Validate all products first before creating Goods Issue
            missing_products = []
            for line in move_lines:
                product_code = line.get('product_code')
                product_id = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
                if not product_id:
                    missing_products.append(product_code)

            if missing_products:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': f"Products with codes {', '.join(missing_products)} not found. Goods Issue creation cancelled."
                }

            # Create Goods Issue
            goods_issue = env['stock.picking'].sudo().create({
                'picking_type_id': picking_type.id,
                'location_id': location_id,
                'location_dest_id': location_dest_id,
                'move_type': move_type,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'vit_trxid': transaction_id,
                'create_uid': uid,
                # 'immediate_transfer': True  # Added to ensure immediate transfer
            })

            # Create move lines
            move_line_vals = []
            for line in move_lines:
                product_code = line.get('product_code')
                product_uom_qty = line.get('product_uom_qty')
                product_id = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)

                move_vals = {
                    'name': product_id.name,
                    'product_id': product_id.id,
                    'product_uom': product_id.uom_id.id,  # Added product UOM
                    'product_uom_qty': product_uom_qty,
                    'quantity': product_uom_qty,  # Added to ensure validation
                    'picking_id': goods_issue.id,
                    'location_id': location_id,
                    'location_dest_id': location_dest_id,
                    'state': 'draft',
                }
                move_line_vals.append((0, 0, move_vals))

            # Update goods issue with move lines
            goods_issue.write({
                'move_ids_without_package': move_line_vals
            })

            try:
                # Validate the goods issue
                goods_issue.button_validate()
            except Exception as validate_error:
                env.cr.rollback()
                # If validation fails, delete the goods issue and return error
                goods_issue.sudo().unlink()
                raise Exception(f"Failed to validate Goods Issue: {str(validate_error)}")

            return {
                'code': 200,
                'status': 'success',
                'message': 'Goods Issue created and validated successfully',
                'id': goods_issue.id,
                'doc_num': goods_issue.name
            }
            
        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to create Goods Issue: {str(e)}", exc_info=True)
            return {
                'status': "Failed", 
                'code': 500, 
                'message': f"Failed to create Goods Issue: {str(e)}"
            }
        
class POSTPurchaseOrderFromSAP(http.Controller):
    @http.route('/api/purchase_order', type='json', auth='none', methods=['POST'], csrf=False)
    def post_purchase_order(self, **kw):
        try:
            # 🔐 Authentication
            config = request.env['setting.config'].sudo().search(
                [('vit_config_server', '=', 'mc')], limit=1
            )
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}

            uid = request.session.authenticate(
                request.session.db,
                config.vit_config_username,
                config.vit_config_password_api
            )
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)

            # 📥 Get JSON payload
            data = request.get_json_data()
            customer_code = data.get('customer_code')
            vendor_reference = data.get('vendor_reference')
            currency_name = data.get('currency_id')        # nama currency, ex: "IDR"
            date_order = data.get('date_order')
            transaction_id = data.get('transaction_id')
            expected_arrival = data.get('expected_arrival')
            picking_type_name = data.get('picking_type')
            location_id = data.get('location_id')
            order_line = data.get('order_line', [])

            # 🔎 Check duplicate PO
            existing_po = env['purchase.order'].sudo().search([
                ('vit_trxid', '=', transaction_id),
                ('picking_type_id.name', '=', picking_type_name),
                ('picking_type_id.default_location_dest_id', '=', location_id)
            ], limit=1)

            if existing_po:
                return {
                    'code': 500,
                    'status': 'failed',
                    'message': 'Purchase Order already exists',
                    'id': existing_po.id,
                }

            # 🔎 Validate customer
            customer_id = env['res.partner'].sudo().search(
                [('customer_code', '=', customer_code)], limit=1
            ).id
            if not customer_id:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Customer with code '{customer_code}' not found.",
                }

            # 🔎 Validate currency
            currency = env['res.currency'].sudo().search([('name', '=', currency_name)], limit=1)
            if not currency:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Currency with name '{currency_name}' not found.",
                }
            currency_id = currency.id

            # 🔎 Validate picking type
            picking_types = env['stock.picking.type'].sudo().search([
                ('name', '=', picking_type_name),
                ('default_location_dest_id', '=', location_id)
            ], limit=1)

            if not picking_types:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Picking type with name '{picking_type_name}' and location_id '{location_id}' not found.",
                }

            # 🔎 Validate all products first
            missing_products = []
            for line in order_line:
                product_code = line.get('product_code')
                product_id = env['product.product'].sudo().search(
                    [('default_code', '=', product_code)], limit=1
                )
                if not product_id:
                    missing_products.append(product_code)

            if missing_products:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Products with codes {', '.join(missing_products)} not found. Purchase Order creation cancelled.",
                }

            # 🧾 Build purchase order lines
            purchase_order_lines = []
            for line in order_line:
                product_code = line.get('product_code')
                product_uom_qty = line.get('product_uom_qty')
                price_unit = line.get('price_unit')
                taxes_name = line.get('taxes_ids')
                vit_line_number_sap = line.get('line_number_sap')

                # Validate tax
                tax = env['account.tax'].sudo().search([('name', '=', taxes_name)], limit=1)
                if not tax:
                    return {
                        'status': "Failed",
                        'code': 500,
                        'message': f"Failed to create PO. Tax not found: {taxes_name}.",
                    }

                product_id = env['product.product'].sudo().search(
                    [('default_code', '=', product_code)], limit=1
                )

                purchase_order_line = {
                    'name': product_id.name,
                    'product_id': product_id.id,
                    'product_qty': product_uom_qty,
                    'price_unit': price_unit,
                    'taxes_id': [(6, 0, [tax.id])],
                    'vit_line_number_sap': vit_line_number_sap,
                    'product_uom': product_id.uom_id.id,
                }
                purchase_order_lines.append((0, 0, purchase_order_line))

            # 📝 Create purchase order
            purchase_order = env['purchase.order'].sudo().create({
                'partner_id': customer_id,
                'partner_ref': vendor_reference,
                'currency_id': currency_id,
                'date_order': date_order,
                'date_planned': expected_arrival,
                'vit_trxid': transaction_id,
                'picking_type_id': picking_types.id,
                'create_uid': uid,
                'user_id': uid,
                'order_line': purchase_order_lines,
            })

            # ✅ Confirm purchase order
            purchase_order.button_confirm()

            # 🔄 Update related pickings
            picking_ids = env['stock.picking'].sudo().search([('purchase_id', '=', purchase_order.id)])
            if picking_ids:
                for picking in picking_ids:
                    for move in picking.move_ids_without_package:
                        move.product_uom_qty = move.quantity
                    picking.write({
                        'origin': purchase_order.name,
                        'vit_trxid': transaction_id
                    })

            return {
                'code': 200,
                'status': 'success',
                'message': 'Purchase created and validated successfully',
                'id': purchase_order.id,
                'doc_num': purchase_order.name
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error(f"Failed to create Purchase Order: {str(e)}", exc_info=True)
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Failed to create Purchase Order: {str(e)}",
            }