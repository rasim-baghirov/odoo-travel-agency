import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

EMAIL_RE = re.compile(r'^[\w.%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # -----Fields-----
    travel_booking_ids = fields.One2many('travel.booking', 'partner_id')
    travel_booking_count = fields.Integer(compute='_compute_travel_booking_count')


    # -----Compute-----
    @api.depends('travel_booking_ids.state')
    def _compute_travel_booking_count(self):
        for rec in self:
            rec.travel_booking_count = len(
                rec.travel_booking_ids.filtered(lambda b: b.state == 'confirmed'))


    # -----UI Helpers-----
    @api.onchange('email')
    def _onchange_email_format(self):
        if self.email and not EMAIL_RE.match(self.email.strip()):
            return {'warning': {
                'title': _('Invalid email'),
                'message': _('Please enter a valid email, for example name@gmail.com'),
            }}


    # -----Constraints-----
    @api.constrains('email')
    def _check_email_format(self):
        for rec in self:
            if rec.email and not EMAIL_RE.match(rec.email.strip()):
                raise ValidationError(
                    _('Invalid email address: "%s". Example: name@gmail.com') % rec.email)


    # -----Actions-----
    def action_view_travel_bookings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bookings'),
            'res_model': 'travel.booking',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }
