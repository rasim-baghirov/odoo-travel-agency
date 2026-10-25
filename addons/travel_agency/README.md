# Travel Agency (Odoo 17)

Module for managing tours and customer bookings.

## Features
- **Tours**: dates, price per person, seat limit, computed free seats, statuses (draft / open / closed), kanban/list/form views, chatter.
- **Bookings**: sequence (BK/0001), frozen price per person, group discount (10% from 5 persons), confirm/cancel workflow.
- **res.partner inherit**: smart button with the number of confirmed trips.
- **Cron**: daily auto-close of tours that have already started.
- **Security**: User (create/edit bookings, read tours) and Manager (full access).

## Business rules
- Only open tours can be booked; only confirmed bookings occupy seats.
- Confirmation fails if there are not enough seats (also protected by a constraint).
- A confirmed booking cannot be cancelled after the tour has started.
- End date must not be earlier than start date; max seats cannot go below booked seats.

## Install
Copy the `travel_agency` folder to your addons path, update the apps list, install **Travel Agency**.
