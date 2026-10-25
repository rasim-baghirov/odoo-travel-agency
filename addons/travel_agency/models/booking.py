from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

GROUP_SIZE = 5
GROUP_DISCOUNT = 10.0
LOCKED_FIELDS = {'tour_id', 'persons', 'price_unit'}


class TravelBooking(models.Model):
    _name = 'travel.booking'
    _description = 'Tour Booking'
    _order = 'id desc'


    # -----Fields-----
    name = fields.Char(default='New', readonly=True, copy=False)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    tour_id = fields.Many2one('travel.tour', string='Tour', required=True, domain="[('state', '=', 'open')]")
    date_start = fields.Date(related='tour_id.date_start', store=True)
    tour_available_seats = fields.Integer(string='Seats left', related='tour_id.available_seats')
    persons = fields.Integer(default=1, required=True)
    currency_id = fields.Many2one('res.currency', compute='_compute_price_unit', store=True)
    price_unit = fields.Monetary(compute='_compute_price_unit', store=True, readonly=False, currency_field='currency_id')
    discount_percent = fields.Float(compute='_compute_discount', store=True)
    amount_total = fields.Monetary(compute='_compute_amount', store=True, currency_field='currency_id')
    state = fields.Selection(
        [('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancelled', 'Cancelled')],
        default='draft', required=True, copy=False)


    # -----Compute-----
    @api.depends('tour_id')
    def _compute_price_unit(self):
        for rec in self:
            rec.price_unit = rec.tour_id.price
            rec.currency_id = rec.tour_id.currency_id

    @api.depends('persons')
    def _compute_discount(self):
        for rec in self:
            rec.discount_percent = GROUP_DISCOUNT if rec.persons >= GROUP_SIZE else 0.0

    @api.depends('price_unit', 'persons', 'discount_percent')
    def _compute_amount(self):
        for rec in self:
            rec.amount_total = rec.price_unit * rec.persons * (1 - rec.discount_percent / 100.0)


    # -----Constraints-----
    @api.constrains('persons', 'price_unit')
    def _check_values(self):
        for rec in self:
            if rec.persons <= 0:
                raise ValidationError(_('Number of persons must be at least 1.'))
            if rec.price_unit < 0:
                raise ValidationError(_('Price cannot be negative.'))

    @api.constrains('partner_id')
    def _check_partner_contacts(self):
        for rec in self:
            if not rec.partner_id.phone or not rec.partner_id.email:
                raise ValidationError(
                    _('Customer "%s" must have both a phone and an email.')
                    % rec.partner_id.name)

    @api.constrains('tour_id')
    def _check_tour_open_for_draft(self):
        for rec in self:
            if rec.state == 'draft' and rec.tour_id.state != 'open':
                raise ValidationError(_('You can only book an open tour.'))

    @api.constrains('state', 'persons', 'tour_id')
    def _check_draft_seats(self):
        for rec in self.filtered(lambda r: r.state == 'draft'):
            left = rec.tour_id.available_seats

            if rec.persons > left:
                raise ValidationError(
                    _('Not enough free seats on "%(tour)s": only %(left)s left, '
                      'but you requested %(persons)s.')
                    % {'tour': rec.tour_id.name, 'left': left, 'persons': rec.persons})

    @api.constrains('state', 'persons', 'tour_id')
    def _check_seats(self):
        """Safety net: confirmed seats never exceed the tour capacity."""
        for rec in self.filtered(lambda r: r.state == 'confirmed'):
            confirmed = rec.tour_id.booking_ids.filtered(lambda b: b.state == 'confirmed')

            if sum(confirmed.mapped('persons')) > rec.tour_id.max_seats:
                raise ValidationError(
                    _('Not enough seats on tour "%s".') % rec.tour_id.name)


    # -----Onchange-----
    @api.onchange('tour_id', 'persons')
    def _onchange_seats_warning(self):
        if self.tour_id and self.persons > self.tour_id.available_seats:
            return {'warning': {
                'title': _('Not enough seats'),
                'message': _('Only %s seat(s) left on this tour.')% self.tour_id.available_seats,
            }}


    # -----State Rules-----
    def _check_can_confirm(self):
        today = fields.Date.context_today(self)
        for rec in self:
            tour = rec.tour_id

            if rec.state != 'draft':
                raise UserError(_('Only draft bookings can be confirmed.'))

            if tour.state != 'open':
                raise UserError(_('The tour is not open for booking.'))

            if tour.date_start <= today:
                raise UserError(_('The tour has already started.'))

            if rec.persons > tour.available_seats:
                raise UserError(_('Only %s seat(s) left on this tour.') % tour.available_seats)

    def _check_can_cancel(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.tour_id.date_start <= today:
                raise UserError(
                    _('Cannot cancel a confirmed booking after the tour has started.'))

    # -----ORM Overrides-----
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('state', 'draft') != 'draft':
                raise ValidationError(_('Bookings must be created as draft and then confirmed.'))

            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('travel.booking') or 'New'

        return super().create(vals_list)

    def write(self, vals):
        if LOCKED_FIELDS & vals.keys() and any(r.state != 'draft' for r in self):
            raise UserError(_('Only draft bookings can be edited. Reset the booking to draft first.'))

        new_state = vals.get('state')
        if new_state == 'confirmed':
            self.filtered(lambda r: r.state != 'confirmed')._check_can_confirm()
        elif new_state == 'cancelled':
            self.filtered(lambda r: r.state == 'confirmed')._check_can_cancel()

        was_confirmed = self.filtered(lambda r: r.state == 'confirmed')
        res = super().write(vals)

        if new_state == 'confirmed':
            self.tour_id.sudo()._auto_close_if_full()
        elif new_state == 'cancelled' and was_confirmed:
            was_confirmed.tour_id.sudo()._auto_reopen_if_free()

        return res

    def unlink(self):
        tours = self.filtered(lambda r: r.state == 'confirmed').tour_id
        res = super().unlink()
        tours.sudo()._auto_reopen_if_free()
        return res

    # -----Actions-----
    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.filtered(lambda r: r.state == 'cancelled').write({'state': 'draft'})
