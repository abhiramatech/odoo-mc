import json
import pytz
import werkzeug.exceptions
from odoo import http, _, fields
from odoo.http import request
from odoo.exceptions import ValidationError
from odoo.addons.dev_pos.controller.api_utils import (
    check_authorization,
    paginate_records,
    serialize_response,
    serialize_error_response,
)

import logging

_logger = logging.getLogger(__name__)

# State yang sudah boleh ditarik SAP jadi dokumen Transfer Request.
# Draft / To Approve belum final, jadi tidak ikut dikirim.
INTEGRATION_STATES = ['approved', 'in_progress', 'done']


class TransferRequestAPI(http.Controller):

    @http.route(['/api/transfer_request/'], type='http', auth='public', methods=['GET'], csrf=False)
    def get_transfer_request(self, createdDateFrom=None, createdDateTo=None, pageSize=200, page=1,
                             q=None, is_integrated=None, state=None, **params):
        try:
            check_authorization()

            if int(page) == 0:
                return serialize_response([], 0, 0)

            date_format = '%Y-%m-%d'
            domain = [('state', 'in', [state] if state else INTEGRATION_STATES)]

            if q:
                domain += [('doc_num', 'ilike', str(q))]

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
                transfer_requests, total_records = paginate_records('transfer.request', domain, pageSize, page)
            else:
                transfer_requests = request.env['transfer.request'].sudo().search(domain)
                total_records = len(transfer_requests)

            data_transfer_request = []
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            for order in transfer_requests:
                create_date_jakarta = pytz.utc.localize(order.create_date).astimezone(jakarta_tz)
                order_data = {
                    'id': order.id,
                    'doc_num': order.doc_num,
                    'transaction_id': order.vit_trxid,
                    'request_type': order.request_type,
                    'transfer_type': order.transfer_type_id.name or "",
                    'warehouse_id': order.warehouse_id.id,
                    'warehouse': order.warehouse_id.name,
                    'location_id': order.location_id.id,
                    'location': order.location_id.complete_name,
                    'warehouse_dest_id': order.warehouse_dest_id.id or "",
                    'warehouse_dest': order.warehouse_dest_id.name or "",
                    'location_dest_id': order.location_dest_id.id,
                    'location_dest': order.location_dest_id.complete_name,
                    'requested_by': order.requested_by_id.name or "",
                    'create_date': str(create_date_jakarta),
                    'request_date': str(order.request_date),
                    'scheduled_date': str(order.scheduled_date) if order.scheduled_date else "",
                    'is_integrated': order.is_integrated,
                    'state': order.state,
                }
                data_transfer_request.append(order_data)

            total_pages = (total_records + pageSize - 1) // pageSize

            return serialize_response(data_transfer_request, total_records, total_pages)

        except ValidationError:
            error_response = {
                'error': 'One or more required parameters are missing.',
                'status': 500
            }
            return http.Response(json.dumps(error_response), content_type='application/json', status=500)

        except Exception as e:
            return serialize_error_response(str(e))

    @http.route(['/api/transfer_request_line/<int:order_id>'], type='http', auth='public',
                methods=['GET'], csrf=False)
    def get_transfer_request_lines(self, order_id, **params):
        try:
            check_authorization()

            transfer_request = request.env['transfer.request'].sudo().browse(order_id)
            if not transfer_request.exists():
                raise werkzeug.exceptions.NotFound(_("Transfer Request"))

            jakarta_tz = pytz.timezone('Asia/Jakarta')
            create_date_jakarta = pytz.utc.localize(transfer_request.create_date).astimezone(jakarta_tz)

            data_transfer_request_lines = []
            for line_number, line in enumerate(transfer_request.line_ids, start=1):
                line_data = {
                    'line_number': line.vit_line_number_sap or line_number,
                    'id': line.id,
                    'doc_no': transfer_request.doc_num,
                    'location_id': transfer_request.location_id.id,
                    'location_name': transfer_request.location_id.complete_name,
                    'location_dest_id': transfer_request.location_dest_id.id,
                    'location_dest': transfer_request.location_dest_id.complete_name,
                    'product_id': line.product_id.id,
                    'product_code': line.product_id.default_code or "",
                    'product_name': line.product_id.name,
                    'demand_qty': line.product_uom_qty,
                    'quantity': line.qty_transferred,
                    'remaining_qty': line.qty_remaining,
                    'product_uom': line.product_uom_id.name,
                    'notes': line.vit_notes or "",
                }
                data_transfer_request_lines.append(line_data)

            response_data = {
                'status': 200,
                'message': 'success',
                'doc_num': transfer_request.doc_num,
                'transaction_id': transfer_request.vit_trxid,
                'request_type': transfer_request.request_type,
                'transfer_type': transfer_request.transfer_type_id.name or "",
                'warehouse_id': transfer_request.warehouse_id.id,
                'warehouse': transfer_request.warehouse_id.name,
                'location_id': transfer_request.location_id.id,
                'location': transfer_request.location_id.complete_name,
                'warehouse_dest_id': transfer_request.warehouse_dest_id.id or "",
                'warehouse_dest': transfer_request.warehouse_dest_id.name or "",
                'location_dest_id': transfer_request.location_dest_id.id,
                'location_dest': transfer_request.location_dest_id.complete_name,
                'requested_by': transfer_request.requested_by_id.name or "",
                'created_date': str(create_date_jakarta),
                'request_date': str(transfer_request.request_date),
                'scheduled_date': str(transfer_request.scheduled_date) if transfer_request.scheduled_date else "",
                'state': transfer_request.state,
                'items': data_transfer_request_lines,
            }
            return werkzeug.wrappers.Response(
                status=200,
                content_type='application/json; charset=utf-8',
                response=json.dumps(response_data)
            )

        except Exception as e:
            return serialize_error_response(str(e))


class TransferRequestPATCH(http.Controller):

    @http.route(['/api/transfer_request/<int:return_id>'], type='json', auth='none',
                methods=['PATCH'], csrf=False)
    def update_transfer_request(self, return_id, **kwargs):
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
            vit_trxid = data.get('vit_trxid')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': 'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            transfer_request = env['transfer.request'].sudo().search([('id', '=', return_id)], limit=1)

            if not transfer_request.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'Transfer Request not found',
                    'id': return_id
                }

            vals = {
                'is_integrated': is_integrated,
                'write_uid': uid,
            }
            # vit_trxid opsional, dipakai kalau SAP mengirim balik nomor dokumennya
            if vit_trxid:
                vals['vit_trxid'] = vit_trxid

            transfer_request.write(vals)

            return {
                'code': 200,
                'status': 'success',
                'message': 'Transfer Request updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating Transfer Request: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }
