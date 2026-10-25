from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class TravelTour(models.Model):
    _name = 'travel.tour'
    _description = 'Tour'
    _order = 'state_order, date_start, id'


    # -----Fields-----
    name = fields.Char(required=True)
    destination = fields.Char(required=True)
    description = fields.Text()
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    duration = fields.Integer(compute='_compute_duration', store=True, help='Days')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    price = fields.Monetary(string='Price per person', currency_field='currency_id', required=True)
    max_seats = fields.Integer(default=10, required=True)
    booking_ids = fields.One2many('travel.booking', 'tour_id')
    booked_seats = fields.Integer(compute='_compute_seats', store=True)
    available_seats = fields.Integer(compute='_compute_seats', store=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('open', 'Open'), ('closed', 'Closed')],
        default='draft', required=True, copy=False,
        group_expand='_read_group_states')
    state_order = fields.Integer(compute='_compute_state_order', store=True)
    auto_closed = fields.Boolean(default=False, copy=False)


    # -----Compute-----
    @api.depends('state')
    def _compute_state_order(self):
        order = {'draft': 0, 'open': 1, 'closed': 2}
        for rec in self:
            rec.state_order = order[rec.state]

    @api.model
    def _read_group_states(self, states, domain, order):
        return [key for key, _label in self._fields['state'].selection]

    @api.depends('date_start', 'date_end')
    def _compute_duration(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end >= rec.date_start:
                rec.duration = (rec.date_end - rec.date_start).days + 1
            else:
                rec.duration = 0

    @api.depends('max_seats', 'booking_ids.state', 'booking_ids.persons')
    def _compute_seats(self):
        for rec in self:
            confirmed = rec.booking_ids.filtered(lambda b: b.state == 'confirmed')
            rec.booked_seats = sum(confirmed.mapped('persons'))
            rec.available_seats = rec.max_seats - rec.booked_seats


    # -----Onchange / Constraints-----
    @api.onchange('date_start', 'date_end')
    def _onchange_dates(self):
        if self.date_start and self.date_end and self.date_end < self.date_start:
            return {'warning': {
                'title': _('Invalid dates'),
                'message': _('End date cannot be earlier than start date.'),
            }}

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_end < rec.date_start:
                raise ValidationError(_('End date cannot be earlier than start date.'))

    @api.constrains('max_seats', 'price')
    def _check_seats_price(self):
        for rec in self:
            if rec.max_seats <= 0:
                raise ValidationError(_('Max seats must be positive.'))

            if rec.price < 0:
                raise ValidationError(_('Price cannot be negative.'))

            if rec.max_seats < rec.booked_seats:
                raise ValidationError(
                    _('Max seats cannot be lower than already booked seats (%s).')
                    % rec.booked_seats)


    # -----Actions-----
    def action_open(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.date_start <= today:
                raise UserError(_('Cannot open a tour that starts today or has already started.'))

            if rec.available_seats <= 0:
                raise UserError(_(
                    'All seats are taken. Cancel a booking to free a seat, '
                    'the tour will reopen automatically.'))

        self.write({'state': 'open', 'auto_closed': False})

    def action_close(self):
        self.write({'state': 'closed', 'auto_closed': False})

    def action_reset_draft(self):
        for rec in self:
            if rec.booking_ids.filtered(lambda b: b.state == 'confirmed'):
                raise UserError(_('Cannot reset a tour that has confirmed bookings.'))
        self.write({'state': 'draft', 'auto_closed': False})

    def action_view_bookings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bookings'),
            'res_model': 'travel.booking',
            'view_mode': 'tree,form',
            'domain': [('tour_id', '=', self.id)],
            'context': {'default_tour_id': self.id},
        }


    # -----Automatic Open / Close-----
    def _auto_close_if_full(self):
        """Close open tours that have no free seats left."""
        full = self.filtered(lambda t: t.state == 'open' and t.available_seats <= 0)
        full.write({'state': 'closed', 'auto_closed': True})

    def _auto_reopen_if_free(self):
        """Reopen tours that were closed automatically once a seat is free again."""
        today = fields.Date.context_today(self)
        free = self.filtered(
            lambda t: t.state == 'closed' and t.auto_closed
            and t.available_seats > 0 and t.date_start > today)
        free.write({'state': 'open', 'auto_closed': False})


    # -----Write Override-----
    def write(self, vals):
        res = super().write(vals)
        if 'max_seats' in vals:
            self._auto_reopen_if_free()
            self._auto_close_if_full()
        return res


    # -----Scheduled Actions-----
    @api.model
    def _cron_close_started_tours(self):
        """Close open tours that start today or earlier."""
        tours = self.search([('state', '=', 'open'),
                             ('date_start', '<=', fields.Date.context_today(self))])
        tours.action_close()
