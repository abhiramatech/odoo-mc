from odoo import http
from odoo.http import request
import json
from odoo.exceptions import AccessError
from concurrent.futures import ThreadPoolExecutor, as_completed
from .api_utils import check_authorization, paginate_records, serialize_response, serialize_error_response
import logging
_logger = logging.getLogger(__name__)

class MasterCustomerPATCH(http.Controller):
    @http.route(['/api/master_customer'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_master_customer(self, **kwargs):
        try:
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

            json_data = request.get_json_data()
            items = json_data.get('items')

            if isinstance(items, dict):
                items = [items]
            elif not isinstance(items, list):
                return {'status': 'Failed', 'code': 400, 'message': "'items' must be a list or object."}

            updated, errors = [], []

            for data in items:
                try:
                    customer_code = data.get('customer_code')
                    if not customer_code:
                        errors.append({'customer_code': None, 'message': "Missing customer_code"})
                        continue

                    master_customer = request.env['res.partner'].sudo().search(
                        [('customer_code', '=', customer_code)], limit=1
                    )
                    if not master_customer:
                        errors.append({
                            'customer_code': customer_code,
                            'message': "Customer not found."
                        })
                        continue

                    update_data = {
                        'name': data.get('name'),
                        'street': data.get('street'),
                        'email': data.get('email'),
                        'mobile': data.get('mobile'),
                        'website': data.get('website'),
                        'is_integrated': data.get('is_integrated'),
                        'write_uid': uid,
                    }

                    master_customer.sudo().write(update_data)

                    updated.append({
                        'id': master_customer.id,
                        'customer_code': master_customer.customer_code,
                        'name': master_customer.name,
                        'status': 'success'
                    })

                except Exception as e:
                    errors.append({
                        'customer_code': data.get('customer_code'),
                        'message': f"Exception: {str(e)}"
                    })

            return {
                'code': 200 if not errors else 207,
                'status': 'success' if not errors else 'partial_success',
                'updated_customers': updated,
                'errors': errors
            }

        except Exception as e:
            _logger.error(f"Error updating master customer: {str(e)}")
            return {'code': 500, 'status': 'failed', 'message': str(e)}




class MasterItemPATCH(http.Controller):
    @http.route(['/api/master_item'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_master_item(self, **kwargs):
        try:
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
            elif not isinstance(items, list):
                return {'code': 400, 'status': 'Failed', 'message': "'items' must be a list or object."}

            updated, errors = [], []

            for data in items:
                try:
                    product_code = data.get('product_code')
                    if not product_code:
                        errors.append({'product_code': None, 'message': "Missing product_code"})
                        continue

                    master_item = request.env['product.template'].sudo().search(
                        [('default_code', '=', product_code)], limit=1
                    )
                    if not master_item:
                        errors.append({
                            'product_code': product_code,
                            'message': f"Product not found with code: {product_code}"
                        })
                        continue

                    # category
                    category_name = data.get('category_name')
                    name_categ = False
                    if category_name:
                        name_categ = request.env['product.category'].sudo().search(
                            [('complete_name', '=', category_name)], limit=1
                        )
                        if not name_categ:
                            errors.append({
                                'product_code': product_code,
                                'message': f"Category not found: {category_name}"
                            })
                            continue

                    # taxes
                    tax_command = []
                    for tax_name in data.get('taxes_names', []):
                        tax = request.env['account.tax'].sudo().search([('name', '=', tax_name)], limit=1)
                        if tax:
                            tax_command.append((4, tax.id))
                        else:
                            errors.append({'product_code': product_code, 'message': f"Tax not found: {tax_name}"})

                    # supplier taxes
                    supplier_tax_ids = []
                    for tax_name in data.get('supplier_taxes_id', []):
                        tax = request.env['account.tax'].sudo().search([('name', '=', tax_name)], limit=1)
                        if tax:
                            supplier_tax_ids.append(tax.id)
                        else:
                            errors.append({'product_code': product_code, 'message': f"Supplier Tax not found: {tax_name}"})

                    # pos category
                    pos_categ_ids = data.get('pos_categ_ids', [])
                    for categ_id in pos_categ_ids:
                        if not request.env['pos.category'].sudo().search([('id', '=', categ_id)], limit=1):
                            errors.append({'product_code': product_code, 'message': f"POS Category not found: {categ_id}"})

                    update_data = {
                        'name': data.get('product_name'),
                        'list_price': data.get('sales_price'),
                        'is_integrated': data.get('is_integrated'),
                        'detailed_type': data.get('product_type'),
                        'invoice_policy': data.get('invoice_policy'),
                        'standard_price': data.get('cost'),
                        'uom_id': data.get('uom_id'),
                        'uom_po_id': data.get('uom_po_id'),
                        'categ_id': name_categ.id if name_categ else False,
                        'pos_categ_ids': [(6, 0, pos_categ_ids)],
                        'taxes_id': tax_command,
                        'supplier_taxes_id': [(6, 0, supplier_tax_ids)],
                        'available_in_pos': data.get('available_in_pos'),
                        'barcode': data.get('barcode'),
                        'image_1920': data.get('image_1920'),
                        'vit_sub_div': data.get('vit_sub_div'),
                        'vit_item_kel': data.get('vit_item_kel'),
                        'vit_item_type': data.get('vit_item_type'),
                        'vit_item_brand': data.get('vit_item_brand'),
                    }
                    if data.get('active') is not None:
                        update_data['active'] = data.get('active')

                    master_item.sudo().write(update_data)

                    updated.append({
                        'id': master_item.id,
                        'product_code': product_code,
                        'name': master_item.name,
                        'status': 'success'
                    })

                except Exception as e:
                    errors.append({
                        'product_code': data.get('product_code'),
                        'message': f"Exception: {str(e)}"
                    })

            return {
                'code': 200 if not errors else 207,
                'status': 'partial_success' if errors else 'success',
                'updated_items': updated,
                'errors': errors,
            }

        except Exception as e:
            _logger.exception("Unexpected error in PATCH /api/master_item")
            return {'code': 500, 'status': 'error', 'message': str(e)}


class MasterPricelistPATCH(http.Controller):
    @http.route(['/api/master_pricelist/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_master_pricelist(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            name = data.get('name')
            currency_id = data.get('currency_id')
            pricelist_ids = data.get('pricelist_ids')

            master_pricelist = env['product.pricelist'].sudo().browse(int(return_id))
            if not master_pricelist.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'Master Pricelist not found',
                    'id': return_id
                }

            # Update name and currency_id
            master_pricelist.write({
                'name': name,
                'currency_id': currency_id,
                'write_uid': uid
            })

            # Update pricelist_ids
            for item in pricelist_ids:
                product_code = item['product_code']
                product = env['product.template'].sudo().search([('default_code', '=', product_code)], limit=1)
                if not product:
                    return {
                        'code': 404,
                        'status': 'error',
                        'message': f"Product with code {product_code} not found",
                        'id': return_id
                    }

                pricelist_item = env['product.pricelist.item'].sudo().search([
                    ('product_tmpl_id', '=', product.id),
                    ('pricelist_id', '=', return_id)
                ], limit=1)

                item_data = {
                    'min_quantity': item['quantity'],
                    'fixed_price': item['price'],
                    'date_start': item['date_start'],
                    'date_end': item['date_end'],
                    'write_uid': uid
                }

                if pricelist_item:
                    pricelist_item.write(item_data)
                else:
                    item_data.update({
                        'pricelist_id': return_id,
                        'product_tmpl_id': product.id,
                    })
                    env['product.pricelist.item'].sudo().create(item_data)

            return {
                'code': 200,
                'status': 'success',
                'message': 'Master Pricelist updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating master pricelist: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }

class MasterCategoryPATCH(http.Controller):
    @http.route(['/api/item_category/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_master_category_item(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            
            category_name = data.get('category_name')
            parent_category_id = data.get('parent_category_id')
            costing_method = data.get('costing_method')
            create_date = data.get('create_date')

            master_category = env['product.category'].sudo().browse(int(return_id))
            if not master_category.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'Master Category not found',
                    'id': return_id
                }

            # Update category
            master_category.write({
                'name': category_name,
                'parent_id': parent_category_id,
                'property_cost_method': costing_method,
                'create_date': create_date,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'Master Category updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating master category: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }
        
class MasterPoSCategoryPATCH(http.Controller):
    @http.route(['/api/pos_category/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_master_pos_category_item(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            
            category_name = data.get('category_name')
            
            master_category = env['pos.category'].sudo().browse(int(return_id))
            if not master_category.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'POS Category not found',
                    'id': return_id
                }

            # Update name
            master_category.write({
                'name': category_name,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'POS Category updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating POS category: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }

class GoodsIssuePATCH(http.Controller):
    @http.route(['/api/goods_issue/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_goods_issue_order(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            is_integrated = data.get('is_integrated')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': 'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            goods_issue_order = env['stock.picking'].sudo().search([
                ('id', '=', return_id),
                ('picking_type_id.name', '=', 'Goods Issue')
            ], limit=1)

            if not goods_issue_order.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'Goods Issue not found',
                    'id': return_id
                }

            goods_issue_order.write({
                'is_integrated': is_integrated,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'Goods Issue updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating Goods Issue: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }
        
class GoodsReceiptPATCH(http.Controller):
    @http.route(['/api/goods_receipt/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_goods_receipt_order(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            is_integrated = data.get('is_integrated')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': 'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            goods_receipt_order = env['stock.picking'].sudo().search([
                ('id', '=', return_id),
                ('picking_type_id.name', '=', 'Goods Receipts')
            ], limit=1)

            if not goods_receipt_order.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'Goods Receipt not found',
                    'id': return_id
                }

            goods_receipt_order.write({
                'is_integrated': is_integrated,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'Goods Receipt updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating Goods Receipt: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }

class GRPOPATCH(http.Controller):
    @http.route(['/api/grpo_transfer/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_grpo_order(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            is_integrated = data.get('is_integrated')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': 'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            grpo_order = env['stock.picking'].sudo().search([
                ('id', '=', return_id),
                ('picking_type_id.name', '=', 'GRPO')
            ], limit=1)

            if not grpo_order.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'GRPO not found',
                    'id': return_id
                }

            grpo_order.write({
                'is_integrated': is_integrated,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'GRPO updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating GRPO: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }
        
class InternalTransferPATCH(http.Controller):
    @http.route(['/api/internal_transfers/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_internal_transfer_order(self, return_id, **kwargs):
        return self._update_stock_picking(return_id, 'Internal Transfers', 'Internal Transfer')

class TsOutPATCH(http.Controller):
    @http.route(['/api/transfer_stock_out/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_transit_out_order(self, return_id, **kwargs):
        return update_stock_picking(return_id, 'TS Out', 'Transfer Stock Out')

class TsInPATCH(http.Controller):
    @http.route(['/api/transfer_stock_in/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_transit_in_order(self, return_id, **kwargs):
        return update_stock_picking(return_id, 'TS In', 'Transfer Stock In')

def update_stock_picking(return_id, picking_type_name, operation_name):
    try:
        # Get configuration
        config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
        if not config:
            return {
                'status': "Failed",
                'code': 500,
                'message': "Configuration not found.",
            }

        username = config.vit_config_username
        password = config.vit_config_password_api

        # Manual authentication
        uid = request.session.authenticate(request.session.db, username, password)
        if not uid:
            return {
                'status': "Failed",
                'code': 401,
                'message': "Authentication failed.",
            }

        # Use superuser environment
        env = request.env(user=request.env.ref('base.user_admin').id)

        data = request.get_json_data()
        is_integrated = data.get('is_integrated')

        if not isinstance(is_integrated, bool):
            return {
                'code': 400,
                'status': 'error',
                'message': f'Invalid data: is_integrated must be a boolean',
                'id': return_id
            }

        stock_picking = env['stock.picking'].sudo().search([
            ('id', '=', return_id),
            ('picking_type_id.name', '=', picking_type_name)
        ], limit=1)

        if not stock_picking.exists():
            return {
                'code': 404,
                'status': 'error',
                'message': f'{operation_name} not found',
                'id': return_id
            }

        stock_picking.write({
            'is_integrated': is_integrated,
            'write_uid': uid
        })

        return {
            'code': 200,
            'status': 'success',
            'message': f'{operation_name} updated successfully',
            'id': return_id
        }

    except Exception as e:
        _logger.error(f"Error updating {operation_name}: {str(e)}")
        return {
            'code': 500,
            'status': 'error',
            'message': str(e),
            'id': return_id
        }

class AccountMovePATCH(http.Controller):
    @http.route(['/api/invoice_order/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_invoice_order(self, return_id, **kwargs):
        return self._update_account_move(return_id, 'out_invoice', 'Invoice')

    @http.route(['/api/credit_memo/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_credit_memo(self, return_id, **kwargs):
        return self._update_account_move(return_id, 'out_refund', 'Credit Memo')

    @staticmethod
    def _update_account_move(return_id, move_type, operation_name):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            is_integrated = data.get('is_integrated')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': f'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            account_move = env['account.move'].sudo().search([
                ('id', '=', return_id),
                ('move_type', '=', move_type)
            ], limit=1)

            if not account_move.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': f'{operation_name} not found',
                    'id': return_id
                }

            account_move.write({
                'is_integrated': is_integrated,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': f'{operation_name} updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating {operation_name}: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }
        
class PaymentPATCH(http.Controller):
    @http.route(['/api/payment_invoice/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_payment_invoice(self, return_id, **kwargs):
        return self._update_payment(return_id, 'Payment Invoice')

    @http.route(['/api/payment_creditmemo/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_payment_credit_memo(self, return_id, **kwargs):
        return self._update_payment(return_id, 'Payment Credit Memo')

    @staticmethod
    def _update_payment(return_id, operation_name):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            is_integrated = data.get('is_integrated')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': f'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            payment = env['account.move'].sudo().search([
                ('id', '=', return_id),
                ('move_type', '=', 'entry')
            ], limit=1)

            if not payment.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': f'{operation_name} not found',
                    'id': return_id
                }

            payment.write({
                'is_integrated': is_integrated,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': f'{operation_name} updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating {operation_name}: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }

class PurchaseOrderPATCH(http.Controller):
    @http.route(['/api/purchase_order/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_purchase_order(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            is_integrated = data.get('is_integrated')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': 'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            purchase_order = env['purchase.order'].sudo().search([('id', '=', return_id)], limit=1)

            if not purchase_order.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'Purchase Order not found',
                    'id': return_id
                }

            purchase_order.write({
                'is_integrated': is_integrated,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'Purchase Order updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating Purchase Order: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }
        
class ManufactureOrderPATCH(http.Controller):
    @http.route(['/api/manufacture_order/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_manufacture_order(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search(
                [('vit_config_server', '=', 'mc')], limit=1
            )
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}

            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            data = request.get_json_data()
            is_integrated = data.get('is_integrated')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': 'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            mo = env['mrp.production'].sudo().search([('id', '=', return_id)], limit=1)
            if not mo.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'Manufacture Order not found',
                    'id': return_id
                }

            mo.write({
                'is_integrated': is_integrated,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'Manufacture Order updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating Manufacture Order: {str(e)}")
            return {'code': 500, 'status': 'error', 'message': str(e), 'id': return_id}


class UnbuildOrderPATCH(http.Controller):
    @http.route(['/api/unbuild_order/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_unbuild_order(self, return_id, **kwargs):
        try:
            config = request.env['setting.config'].sudo().search(
                [('vit_config_server', '=', 'mc')], limit=1
            )
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}

            username = config.vit_config_username
            password = config.vit_config_password_api

            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            data = request.get_json_data()
            is_integrated = data.get('is_integrated')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': 'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            unbuild = env['mrp.unbuild'].sudo().search([('id', '=', return_id)], limit=1)
            if not unbuild.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'Unbuild Order not found',
                    'id': return_id
                }

            unbuild.write({
                'is_integrated': is_integrated,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'Unbuild Order updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating Unbuild Order: {str(e)}")
            return {'code': 500, 'status': 'error', 'message': str(e), 'id': return_id}
